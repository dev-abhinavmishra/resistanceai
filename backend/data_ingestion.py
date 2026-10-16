
import json
from typing import Dict, Any, List, Optional
import os

from .corpus import load_records, data_path, record_uid, record_sample_uid
from .features import canonical_cancer_type, normalize_msi_type


class ClinicalDataIngestor:
    """
    Enterprise ingestion for ResistanceAI v9.
    Normalizes FHIR-like EHR records and structured genomic (NGS) reports
    into the shared clinical-input schema used by the model.
    """

    @staticmethod
    def ingest_genomic_report(file_content: str, format: str = "json") -> Dict[str, Any]:
        """
        Parses a structured genomic report (Illumina/Foundation-like) into the
        v9 clinical-input schema.
        """
        if format != "json":
            raise ValueError(f"unsupported report format: {format}")
        try:
            data = json.loads(file_content)
            biomarkers = data.get("biomarkers", {})
            variants = data.get("variants", [])
            cna_in = data.get("cnv") or data.get("cna") or {}
            fusions_in = data.get("fusions", [])

            tmb_val = biomarkers.get("tmb")
            driver_variants = [v.get("gene") for v in variants if v.get("gene")]
            # Keep the protein-level change per variant — the predictor's
            # variant-specific therapy matching (e.g. BRAF V600E) needs it;
            # dropping "alteration" made that path unreachable for reports.
            mutation_details = []
            for v in variants:
                if not v.get("gene"):
                    continue
                pc = str(v.get("alteration") or v.get("protein_change")
                         or v.get("hgvsp") or "")
                if pc.startswith("p."):
                    pc = pc[2:]
                mutation_details.append({"gene": v["gene"],
                                         "protein_change": pc})
            msi = biomarkers.get("msi") or biomarkers.get("msi_status") or ""

            cna = {}
            for k, v in cna_in.items():
                if isinstance(v, str):
                    cna[k] = {"amplification": 2, "amp": 2, "gain": 1,
                              "deletion": -2, "deep_deletion": -2, "del": -2,
                              "loss": -1}.get(v.lower(), 0)
                else:
                    cna[k] = int(v)

            sv_count = biomarkers.get("sv_count")
            if sv_count is None and fusions_in:
                sv_count = len(fusions_in) + int(biomarkers.get("sv_other", 0))

            return {
                "cancer_type": data.get("cancer_type") or data.get("tumor_type"),
                "stage": data.get("stage"),
                "age_at_diagnosis": data.get("age") or biomarkers.get("age"),
                "sex": data.get("sex"),
                "tmb": tmb_val,
                "hr_deficiency": "present" if str(biomarkers.get("hrd_status", "")).lower() in
                                 ("positive", "present", "1") else "absent",
                # Shared spelling family with the corpus path — covers
                # 'MSI-H', 'MSI-High', 'Instable', 'MSS', 'MSI-L', ...
                "msi_type": normalize_msi_type(msi),
                "msi_score": biomarkers.get("msi_score"),
                "gene_mutations": driver_variants,
                "mutation_details": mutation_details,
                "cna": cna,
                "fusions": fusions_in,
                "sv_count": sv_count,
                "tumor_purity": biomarkers.get("purity"),
                # signature_1_weight is a 0-100 class fraction — encode as a
                # direct fraction, not a count (a lone count reads as 100% C>T).
                "spectrum_fractions": (
                    {"C>T": float(biomarkers["signature_1_weight"]) / 100.0}
                    if biomarkers.get("signature_1_weight") is not None else None),
                "detected_variants": driver_variants,
            }
        except Exception as e:
            raise ValueError(f"Failed to parse genomic report: {str(e)}")

    @staticmethod
    def ingest_ehr_patient(patient_id: str) -> Dict[str, Any]:
        """
        Bi-directional EHR bridge. Pulls the patient's normalized clinical
        record from the sequenced corpus (MSK-IMPACT + MSK-CHORD); falls back
        to the legacy mock cohort for demo IDs.
        """
        rec = _lookup_corpus_patient(patient_id)
        if rec:
            return rec
        MOCK_EHR_DB = {
            "PX-9921": {"name": "Sarah Connor", "age_at_diagnosis": 42, "cancer_type": "breast",
                        "stage": "IV", "hr_deficiency": "present",
                        "gene_mutations": ["ERBB2"], "cna": {"ERBB2": 2},
                        "detected_variants": ["HER2+"], "tmb": 8.0},
            "PX-8812": {"name": "James Howlett", "age_at_diagnosis": 61, "cancer_type": "lung",
                        "stage": "III", "gene_mutations": ["EGFR", "TP53"],
                        "cna": {"MET": 2}, "detected_variants": ["EGFR"], "tmb": 6.0},
            "PX-7743": {"name": "Bruce Wayne", "age_at_diagnosis": 48, "cancer_type": "prostate",
                        "stage": "IV", "hr_deficiency": "present",
                        "gene_mutations": ["BRCA2"], "cna": {"BRCA2": -2},
                        "detected_variants": ["BRCA1/2"], "tmb": 4.0},
            "PX-6654": {"name": "Diana Prince", "age_at_diagnosis": 52, "cancer_type": "ovarian",
                        "stage": "III", "hr_deficiency": "present",
                        "gene_mutations": ["BRCA1"], "detected_variants": ["BRCA_Mutant"], "tmb": 3.5},
            "PX-5565": {"name": "Clark Kent", "age_at_diagnosis": 35, "cancer_type": "colorectal",
                        "stage": "IV", "gene_mutations": ["BRAF", "APC", "TP53"],
                        "detected_variants": ["BRAF_V600E"], "tmb": 5.0},
            "PX-3387": {"name": "Barry Allen", "age_at_diagnosis": 29, "cancer_type": "lung",
                        "stage": "IV", "gene_mutations": ["TP53"],
                        "fusions": [{"gene1": "EML4", "gene2": "ALK", "sv_class": "INVERSION"}],
                        "detected_variants": ["ALK"], "tmb": 3.0},
            "PX-1109": {"name": "Hal Jordan", "age_at_diagnosis": 38, "cancer_type": "colorectal",
                        "stage": "III", "gene_mutations": ["POLE", "APC", "TP53", "PIK3CA"],
                        "msi_type": "Unstable", "detected_variants": ["TMB-H"], "tmb": 120.0},
            "PX-0010": {"name": "Selina Kyle", "age_at_diagnosis": 34, "cancer_type": "breast",
                        "stage": "II", "hr_deficiency": "present",
                        "gene_mutations": ["BRCA1", "TP53"], "tmb": 4.5},
        }
        rec = dict(MOCK_EHR_DB.get(patient_id, {"name": "Unknown", "age_at_diagnosis": 50,
                                                "cancer_type": "lung", "stage": "II"}))
        rec.setdefault("cancer_type_canonical",
                       canonical_cancer_type(rec.get("cancer_type")))
        # Mock records name patients under "name"; the UI displays
        # "patient_name" (same key the corpus path uses) — alias it so demo
        # patients aren't rendered as bare ids. Every ingested record also
        # carries its own id so downstream consumers (e.g. the digital-twin
        # self-exclusion) don't depend on the caller re-attaching it.
        rec.setdefault("patient_name", rec.get("name"))
        rec.setdefault("patient_id", patient_id)
        return rec


