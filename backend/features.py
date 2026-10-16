"""
Shared clinical-input schema and model feature builder for ResistanceAI v9.

Every data source (MSK-IMPACT, MSK-CHORD, uploaded NGS reports, mock EHR)
normalizes into a single "clinical input" dict. `build_model_vector` maps that
dict to the fixed numeric feature vector used by the trained model — identical
code path at train time and inference time.
"""

from typing import Dict, Any, Optional
import re
import numpy as np

# ---------------------------------------------------------------------------
# Canonical cancer types
# ---------------------------------------------------------------------------

CANONICAL_TYPES = [
    "lung", "breast", "colorectal", "prostate", "ovarian", "melanoma",
    "pancreatic", "bladder", "renal", "cns", "esophagogastric", "endometrial",
    "sarcoma", "head_neck", "hepatobiliary", "thyroid", "cervical",
    "mesothelioma", "other",
]

_CANCER_TYPE_RULES = [
    ("lung", ["non-small cell lung", "small cell lung", "nsclc", "sclc", "lung"]),
    ("breast", ["breast", "tnbc"]),
    ("colorectal", ["colorectal", "colon", "rectal", "appendiceal", "anal", "crc"]),
    ("prostate", ["prostate"]),
    ("ovarian", ["ovarian", "fallopian", "peritoneal"]),
    ("melanoma", ["melanoma"]),
    ("pancreatic", ["pancreatic", "pdac"]),
    ("bladder", ["bladder", "urothelial"]),
    ("renal", ["renal", "kidney", "rcc"]),
    ("cns", ["glioma", "glioblastoma", "gbm", "cns", "brain", "embryonal", "medulloblastoma",
             "neuroblastoma", "meningioma", "ependymoma", "astrocytoma"]),
    ("esophagogastric", ["esophagogastric", "esophageal", "gastric", "stomach",
                         "small bowel", "ampullary", "escc"]),
    ("endometrial", ["endometrial", "uterine"]),
    ("sarcoma", ["sarcoma", "gastrointestinal stromal", "gist", "bone", "soft tissue"]),
    ("head_neck", ["head and neck", "salivary", "nasopharyn", "oral", "laryngeal",
                   "sinonasal", "adrenocortical", "hnscc"]),
    ("hepatobiliary", ["hepato", "cholangio", "biliary", "gallbladder", "liver", "hcc"]),
    ("thyroid", ["thyroid"]),
    ("cervical", ["cervical"]),
    ("mesothelioma", ["mesothelioma"]),
]


def canonical_cancer_type(raw: str) -> str:
    """Map free-text cBioPortal CANCER_TYPE to canonical key."""
    s = str(raw or "").lower()
    for canon, needles in _CANCER_TYPE_RULES:
        if any(n in s for n in needles):
            return canon
    return "other"


# ---------------------------------------------------------------------------
# Genomic vocabularies
# ---------------------------------------------------------------------------

# ~90 clinically salient genes -> binary mutation features
DRIVER_GENES = [
    "EGFR", "KRAS", "NRAS", "HRAS", "BRAF", "ARAF", "RAF1", "MAP2K1", "NF1",
    "PIK3CA", "PIK3R1", "AKT1", "MTOR", "RICTOR", "PTEN", "TSC1", "TSC2",
    "ERBB2", "ERBB3", "MET", "ALK", "ROS1", "RET", "FGFR1", "FGFR2", "FGFR3",
    "KIT", "PDGFRA", "NTRK1", "NTRK2", "NTRK3", "NRG1",
    "TP53", "RB1", "APC", "CDKN2A", "CDKN2B", "SMAD4", "VHL", "FH",
    "STK11", "KEAP1", "NFE2L2", "B2M", "JAK1", "JAK2",
    "CCND1", "CCNE1", "CDK4", "CDK6", "MDM2", "MDM4",
    "ESR1", "AR", "PGR", "SPOP", "FOXA1", "GATA3",
    "BRCA1", "BRCA2", "PALB2", "ATM", "ATR", "CHEK2", "RAD51C", "RAD51D",
    "BARD1", "BRIP1", "FANCA", "MLH1", "MSH2", "MSH6", "PMS2", "POLE", "POLD1",
    "ARID1A", "ARID1B", "SMARCA4", "SMARCB1", "KMT2C", "KMT2D", "CREBBP",
    "EP300", "EZH2", "IDH1", "IDH2", "DNMT3A", "TET2", "ASXL1", "TERT",
    "NOTCH1", "FBXW7", "CTNNB1", "AXIN1", "RNF43", "SOX9",
    "MYC", "MYCN", "PBRM1", "SETD2", "BAP1", "KDM5C", "GNAS", "SMO",
    "FLT3", "CDK12", "FAT1", "NOTCH2", "KDM6A", "RHOA", "RUNX1", "WT1",
]

