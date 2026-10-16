"""
ResistanceAI v9 predictor — calibrated ensemble inference.

Loads the v9 artifact (bagged HistGradientBoosting ensemble + isotonic
calibration) and produces:
  * calibrated risk score with an ensemble-spread uncertainty interval
  * cohort percentile placement
  * patient-specific feature attributions (leave-one-out ablation)
  * mechanistic resistance hypotheses (backend.mechanisms)
  * evidence-ranked therapy matching (expanded treatments.json)

Backward compatible: legacy 7-feature inputs are mapped onto the clinical
input schema with median imputation.
"""

import os
import json
import pickle
import warnings
import numpy as np
from typing import Dict, Any, List, Optional

try:
    from threadpoolctl import threadpool_limits

    def _st_predict():
        # HGB predict OpenMP-parallelizes even single-row calls; at these
        # batch sizes (<=~50 rows) thread dispatch/sync costs exceed the
        # kernel itself — on some hosts by orders of magnitude. Serial is
        # the correct latency choice for interactive inference.
        return threadpool_limits(limits=1)
except Exception:  # threadpoolctl ships with sklearn; guard anyway
    from contextlib import nullcontext

    def _st_predict():
        return nullcontext()

from .features import (build_model_vector, feature_display_name,
                       fusion_gene_set, normalize_clinical_input,
                       is_msi_unstable, HRD_GENES, MMR_GENES)
from .mechanisms import analyze as analyze_mechanisms