_corpus_index: Optional[Dict[str, Dict[str, Any]]] = None
_bare_index: Optional[Dict[str, List[str]]] = None


def _build_corpus_indices():
    """uid -> record index plus a bare-id -> uids ambiguity map.

    MSK-IMPACT and MSK-CHORD share the same P-XXXXXXX namespace (~4.2k
    patients and ~4.2k samples collide), so a bare id does NOT identify a
    unique patient — callers must pass the cohort-qualified uid.
    """
    idx, bare = {}, {}
    for r in load_records():
        for raw, uid in ((r["patient_id"], record_uid(r)),
                         (r["sample_id"], record_sample_uid(r))):
            idx[uid] = r
            bare.setdefault(raw, set()).add(uid)
    return idx, bare


def _lookup_corpus_patient(patient_id: str) -> Optional[Dict[str, Any]]:
    """Direct clinical-input lookup by cohort-qualified uid ("chord:P-0001234").

    Bare ids are honored only when unambiguous: an id present in both
    cohorts is two different patients, and guessing would misattribute a
    real patient's record — those return None so the caller falls back to
    the clearly-marked mock patient instead.

    Shares the process-wide `corpus.load_records` cache — the JSONL is parsed
    once per process regardless of how many engines consume it.
    """
    global _corpus_index, _bare_index
    if _corpus_index is None:
        _corpus_index, _bare_index = _build_corpus_indices()
    if ":" in patient_id:
        rec = _corpus_index.get(patient_id)
    else:
        uids = _bare_index.get(patient_id, [])
        # uids is a SET (built by _build_corpus_indices) — index it via
        # next(iter()); uids[0] raises TypeError on every unambiguous id.
        rec = _corpus_index[next(iter(uids))] if len(uids) == 1 else None
    if not rec:
        return None
    ci = rec["clinical_input"]
    out = dict(ci)
    out["patient_id"] = record_uid(rec)
    out["patient_name"] = f"{rec['patient_id']} ({rec['cohort']})"
    out["detected_variants"] = list(ci.get("gene_mutations") or [])
    out["display"] = rec.get("display", {})
    out["os_months"] = rec.get("os_months")
    out["os_status"] = rec.get("os_status")
    out["tx_agents"] = rec.get("tx_agents", [])
    return out