HRD_GENES = ["BRCA1", "BRCA2", "PALB2", "ATM", "ATR", "CHEK1", "CHEK2",
             "RAD51C", "RAD51D", "BARD1", "BRIP1", "FANCA", "FANCC", "CDK12"]
MMR_GENES = ["MLH1", "MSH2", "MSH6", "PMS2"]
IMMUNE_RESISTANCE_GENES = ["STK11", "KEAP1", "B2M", "JAK1", "JAK2", "PBRM1", "PTEN"]

PATHWAYS = {
    "rtk_ras": ["EGFR", "ERBB2", "ERBB3", "ERBB4", "MET", "FGFR1", "FGFR2",
                "FGFR3", "FGFR4", "ALK", "ROS1", "RET", "NTRK1", "NTRK2", "NTRK3",
                "KIT", "PDGFRA", "KRAS", "NRAS", "HRAS", "BRAF", "RAF1", "ARAF",
                "NF1", "PTPN11", "MAP2K1", "SOS1"],
    "pi3k_mtor": ["PIK3CA", "PIK3R1", "AKT1", "AKT2", "AKT3", "MTOR", "RICTOR",
                  "PTEN", "TSC1", "TSC2", "INPP4B", "STK11"],
    "cell_cycle": ["CDK4", "CDK6", "CCND1", "CCND2", "CCND3", "CCNE1", "RB1",
                   "CDKN2A", "CDKN2B", "CDKN1A", "CDKN1B", "E2F3"],
    "ddr_hrd": HRD_GENES + ["PARP1", "PARP2"],
    "tp53": ["TP53", "MDM2", "MDM4", "ATM"],
    "wnt": ["APC", "CTNNB1", "AXIN1", "AXIN2", "RNF43", "SOX9", "TCF7L2", "RSPO3"],
    "notch": ["NOTCH1", "NOTCH2", "NOTCH3", "NOTCH4", "FBXW7", "JAG1", "DLL3"],
    "chromatin": ["ARID1A", "ARID1B", "ARID2", "SMARCA4", "SMARCB1", "KMT2A",
                  "KMT2B", "KMT2C", "KMT2D", "EP300", "CREBBP", "EZH2", "SETD2",
                  "KDM6A", "DNMT3A", "TET2", "IDH1", "IDH2", "ASXL1"],
    "immune_evasion": ["STK11", "KEAP1", "B2M", "JAK1", "JAK2", "CD274", "PDCD1LG2",
                       "PBRM1", "PTEN", "CTLA4", "VTCN1"],
    "hormone": ["AR", "ESR1", "PGR", "FOXA1", "GATA3", "NCOR1", "CYP19A1"],
}

# CNA events with direct clinical meaning -> dedicated flags
CNA_FLAG_GENES = {
    "MYC": "amp", "MYCN": "amp", "ERBB2": "amp", "EGFR": "amp", "MET": "amp",
    "CCND1": "amp", "CCNE1": "amp", "CDK4": "amp", "CDK6": "amp", "MDM2": "amp",
    "FGFR1": "amp", "FGFR2": "amp", "KRAS": "amp", "BRAF": "amp", "AR": "amp",
    "CD274": "amp", "AKT1": "amp",
    "CDKN2A": "del", "CDKN2B": "del", "PTEN": "del", "RB1": "del",
    "BRCA1": "del", "BRCA2": "del", "ATM": "del", "TP53": "del", "NF1": "del",
    "SMAD4": "del", "APC": "del", "PBRM1": "del", "STK11": "del", "KEAP1": "del",
    "B2M": "del",
}

FUSION_GENES = {"ALK", "ROS1", "RET", "NTRK1", "NTRK2", "NTRK3", "FGFR2", "FGFR3",
                "MET", "BRAF", "RAF1", "NRG1", "TMPRSS2", "EWSR1", "BCR", "ABL1",
                "RSPO2", "RSPO3"}

