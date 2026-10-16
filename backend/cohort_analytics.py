"""
Pharma-grade cohort analytics: biomarker-defined cohort discovery over the
combined MSK-IMPACT + MSK-CHORD corpus (~35k sequenced patients).

Used by the Pharma Analytics tab for prevalence estimates, outcome
distributions, and KM stratification — the same questions a sponsor asks
when sizing a biomarker-selected trial.
"""

import numpy as np
from collections import Counter
from typing import Dict, Any

from .survival import kaplan_meier, median_survival
from .corpus import load_records, data_path, record_uid
from .features import is_msi_unstable, normalize_msi_type

RECORDS = data_path("patient_records.jsonl")

# Outcome statistics are suppressed below this cohort size: at n<5 an
# aggregate (median OS/TMB, KM curve, co-alteration list) is effectively a
# row-level record and would leak individual patient data.
MIN_COHORT_FOR_STATS = 5


class CohortAnalytics:
    def __init__(self, records_path=RECORDS):
        self.recs = []
        for r in load_records(records_path):
            ci = r["clinical_input"]
            self.recs.append({
                    "patient_id": r["patient_id"], "uid": record_uid(r),
                    "cohort": r["cohort"],
                    "cancer_type": ci["cancer_type_canonical"],
                    "stage": ci.get("stage"), "sample_type": ci.get("sample_type"),
                    "tmb": ci.get("tmb"), "msi_type": ci.get("msi_type"),
                    "genes": set(ci.get("gene_mutations") or []),
                    "amps": {g for g, v in (ci.get("cna") or {}).items() if v >= 2},
                    "dels": {g for g, v in (ci.get("cna") or {}).items() if v <= -2},
                    # HRD flag mirrors features.py: HRD-gene mutation OR deep
                    # deletion of a core HR gene (BRCA1/2, ATM).
                    "hrd": bool(set(ci.get("gene_mutations") or []) &
                              {"BRCA1", "BRCA2", "PALB2", "ATM", "RAD51C", "RAD51D"})
                              or any((ci.get("cna") or {}).get(g, 0) <= -2
                                     for g in ("BRCA1", "BRCA2", "ATM")),
                    "os_months": r["os_months"], "os_status": r["os_status"],
                    "resistant": r["resistant"], "label_source": r["label_source"],
                })
        self.n = len(self.recs)

    def query(self, cancer_types=None, genes=None, amps=None, dels=None,
              tmb_min=None, tmb_max=None, msi=None, stage_iv=False,
              hrd=None) -> Dict[str, Any]:
        sel = self.recs
        if cancer_types:
            sel = [r for r in sel if r["cancer_type"] in set(cancer_types)]
        if genes:
            sel = [r for r in sel if set(genes) <= r["genes"]]
        if amps:
            sel = [r for r in sel if set(amps) <= r["amps"]]
        if dels:
            sel = [r for r in sel if set(dels) <= r["dels"]]
        if tmb_min is not None:
            sel = [r for r in sel if r["tmb"] is not None and r["tmb"] >= tmb_min]
        if tmb_max is not None:
            sel = [r for r in sel if r["tmb"] is not None and r["tmb"] < tmb_max]
        if msi is not None:
            ms = str(msi).lower()
            if ms == "unstable":
                # corpus spelling is 'Instable' — match the family of
                # MSI-high spellings, not the literal 'unstable' prefix
                sel = [r for r in sel if is_msi_unstable(r["msi_type"])]
            elif ms == "stable":
                sel = [r for r in sel
                       if normalize_msi_type(r["msi_type"]) == "Stable"]
        if stage_iv:
            sel = [r for r in sel if r["stage"] == "IV"]
        if hrd is True:
            sel = [r for r in sel if r["hrd"]]
        elif hrd is False:
            # explicit False = HRD-negative cohort, not "no filter"
            sel = [r for r in sel if not r["hrd"]]
        return self._summarize(sel)

    def _summarize(self, sel) -> Dict[str, Any]:
        n = len(sel)
        base = {"n": n, "cohort_total": self.n,
                "prevalence_pct": (n / self.n * 100) if self.n else 0.0}
        if n < MIN_COHORT_FOR_STATS:
            # k-anonymity floor: counts are returned (feasibility answers)
            # but outcome/genomic detail is suppressed to prevent
            # re-identification of individual patients. n=0 (empty/missing
            # corpus) takes the same shape so callers see a uniform schema.
            return {**base, "suppressed_small_n": True,
                    "failure_rate": None, "n_labeled": 0, "median_os": None,
                    "median_tmb": None, "km": {"t": [], "S": []},
                    "top_coalterations": [], "by_site": {}, "by_cohort": {}}

        os_t = np.array([r["os_months"] if r["os_months"] is not None else np.nan
                         for r in sel])
        os_e = np.array([r["os_status"] if r["os_status"] is not None else np.nan
                         for r in sel])
        res = [r["resistant"] for r in sel if r["resistant"] is not None]
        tmb = [r["tmb"] for r in sel if r["tmb"] is not None]
        t, s, _ = kaplan_meier(os_t, os_e)
        gene_counts = Counter(g for r in sel for g in r["genes"])
        top_coalt = [{"gene": g, "n": c, "pct": c / max(n, 1) * 100}
                     for g, c in gene_counts.most_common(15)]
        return {**base, "suppressed_small_n": False,
                "failure_rate": float(np.mean(res)) if res else None,
                "n_labeled": len(res),
                "median_os": median_survival(os_t, os_e),
                "median_tmb": float(np.median(tmb)) if tmb else None,
                "km": {"t": [float(x) for x in t], "S": [float(x) for x in s]},
                "top_coalterations": top_coalt,
                "by_site": dict(Counter(r["cancer_type"] for r in sel).most_common(8)),
                "by_cohort": dict(Counter(r["cohort"] for r in sel))}


_ENGINE = None


def get_engine():
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = CohortAnalytics()
    return _ENGINE