class ResistancePredictor:
    """v9 frontier predictor wrapper."""

    def __init__(self, model_dir: str = None):
        model_dir = model_dir or os.environ.get(
            "RESISTANCEAI_MODEL_DIR", "backend/artifacts")
        v2_path = os.path.join(model_dir, "resistance_model_v2.pkl")
        with open(v2_path, "rb") as f:
            art = pickle.load(f)
        self.models = art["models"]
        self.isotonic = art["isotonic"]
        self.feature_names = art["feature_names"]
        self.medians = art["medians"]
        self.meta = art.get("meta", {})
        self.cohort_risk = np.sort(art.get("cohort_risk", np.array([0.5])))

        trained_sk = self.meta.get("sklearn_version")
        if trained_sk:
            import sklearn
            if trained_sk.split(".")[:2] != sklearn.__version__.split(".")[:2]:
                warnings.warn(
                    f"Model artifact was trained with scikit-learn {trained_sk} "
                    f"but {sklearn.__version__} is installed — retrain via "
                    "backend/models/train_v2.py or install the pinned version.",
                    stacklevel=2)

        kb_path = os.path.join(os.path.dirname(__file__), "knowledge_base",
                               "treatments.json")
        try:
            with open(kb_path) as f:
                self.kb = json.load(f)
        except Exception as e:
            print(f"Warning: treatments.json failed to load: {e}")
            self.kb = {"cancer_types": {}, "universal_biomarkers": {}}

    # ------------------------------------------------------------------ API

    def predict_resistance(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        clinical = normalize_clinical_input(input_data)
        vec = build_model_vector(clinical, self.medians)
        x = np.array([[vec.get(f, 0.0) for f in self.feature_names]])

        with _st_predict():
            ens = np.array([m.predict_proba(x)[:, 1][0] for m in self.models])
        raw = float(ens.mean())
        proba = float(self.isotonic.predict([raw])[0])
        spread = float(ens.std())
        risk_score = int(round(proba * 100))
        # Ensemble-spread interval: disagreement across the 8 bagged models.
        # A model-uncertainty proxy, not a calibrated coverage guarantee.
        ci_half = max(2, int(round(1.645 * spread * 100)))
        percentile = float(np.searchsorted(self.cohort_risk, proba) /
                           max(len(self.cohort_risk), 1) * 100)

        mechanisms = analyze_mechanisms(clinical)
        contributions = self._attributions(vec, raw)
        therapies = self._match_therapies(clinical)
        risk_tier, interpretation = self._interpret(risk_score, clinical, mechanisms)

        return {
            "risk_score": risk_score,
            "risk_tier": risk_tier,
            "probability": proba,
            "risk_ci": [max(0, risk_score - ci_half), min(100, risk_score + ci_half)],
            "cohort_percentile": round(percentile, 1),
            "interpretation": interpretation,
            "mechanisms": mechanisms,
            "feature_contributions": contributions,
            "recommendation": {
                "summary": "Escalated monitoring + targeted-therapy evaluation recommended."
                           if risk_tier == "HIGH" else
                           "Proceed with biomarker-guided protocol.",
                "therapies": therapies,
                "trials": [],
            },
            "model_version": self.meta.get("version", "v9"),
            "n_training": self.meta.get("n_training"),
        }

    # ------------------------------------------------------------- internals

    def _attributions(self, vec: Dict[str, float], base_raw: float) -> List[Dict[str, Any]]:
        """Patient-specific ablation: effect of reverting each active feature."""
        candidates = []
        for f in self.feature_names:
            v = vec.get(f, 0.0)
            if v and v != self.medians.get(f):
                if f.startswith(("mut_", "cna_", "fusion_", "hrd_", "mmr_", "msi_",
                                 "pole_", "immune_", "ct_")):
                    candidates.append((f, 0.0))
                elif f in ("tmb_log", "fga", "n_amp", "n_deepdel", "sv_count",
                           "stage_ord", "age_at_diagnosis", "msi_score", "n_mut",
                           "driver_alt_count", "is_metastatic", "smoking_ever",
                           "tumor_purity", "n_indel_frac", "sex_male") or \
                        f.startswith(("pathway_", "frac_")):
                    candidates.append((f, self.medians.get(f, 0.0)))
        if not candidates:
            return []

        rows = [vec.copy() for _ in candidates]
        for row, (f, repl) in zip(rows, candidates):
            row[f] = repl
        X = np.array([[r.get(f, 0.0) for f in self.feature_names] for r in rows])
        # ensemble-mean delta so attribution matches the scored model
        with _st_predict():
            ablated = np.mean([m.predict_proba(X)[:, 1] for m in self.models],
                              axis=0)
        deltas = []
        for (f, _), p in zip(candidates, ablated):
            deltas.append({"name": f, "display": feature_display_name(f),
                           "weight": float(base_raw - p)})
        deltas.sort(key=lambda d: -abs(d["weight"]))
        return deltas[:12]

    @staticmethod
    def _protein_change(ci: Dict[str, Any], gene: str, prefix: str) -> bool:
        """True when a specific protein-level alteration is evidenced.

        Sources: corpus/report `mutation_details` (e.g. {"gene": "BRAF",
        "protein_change": "V600E"}) or legacy variant hints like
        "BRAF_V600E"/"BRAF-V600E". Returns False when only the gene is known.
        """
        for d in ci.get("mutation_details") or []:
            if not (isinstance(d, dict) and d.get("gene") == gene):
                continue
            pc = str(d.get("protein_change", ""))
            if pc.startswith("p."):
                pc = pc[2:]
            if pc.startswith(prefix):
                return True
        for h in ci.get("variant_hints") or []:
            if isinstance(h, str) and \
                    h.replace("-", "_").startswith(f"{gene}_{prefix}"):
                return True
        return False

    def _match_therapies(self, ci: Dict[str, Any]) -> List[Dict[str, Any]]:
        site = ci["cancer_type_canonical"]
        biom = (self.kb.get("cancer_types", {}).get(site, {})
                .get("biomarkers", {}))
        uni = self.kb.get("universal_biomarkers", {})

        muts = set(ci.get("gene_mutations") or [])
        cna = ci.get("cna") or {}
        amps = {g for g, v in cna.items() if v >= 2}
        dels = {g for g, v in cna.items() if v <= -2}
        fus_genes = fusion_gene_set(ci.get("fusions"))

        hits, seen = [], set()

        def add(key, tag):
            for reg in biom.get(key, {}).get("regimens", []):
                if reg["name"] not in seen:
                    seen.add(reg["name"])
                    r = dict(reg)
                    r["matched_biomarker"] = tag or key
                    hits.append(r)

        actionable = muts | amps | dels | fus_genes
        for g in sorted(actionable):
            add(g, f"{g} alteration")
        # Legacy biomarker labels matched directly against KB keys
        # (e.g. "BRCA1/2", "PTEN_Loss", "BRAF_V600E" in the v8 payload format).
        for v in ci.get("variant_hints", []):
            add(v, v)
        if fus_genes & {"NTRK1", "NTRK2", "NTRK3"}:
            for reg in uni.get("NTRK_fusion", []):
                if reg["name"] not in seen:
                    seen.add(reg["name"]); hits.append(dict(reg, matched_biomarker="NTRK fusion"))
        if fus_genes & {"RET"}:
            for reg in uni.get("RET_fusion", []):
                if reg["name"] not in seen:
                    seen.add(reg["name"]); hits.append(dict(reg, matched_biomarker="RET fusion"))
        if fus_genes & {"NRG1"}:
            for reg in uni.get("NRG1_fusion", []):
                if reg["name"] not in seen:
                    seen.add(reg["name"]); hits.append(dict(reg, matched_biomarker="NRG1 fusion"))

        hrd = ci.get("hr_deficiency") == "present" or bool(muts & set(HRD_GENES)) or \
            bool(dels & {"BRCA1", "BRCA2"})
        if hrd:
            add("HRD_Positive", "HRD signature")
        if is_msi_unstable(ci.get("msi_type")) or \
                bool(muts & set(MMR_GENES)):
            for reg in uni.get("MSI-H", []):
                if reg["name"] not in seen:
                    seen.add(reg["name"]); hits.append(dict(reg, matched_biomarker="MSI-High"))
        tmb = ci.get("tmb") or 0
        if tmb >= 10:
            add("TMB-H", f"TMB {tmb:.0f} mut/Mb")
            for reg in uni.get("TMB-H", []):
                if reg["name"] not in seen:
                    seen.add(reg["name"]); hits.append(dict(reg, matched_biomarker="TMB-High"))
        if "POLE" in muts and tmb >= 40:
            # Ultramutation is the therapeutic rationale — a lone POLE missense
            # without a hypermutator phenotype does not support the IO tag.
            for reg in uni.get("POLE", []):
                if reg["name"] not in seen:
                    seen.add(reg["name"]); hits.append(dict(reg, matched_biomarker="POLE ultramutated"))
        if "ERBB2" in amps or ci.get("her2_positive"):
            for reg in uni.get("HER2_IHC3", []):
                if reg["name"] not in seen:
                    seen.add(reg["name"]); hits.append(dict(reg, matched_biomarker="HER2 amplification"))
        if "BRAF" in muts and self._protein_change(ci, "BRAF", "V600"):
            # Site-agnostic approval is V600-specific — class II/III BRAF
            # alterations and fusions must not trigger the V600E tag.
            for reg in uni.get("BRAF_V600E", []):
                if reg["name"] not in seen:
                    seen.add(reg["name"]); hits.append(dict(reg, matched_biomarker="BRAF V600E"))

        if not hits:
            hits.append({
                "name": "Institutional Standard of Care",
                "type": "Standard of Care", "line": "1st-Line",
                "guideline_tier": "Standard Care", "evidence_level": "Level 2-3",
                "regulatory_status": "FDA Approved",
                "rationale": "No FDA-level actionable biomarkers detected; evaluate clinical trials and standard regimens.",
                "patient_explanation": "Standard chemotherapy for this tumor type.",
            })
        return hits[:8]

    def _interpret(self, risk_score, ci, mechanisms):
        n_mech = len([m for m in mechanisms if not m.get("sensitivity")])
        if risk_score >= 70:
            tier = "HIGH"
            text = (f"Multi-omic signature indicates high escape pressure ({risk_score}%). "
                    f"{n_mech} plausible resistance mechanism(s) identified.")
        elif risk_score >= 40:
            tier = "MODERATE"
            text = (f"Intermediate resistance probability ({risk_score}%). "
                    "Genomic context supports standard protocols with biomarker-linked escalation on progression.")
        else:
            tier = "LOW"
            text = (f"Favorable therapeutic window ({risk_score}%). "
                    "Genome suggests durable response to front-line standard-of-care.")
        return tier, text


_predictor = None


def get_predictor() -> Optional[ResistancePredictor]:
    global _predictor
    if _predictor is None:
        try:
            _predictor = ResistancePredictor(
                model_dir=os.environ.get("RESISTANCEAI_MODEL_DIR",
                                         "backend/artifacts"))
        except Exception as e:
            print(f"Predictor init failed: {e}")
            return None
    return _predictor


def predict_resistance(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Predict via the shared singleton. Raises if the model artifact is
    unavailable — callers must surface an error rather than a fabricated score."""
    p = get_predictor()
    if not p:
        raise RuntimeError("model artifact unavailable — "
                           "run backend/models/train_v2.py")
    return p.predict_resistance(input_data)