ONCOGENES_FOR_CNA = {g for g, kind in CNA_FLAG_GENES.items() if kind == "amp"}
TSG_FOR_CNA = {g for g, kind in CNA_FLAG_GENES.items() if kind == "del"}


def fusion_gene_set(fusions) -> set:
    """Normalize a fusion payload -> set of partner gene symbols.

    Accepts both representations used across the codebase:
      * dicts   {"gene1": "EML4", "gene2": "ALK"}  (corpus / cBioPortal style)
      * strings "EML4-ALK" or "EML4_ALK"           (API / report style)
    """
    genes = set()
    for fz in fusions or []:
        if isinstance(fz, dict):
            genes.update([fz.get("gene1", ""), fz.get("gene2", "")])
        elif isinstance(fz, str):
            genes.update(fz.replace("_", "-").split("-"))
    genes.discard("")
    genes.discard(None)
    return genes


def is_msi_unstable(value) -> bool:
    """True for any spelling of MSI-high used across our data sources.

    MSK-CHORD ships the value 'Instable'; NGS reports and API payloads
    typically send 'Unstable', 'MSI-H' or 'MSI-High'. Matching the family of
    spellings keeps the feature consistent between corpus records and
    uploaded reports — a startswith('unstable') check alone silently misses
    every real MSI-H patient in the corpus.
    """
    s = str(value or "").strip().lower()
    return s.startswith(("unstable", "instable", "msi-h", "msih", "high"))


def normalize_msi_type(value) -> Optional[str]:
    """Normalize an MSI status string to 'Unstable' | 'Stable' | None.

    One spelling family shared by every ingestion path — the CHORD corpus
    ships 'Instable', NGS reports send 'MSI-H'/'MSI-High'/'Unstable', and
    stable variants arrive as 'Stable', 'MSS', 'MSI-L' or 'Low'. Anything
    else (unknown / not reported) returns None so the msi_unstable feature
    falls back to MMR-gene / hypermutation evidence instead of guessing.
    """
    s = str(value or "").strip().lower()
    if is_msi_unstable(s):
        return "Unstable"
    if s.startswith(("stable", "mss", "msi-l", "msi-s", "low")):
        return "Stable"
    return None

NUMERIC_FEATURES = [
    "age_at_diagnosis", "tmb_log", "n_mut", "frac_ct", "frac_ca", "frac_cg",
    "frac_tc", "frac_ta", "frac_tg", "n_indel_frac", "fga", "n_amp", "n_deepdel",
    "sv_count", "tumor_purity", "msi_score", "stage_ord", "is_metastatic",
    "sex_male", "smoking_ever", "driver_alt_count",
] + [f"pathway_{k}" for k in PATHWAYS]

BINARY_FEATURES = (
    [f"mut_{g}" for g in DRIVER_GENES]
    + [f"cna_{g}_{k}" for g, k in sorted(CNA_FLAG_GENES.items())]
    + ["fusion_any", "fusion_rtk", "hrd_present", "mmr_deficient", "pole_mut",
       "msi_unstable", "immune_evasion_alt"]
)

CATEGORICAL_ONEHOT = {"cancer_type": CANONICAL_TYPES}
FEATURE_NAMES = (
    NUMERIC_FEATURES + BINARY_FEATURES + [f"ct_{c}" for c in CANONICAL_TYPES]
)


# ---------------------------------------------------------------------------
# Feature builder
# ---------------------------------------------------------------------------

_SPEC_KEYS = ["C>T", "C>A", "C>G", "T>C", "T>A", "T>G"]


def _spec(rec: Dict[str, Any]) -> Dict[str, float]:
    """Six-class substitution spectrum fractions (from raw class counts)."""
    spec = rec.get("substitution_spectrum") or {}
    # Only the six modeled classes count toward the total — a stray key
    # (e.g. an indel class) would otherwise dilute every fraction.
    total = sum(spec.get(k, 0) for k in _SPEC_KEYS
                if isinstance(spec.get(k), (int, float)))
    out = {}
    for k in _SPEC_KEYS:
        out[k] = (spec.get(k, 0) / total) if total else 0.0
    return out


