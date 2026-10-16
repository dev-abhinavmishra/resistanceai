"""Digital twin engine — find the k most similar real patients.

Similarity is computed over the genomic subspace of the model feature space
(demographics and cancer-type one-hots excluded, so twins match on tumor
biology), restricted to patients of the same canonical cancer type first and
falling back to the full cohort. Uses MSK-IMPACT + MSK-CHORD records only.

Patient identity: feature_matrix.parquet rows carry a cohort-qualified `uid`
(``impact2017:P-0001234``) written by train_v2.py — IMPACT and CHORD share the
bare P-XXXXXXX namespace (~4.2k collisions), so twin rows must key on uids,
never bare patient ids.
"""
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .corpus import data_path, load_records, record_uid
from .features import build_model_vector, normalize_clinical_input, FEATURE_NAMES
from .survival import kaplan_meier, median_survival

FEATURE_MATRIX = "feature_matrix.parquet"

# Genomic/biological features used for similarity — the model feature space
# minus demographics (age, sex, smoking), stage encoding, and cancer-type
# one-hots (site restriction is applied as a hard mask instead).
_NON_GENOMIC = {
    "age_at_diagnosis", "stage_ord", "is_metastatic", "sex_male",
    "smoking_ever",
}
TWIN_FEATURES = [f for f in FEATURE_NAMES
                 if f not in _NON_GENOMIC and not f.startswith("ct_")]


def _scalar(v):
    """NaN -> None so outputs stay JSON/display-safe.

    The twin metadata goes through a pandas DataFrame, where missing values
    surface as float nan rather than None — `is not None` checks (and
    `f"{v:.0f}"` rendering) let nan through as a bogus value. Lists/dicts
    pass through unchanged.
    """
    try:
        return None if pd.isna(v) else v
    except (TypeError, ValueError):
        return v


class DigitalTwinEngine:
    def __init__(self):
        self._df: Optional[pd.DataFrame] = None
        self._meta: Optional[pd.DataFrame] = None
        self._mat: Optional[np.ndarray] = None
        self._std: Optional[np.ndarray] = None

    def _load(self):
        if self._df is not None:
            return
        df = pd.read_parquet(data_path(FEATURE_MATRIX))
        recs = load_records()

        if "uid" in df.columns:
            uids = df["uid"].astype(str).values
        else:
            # Legacy matrix without the uid column: train_v2 writes rows in
            # record order, so a positional join is safe — but verify the
            # bare-id alignment before trusting it rather than silently
            # attaching the wrong patient's metadata.
            pids = df["patient_id"].astype(str).values
            rec_pids = np.array([r["patient_id"] for r in recs[:len(df)]])
            if len(df) > len(recs) or (pids == rec_pids).mean() < 0.99:
                raise RuntimeError(
                    "feature_matrix.parquet is not aligned with "
                    "patient_records.jsonl — retrain via "
                    "backend/models/train_v2.py")
            uids = np.array([record_uid(r) for r in recs[:len(df)]])

        slim = {record_uid(r): r for r in recs}
        meta_rows = []
        for uid in uids:
            r = slim.get(uid)
            ci = r["clinical_input"] if r else {}
            meta_rows.append({
                "uid": uid,
                "pid": r["patient_id"] if r else None,
                "cohort": r["cohort"] if r else None,
                "site": ci.get("cancer_type_canonical"),
                "stage": ci.get("stage"),
                "drivers": list(ci.get("gene_mutations") or []),
                "os_months": r["os_months"] if r else None,
                "os_status": r["os_status"] if r else None,
                "resistant": r["resistant"] if r else None,
                "tx_agents": list(r["tx_agents"]) if r else [],
            })
        self._meta = pd.DataFrame(meta_rows)
        self._df = df
        feats = [c for c in TWIN_FEATURES if c in df.columns]
        self._feat_cols = feats
        mat = df[feats].fillna(0).values.astype(float)
        self._mat = mat
        self._std = mat.std(axis=0) + 1e-9

    def find_twins(self, clinical_input: Dict[str, Any],
                   medians: Optional[Dict[str, float]] = None,
                   k: int = 25, same_site: bool = True) -> Dict[str, Any]:
        """Return the k nearest real patients by standardized genomic distance."""
        self._load()
        # Same normalization path as inference — legacy payloads keep signal.
        ci = normalize_clinical_input(clinical_input)
        q = build_model_vector(ci, medians)
        qv = np.array([float(q.get(c) or 0.0) for c in self._feat_cols])

        site = ci.get("cancer_type_canonical")
        mask = np.ones(len(self._df), dtype=bool)
        scope = "all-sites"
        # When the query patient is itself a corpus record (patient_id carries
        # the cohort-qualified uid), exclude it — "similar patients" must mean
        # *other* patients, not a distance-0 self-match.
        q_uid = str(ci.get("patient_id") or "")
        self_row = (self._meta["uid"] == q_uid).values if q_uid else None
        if same_site and site:
            same = (self._meta["site"] == site).values
            if self_row is not None:
                same = same & ~self_row
            if same.sum() >= k:
                mask = same
                scope = site
        if self_row is not None:
            mask = mask & ~self_row

        idx = np.where(mask)[0]
        dist = np.sqrt(((self._mat[idx] - qv) / self._std) ** 2).mean(axis=1)
        order = np.argsort(dist)[:k]
        sel = idx[order]

        twins = []
        for rank, i in enumerate(sel):
            m = self._meta.iloc[i]
            twins.append({
                "rank": rank + 1,
                "uid": m["uid"],
                "pid": m["uid"],          # uid IS the unique patient key now
                "bare_pid": m["pid"],
                "cohort": m["cohort"],
                "cancer_type": m["site"],
                "site": m["site"],
                "stage": _scalar(m["stage"]),
                "drivers": m["drivers"],
                "distance": round(float(dist[order[rank]]), 4),
                "similarity": round(1.0 / (1.0 + float(dist[order[rank]])), 4),
                "os_months": _scalar(m["os_months"]),
                "os_status": _scalar(m["os_status"]),
                "resistant": _scalar(m["resistant"]),
                "tx_agents": m["tx_agents"],
            })
        return {"scope": scope, "n_pool": int(mask.sum()), "k": len(twins),
                "query_site": site, "twins": twins,
                "summary": self._summary(twins)}

    @staticmethod
    def _summary(twins: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate outcomes across the twin cohort — what happened to the
        patients who looked like this one."""
        if not twins:
            return {"n": 0, "median_os": None, "failure_rate": None,
                    "km": {"t": [], "S": []}, "n_labeled": 0}
        os_t = np.array([t["os_months"] if t["os_months"] is not None else np.nan
                         for t in twins])
        os_e = np.array([t["os_status"] if t["os_status"] is not None else np.nan
                         for t in twins])
        labeled = [t["resistant"] for t in twins if t["resistant"] is not None]
        t, s, _ = kaplan_meier(os_t, os_e)
        return {
            "n": len(twins),
            "n_labeled": len(labeled),
            "median_os": median_survival(os_t, os_e),
            "failure_rate": float(np.mean(labeled)) if labeled else None,
            "km": {"t": [float(x) for x in t], "S": [float(x) for x in s]},
        }