class CaseQueueManager:
    """Manages the clinical worklist/queue for Tumor Boards."""

    def __init__(self, queue_file: str = None, records_path: str = None):
        if queue_file is None:
            queue_file = os.path.join(
                os.environ.get("RESISTANCEAI_MODEL_DIR", "backend/artifacts"),
                "case_queue.json")
        if records_path is None:
            records_path = data_path("patient_records.jsonl")
        self.queue_file = queue_file
        self.records_path = records_path
        self.queue = self._load_queue()

    def _load_queue(self) -> List[Dict[str, Any]]:
        """Curated queue: a biomarker-diverse slice of the real corpus,
        with the legacy demo patients pinned at the top.

        If a queue was previously persisted via add_case(), the file is the
        source of truth — otherwise the curated default is regenerated."""
        if os.path.exists(self.queue_file):
            try:
                with open(self.queue_file) as f:
                    saved = json.load(f)
                if isinstance(saved, list):
                    return saved
            except (json.JSONDecodeError, OSError) as e:
                print(f"Case queue file unreadable ({e}) — regenerating default")
        queue = self._corpus_queue()
        queue.extend([
            {"id": "PX-9921", "status": "Genomics Ready", "priority": "High", "site": "Breast (HER2+)"},
            {"id": "PX-8812", "status": "Board Pending", "priority": "High", "site": "Lung (EGFR+MET amp)"},
            {"id": "PX-7743", "status": "New Case", "priority": "Critical", "site": "Prostate (BRCA2)"},
            {"id": "PX-6654", "status": "Genomics Ready", "priority": "Medium", "site": "Ovarian (BRCA1)"},
            {"id": "PX-5565", "status": "Follow-up", "priority": "Low", "site": "CRC (BRAF+)"},
            {"id": "PX-3387", "status": "In Analysis", "priority": "High", "site": "Lung (ALK fusion)"},
            {"id": "PX-1109", "status": "Board Pending", "priority": "Critical", "site": "CRC (POLE/MSI-H)"},
            {"id": "PX-0010", "status": "New Case", "priority": "Medium", "site": "Breast (HRD+)"},
        ])
        return queue

    def _corpus_queue(self, n_per_site: int = 4) -> List[Dict[str, Any]]:
        """Pick biomarker-diverse real patients for the worklist.

        Status/priority are derived from the record's own data — nothing is
        fabricated: every listed case is sequenced ('Genomics Ready'), and
        stage-IV cases are surfaced as higher priority for board triage.
        """
        if not os.path.exists(self.records_path):
            return []
        picks = {}
        try:
            for r in load_records(self.records_path):
                ci = r["clinical_input"]
                if r["resistant"] is None or not ci.get("gene_mutations"):
                    continue
                site = ci["cancer_type_canonical"]
                if site == "other":
                    continue
                drivers = [g for g in ci["gene_mutations"]
                           if g in ("EGFR", "KRAS", "BRAF", "ERBB2", "BRCA1", "BRCA2",
                                    "ALK", "MET", "PIK3CA", "POLE", "MSH2", "RET",
                                    "NTRK1", "FGFR2", "IDH1", "ESR1", "AR")]
                score = len(drivers) + (1 if (ci.get("tmb") or 0) > 15 else 0)
                picks.setdefault(site, []).append((score, r))
            queue = []
            for site, lst in picks.items():
                lst.sort(key=lambda x: -x[0])
                for score, r in lst[:n_per_site]:
                    ci = r["clinical_input"]
                    queue.append({
                        # cohort-qualified uid — bare pids collide across
                        # IMPACT/CHORD, so the queue must carry the cohort.
                        "id": record_uid(r),
                        "pid": r["patient_id"],
                        "cohort": r["cohort"],
                        "status": "Genomics Ready",
                        "priority": "Critical" if ci.get("stage") == "IV"
                                    else "High",
                        "site": f"{site.title()} ({','.join(ci['gene_mutations'][:3])})",
                        "_real": True,
                    })
            return queue
        except Exception as e:
            print(f"Corpus queue build failed: {e}")
            return []

    def add_case(self, case_data: Dict[str, Any]):
        self.queue.append(case_data)
        self._save_queue()

    def _save_queue(self):
        # tmp + atomic rename, matching InstitutionalDB's ledger writes —
        # readers never see a torn file.
        os.makedirs(os.path.dirname(self.queue_file), exist_ok=True)
        tmp = self.queue_file + ".tmp"
        with open(tmp, 'w') as f:
            json.dump(self.queue, f, indent=4)
        os.replace(tmp, self.queue_file)