def build_model_vector(rec: Dict[str, Any], medians: Optional[Dict[str, float]] = None) -> Dict[str, float]:
    """Map a normalized clinical input record to the fixed model feature vector.

    Missing numeric values fall back to `medians` (population values saved at
    train time) so partial NGS reports still produce sane vectors.
    """
    medians = medians or {}
    feats: Dict[str, float] = {}

    muts = set(rec.get("gene_mutations") or [])
    cna = rec.get("cna") or {}
    fusions = rec.get("fusions") or []
    spec = _spec(rec)
    # Precedence for the six-class fractions:
    #   1. substitution_spectrum (raw counts, normalized here)
    #   2. spectrum_fractions    (direct 0-1 fractions, e.g. from report weights)
    #   3. population medians    (no spectrum information at all)
    fracs_in = rec.get("spectrum_fractions") or {}
    has_spec = any(v > 0 for v in spec.values())

    tmb = rec.get("tmb")
    feats["tmb_log"] = float(np.log1p(tmb)) if tmb is not None else medians.get("tmb_log", 1.6)
    feats["age_at_diagnosis"] = _num(rec, "age_at_diagnosis", medians, 62.0)
    feats["n_mut"] = _num(rec, "n_mut", medians, max(len(muts), 4))
    for key, name in [("C>T", "frac_ct"), ("C>A", "frac_ca"), ("C>G", "frac_cg"),
                      ("T>C", "frac_tc"), ("T>A", "frac_ta"), ("T>G", "frac_tg")]:
        if has_spec:
            feats[name] = spec[key]
        elif isinstance(fracs_in.get(key), (int, float)):
            feats[name] = float(min(max(fracs_in[key], 0.0), 1.0))
        else:
            feats[name] = medians.get(name, 0.12)
    feats["n_indel_frac"] = _num(rec, "n_indel_frac", medians, 0.1)
    feats["fga"] = _num(rec, "fga", medians, 0.25)
    feats["n_amp"] = _num(rec, "n_amp", medians, 2.0)
    feats["n_deepdel"] = _num(rec, "n_deepdel", medians, 2.0)
    feats["sv_count"] = _num(rec, "sv_count", medians, len(fusions))
    feats["tumor_purity"] = _num(rec, "tumor_purity", medians, 50.0)
    feats["msi_score"] = _num(rec, "msi_score", medians, 3.0)

    stage_map = {"I": 1, "II": 2, "III": 3, "IV": 4, "STAGE 1-3": 2, "STAGE 4": 4}
    stage_raw = str(rec.get("stage", "")).upper().strip()
    feats["stage_ord"] = float(stage_map.get(stage_raw, medians.get("stage_ord", 3.0)))
    st = str(rec.get("sample_type", "")).lower()
    feats["is_metastatic"] = 1.0 if ("metast" in st or stage_raw == "IV" or stage_raw == "STAGE 4") else 0.0
    feats["sex_male"] = 1.0 if str(rec.get("sex", "")).lower().startswith("m") else 0.0
    smk = str(rec.get("smoking_history", "")).lower()
    # Token matching, not substring: "ever" is a substring of "never" — a
    # substring check codes every never-smoker as an ever-smoker, and misses
    # CHORD's "Prev/Curr Smoker" label entirely (actual smokers coded 0).
    smk_tokens = set(re.findall(r"[a-z]+", smk))
    never = bool(smk_tokens & {"never", "non", "none"})
    ever = bool(smk_tokens & {"current", "former", "prev", "curr", "ever",
                              "heavy", "light", "smoker", "smoking", "ex",
                              "quit", "yes"})
    feats["smoking_ever"] = 1.0 if (ever and not never) else 0.0

    hrd_present = bool(muts & set(HRD_GENES)) or any(cna.get(g, 0) <= -2 for g in ["BRCA1", "BRCA2", "ATM"])
    if rec.get("hr_deficiency") == "present":
        hrd_present = True
    mmr_def = bool(muts & set(MMR_GENES))
    pole_mut = "POLE" in muts
    msi_unstable = is_msi_unstable(rec.get("msi_type")) or mmr_def or \
        (tmb is not None and tmb >= 40 and pole_mut)

    feats["hrd_present"] = float(hrd_present)
    feats["mmr_deficient"] = float(mmr_def)
    feats["pole_mut"] = float(pole_mut)
    feats["msi_unstable"] = float(msi_unstable)
    feats["immune_evasion_alt"] = float(bool(muts & set(IMMUNE_RESISTANCE_GENES)) or
                                        cna.get("CD274", 0) >= 2 or cna.get("B2M", 0) <= -2)

    for g in DRIVER_GENES:
        feats[f"mut_{g}"] = 1.0 if g in muts else 0.0
    for g, kind in sorted(CNA_FLAG_GENES.items()):
        v = cna.get(g, 0)
        feats[f"cna_{g}_{kind}"] = 1.0 if (v >= 2 if kind == "amp" else v <= -2) else 0.0

    fusion_pairs = fusion_gene_set(fusions)
    feats["fusion_any"] = 1.0 if fusion_pairs else 0.0
    feats["fusion_rtk"] = 1.0 if (fusion_pairs & FUSION_GENES) else 0.0

    alt_genes = set(muts)
    for g, v in cna.items():
        if g in ONCOGENES_FOR_CNA and v >= 2:
            alt_genes.add(g)
        elif g in TSG_FOR_CNA and v <= -2:
            alt_genes.add(g)
    feats["driver_alt_count"] = float(len(alt_genes & set(DRIVER_GENES)))

    for pw, genes in PATHWAYS.items():
        altered = len(alt_genes & set(genes))
        feats[f"pathway_{pw}"] = altered / len(genes)

    canon = rec.get("cancer_type_canonical") or canonical_cancer_type(rec.get("cancer_type"))
    for c in CANONICAL_TYPES:
        feats[f"ct_{c}"] = 1.0 if canon == c else 0.0

    return feats


def _num(rec, key, medians, default):
    v = rec.get(key)
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return float(medians.get(key, default))
    return float(v)


# ---------------------------------------------------------------------------
# Clinical-input normalization
# ---------------------------------------------------------------------------

# Amino-acid-change suffix for "GENE-PROTEIN" report labels ("BRAF-V600E",
# "KRAS-G12C", "TP53-A138Cfs*27"). Deliberately strict so true fusions like
# "EML4-ALK", "BCR-ABL1" or "BCR-P2RY8" (partner names can contain digits)
# still take the fusion path.
_AA_CHANGE_RE = re.compile(
    r"[A-Z]\d+[A-Z*]?$"                     # V600E, G12C, W288*
    r"|[A-Z]\d+[A-Z*](?:fs|ins|del)\S*$"    # A138Cfs*27, K642Efs
    r"|[A-Z]\d+(?:fs|ins|del|=)\S*$")       # G12del, E545ins

# Legacy biomarker labels (v8 detected_variants payloads) -> v9 genomic events.
# Entries map to a (gene, optional_cna_call) so both feature vector and therapy
# matching see the underlying biology.
# Label tokens that look like gene symbols but aren't — prevents biomarker
# strings such as "PD_L1" or "TMB_H" from being parsed as fusion pairs.
_NON_GENE_TOKENS = {"TMB", "MSI", "MSS", "HRD", "PDL1", "PD", "L1", "GEP",
                    "LOH", "FGA", "SIGNATURE", "HIGH", "LOW", "POSITIVE",
                    "NEGATIVE", "WT", "MUT", "AMP", "DEL", "NA"}

# Suffixes on "GENE_SUFFIX" report labels that denote copy-number events,
# not fusion partners ("MYC_AMP", "CDKN2A_LOSS", "PTEN_DEL").
_CNA_SUFFIXES = {"AMP": 2, "AMPLIFICATION": 2, "GAIN": 1,
                 "DEL": -2, "DELETION": -2, "LOSS": -2}

LEGACY_VARIANT_MAP = {
    "HER2+": ("ERBB2", 2), "HER2": ("ERBB2", 2),
    "EGFR": ("EGFR", None), "KRAS": ("KRAS", None), "KRAS_G12C": ("KRAS", None),
    "ALK": ("ALK", None), "ROS1": ("ROS1", None), "RET": ("RET", None),
    "MET": ("MET", None), "BRAF": ("BRAF", None), "BRAF_V600": ("BRAF", None),
    "BRAF_V600E": ("BRAF", None), "NRAS": ("NRAS", None), "KIT": ("KIT", None),
    "PIK3CA": ("PIK3CA", None), "PTEN": ("PTEN", None),
    "PTEN_Loss": ("PTEN", -2), "BRCA1": ("BRCA1", None), "BRCA2": ("BRCA2", None),
    "BRCA_Mutant": ("BRCA1", None), "BRCA1/2": ("BRCA2", None),
    "IDH1": ("IDH1", None), "IDH2": ("IDH2", None), "FGFR2": ("FGFR2", None),
    "FGFR3": ("FGFR3", None), "POLE": ("POLE", None), "ERBB2": ("ERBB2", None),
    "STK11": ("STK11", None), "KEAP1": ("KEAP1", None), "TP53": ("TP53", None),
    "AR": ("AR", None), "ESR1": ("ESR1", None), "NF1": ("NF1", None),
    "MSI-H": (None, None), "TMB-H": (None, None), "HRD_Positive": (None, None),
}


def normalize_clinical_input(d: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a clinical input payload to the v9 schema.

    Any v9-schema field supplied is honored as-is; legacy v8 fields
    (tmb_level, ct_transition_pct, structural_variant_burden,
    detected_variants labels) are additionally mapped onto the same
    schema, so mixed payloads lose no signal.

    Every model-facing consumer (predictor, digital twin, cohort tooling)
    must run inputs through this so train/serve/retrieve see identical
    normalization.
    """
    ci = dict(d)

    # --- legacy scalar mappings (only fill values the caller didn't give)
    tmb_map = {"tmb_1": 3.0, "tmb_2": 7.5, "tmb_3": 15.0, "tmb_4": 30.0}
    if ci.get("tmb") is None and d.get("tmb_level") in tmb_map:
        ci["tmb"] = tmb_map[d["tmb_level"]]
    if ci.get("substitution_spectrum") is None and \
            ci.get("spectrum_fractions") is None and \
            d.get("ct_transition_pct") is not None:
        # legacy field was a 0-100 C>T percentage — encode as a direct
        # fraction, not a count (a single-class count would read as 100%).
        ci["spectrum_fractions"] = {"C>T": float(d["ct_transition_pct"]) / 100.0}
    svb = d.get("structural_variant_burden")
    if svb in ("high", "low"):
        fill = {"high": (8.0, 6.0, 15.0), "low": (0.0, 0.0, 1.0)}[svb]
        for key, val in zip(("n_amp", "n_deepdel", "sv_count"), fill):
            if ci.get(key) is None:
                ci[key] = val

    # --- legacy biomarker labels -> genomic events
    raw_variants = [v for v in d.get("detected_variants", [])
                    if isinstance(v, str)]
    if raw_variants:
        genes = list(ci.get("gene_mutations") or [])
        cna = dict(ci.get("cna") or {})
        fusions = list(ci.get("fusions") or [])
        for v in raw_variants:
            if v in LEGACY_VARIANT_MAP:
                gene, call = LEGACY_VARIANT_MAP[v]
                if gene and call is not None:
                    # CNA-level label (HER2+, PTEN_Loss) — record the
                    # copy-number event without fabricating a mutation
                    if gene not in cna:
                        cna[gene] = call
                elif gene and gene not in genes:
                    genes.append(gene)
                # mapped labels with no gene (MSI-H/TMB-H/HRD_Positive)
                # are handled below — never treated as gene symbols
            elif "-" in v:
                left, _, right = v.partition("-")
                if re.fullmatch(_AA_CHANGE_RE, right):
                    # "BRAF-V600E" style protein-change label -> mutation
                    # on the left-hand gene, not a fusion pair.
                    if left and left.upper() not in _NON_GENE_TOKENS and \
                            left not in genes:
                        genes.append(left)
                elif left.upper() not in _NON_GENE_TOKENS and \
                        right.upper() not in _NON_GENE_TOKENS and v not in fusions:
                    # "EML4-ALK" style label -> fusion event, not a mutation.
                    # The token guards stop "PD-L1"/"HER2-AMP" biomarker labels
                    # from fabricating gene symbols or fusion pairs.
                    fusions.append(v)
            elif "_" in v:
                parts = v.split("_")
                suffix = parts[-1].upper()
                if len(parts) == 2 and parts[0] and \
                        parts[0].upper() not in _NON_GENE_TOKENS and \
                        suffix in _CNA_SUFFIXES:
                    # "MYC_AMP"/"CDKN2A_LOSS" style label -> copy-number
                    # event on the left-hand gene (same convention as
                    # PTEN_Loss in LEGACY_VARIANT_MAP).
                    if parts[0] not in cna:
                        cna[parts[0]] = _CNA_SUFFIXES[suffix]
                elif len(parts) == 2 and parts[0] and \
                        parts[0].upper() not in _NON_GENE_TOKENS and \
                        (re.fullmatch(_AA_CHANGE_RE, parts[1]) or
                         re.fullmatch(r"EXON\d+\S*", suffix)):
                    # "TP53_R175H" style label -> mutation on the left-hand
                    # gene; "MET_EXON14"/"EGFR_EXON20INS" are exon-level
                    # alterations on that gene too, not fusion partners
                    # (the hyphenated branch only covers "GENE-AA").
                    if parts[0] not in genes:
                        genes.append(parts[0])
                elif parts[0].upper() not in _NON_GENE_TOKENS and \
                        parts[-1].upper() not in _NON_GENE_TOKENS and \
                        all(re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,11}", p)
                            for p in parts) and "-".join(parts) not in fusions:
                    # "EML4_ALK" style label -> fusion event. Non-gene
                    # biomarker/alteration tokens (PD_L1, TMB_H, X_DEL) are
                    # excluded on both sides so they can't fabricate a pair.
                    fusions.append("-".join(parts))
            elif "+" not in v and v not in genes:
                genes.append(v)
        ci["gene_mutations"] = genes
        if cna:
            ci["cna"] = cna
        if fusions:
            ci["fusions"] = fusions
        if "MSI-H" in raw_variants and not ci.get("msi_type"):
            ci["msi_type"] = "Unstable"
        if "TMB-H" in raw_variants and (ci.get("tmb") or 0) < 10:
            ci["tmb"] = 10.0
        if "HRD_Positive" in raw_variants and \
                ci.get("hr_deficiency") != "present":
            ci["hr_deficiency"] = "present"
        hints = list(ci.get("variant_hints") or [])
        hints += [v for v in raw_variants if v not in hints]
        ci["variant_hints"] = hints

    if not ci.get("sample_type"):
        ci["sample_type"] = "Metastasis" if str(
            ci.get("stage", "")).upper() in ("IV", "STAGE 4") else "Primary"
    ci["cancer_type_canonical"] = ci.get("cancer_type_canonical") or \
        canonical_cancer_type(ci.get("cancer_type"))
    return ci


def feature_display_name(fname: str) -> str:
    """Human-readable label for a model feature (dashboard explanations)."""
    if fname.startswith("mut_"):
        return f"{fname[4:]} mutation"
    if fname.startswith("cna_"):
        parts = fname.split("_")
        return f"{parts[1]} copy-number {'gain' if parts[2] == 'amp' else 'loss'}"
    if fname.startswith("pathway_"):
        return fname[8:].replace("_", "/").title() + " pathway"
    if fname.startswith("ct_"):
        return "Cancer type: " + fname[3:].replace("_", " ").title()
    if fname.startswith("frac_"):
        _cls = {"ct": "C>T", "ca": "C>A", "cg": "C>G",
                "tc": "T>C", "ta": "T>A", "tg": "T>G"}
        return "Substitution spectrum " + _cls.get(fname[5:], fname[5:].upper())
    names = {
        "age_at_diagnosis": "Age at diagnosis", "tmb_log": "Tumor mutational burden",
        "n_mut": "Mutation count", "n_indel_frac": "Indel fraction",
        "fga": "Fraction genome altered", "n_amp": "Amplification count",
        "n_deepdel": "Deep deletion count", "sv_count": "Structural variant count",
        "tumor_purity": "Tumor purity", "msi_score": "MSI score",
        "stage_ord": "Tumor stage", "is_metastatic": "Metastatic disease",
        "sex_male": "Sex", "smoking_ever": "Smoking history",
        "driver_alt_count": "Driver alteration count",
        "fusion_any": "Gene fusion", "fusion_rtk": "Actionable kinase fusion",
        "hrd_present": "HRD signature", "mmr_deficient": "MMR deficiency",
        "pole_mut": "POLE ultramutator", "msi_unstable": "MSI-High",
        "immune_evasion_alt": "Immune-evasion alterations",
    }
    return names.get(fname, fname)
