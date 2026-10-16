"""
ResistanceAI v9 — frontier training pipeline.

Model: bagged HistGradientBoosting ensemble + isotonic probability calibration.
  * Ensemble spread -> per-patient prediction confidence interval
  * Isotonic calibration -> risk scores that mean what they say (Brier/ECE)
  * Permutation importance on held-out data -> honest global explanations

Artifacts (backend/artifacts/):
  resistance_model_v2.pkl   {feature_names, medians, models[], isotonic, meta}
  model_metrics.json        real evaluation metrics for the Validation tab
  cohort_stats.json         cohort summary + risk-stratum KM curves for UI
Data:
  backend/data/feature_matrix.parquet  feature vectors aligned to records
"""

import json
import os
import sys
import numpy as np
import pandas as pd
import pickle
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (roc_auc_score, average_precision_score, brier_score_loss,
                             accuracy_score, f1_score, roc_curve, precision_recall_curve,
                             confusion_matrix)
from sklearn.inspection import permutation_importance
from sklearn.model_selection import train_test_split, cross_val_predict, StratifiedKFold

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from backend.features import build_model_vector, FEATURE_NAMES
from backend.corpus import data_path, record_uid

RECORDS = data_path("patient_records.jsonl")
MATRIX_OUT = data_path("feature_matrix.parquet")
ART_DIR = os.environ.get("RESISTANCEAI_MODEL_DIR", "backend/artifacts")
MODEL_OUT = os.path.join(ART_DIR, "resistance_model_v2.pkl")
METRICS_OUT = os.path.join(ART_DIR, "model_metrics.json")
COHORT_OUT = os.path.join(ART_DIR, "cohort_stats.json")

N_ENSEMBLE = 8
HGB_PARAMS = dict(max_iter=450, learning_rate=0.05, max_leaf_nodes=31,
                  min_samples_leaf=60, l2_regularization=1.0,
                  early_stopping=True, validation_fraction=0.12,
                  n_iter_no_change=30)


def load_records(path=RECORDS):
    recs = []
    with open(path) as f:
        for line in f:
            recs.append(json.loads(line))
    return recs


def build_matrix(recs, medians=None):
    feats = [build_model_vector(r["clinical_input"], medians) for r in recs]
    X = pd.DataFrame(feats)
    return X.reindex(columns=FEATURE_NAMES, fill_value=0.0)


def km_curve(times, events, max_points=80):
    """Standard Kaplan-Meier. Returns (t, S) downsampled for display."""
    t = np.asarray(times, dtype=float)
    e = np.asarray(events, dtype=float)
    mask = ~np.isnan(t) & ~np.isnan(e)
    t, e = t[mask], e[mask]
    if len(t) == 0:
        return [0.0], [1.0]
    order = np.argsort(t)
    t, e = t[order], e[order]
    times_out, surv = [0.0], [1.0]
    S, n = 1.0, len(t)
    i = 0
    while i < n:
        ti = t[i]
        j = i
        while j < n and t[j] == ti:
            j += 1
        d = e[i:j].sum()
        at_risk = n - i
        if at_risk > 0 and d > 0:
            S *= 1.0 - d / at_risk
        times_out.append(float(ti))
        surv.append(float(S))
        i = j
    if len(times_out) > max_points:
        sel = np.unique(np.linspace(0, len(times_out) - 1, max_points).astype(int))
        times_out = [times_out[k] for k in sel]
        surv = [surv[k] for k in sel]
    return times_out, surv


def train():
    print("Loading records...")
    recs = load_records()
    labeled = [r for r in recs if r["resistant"] is not None]
    print(f"{len(recs)} total, {len(labeled)} labeled")

    meta_idx = pd.DataFrame({
        "patient_id": [r["patient_id"] for r in recs],
        "cohort": [r["cohort"] for r in recs],
        "cancer_type": [r["clinical_input"]["cancer_type_canonical"] for r in recs],
        "os_months": [r["os_months"] for r in recs],
        "os_status": [r["os_status"] for r in recs],
        "resistant": [r["resistant"] for r in recs],
    })
    lab_mask = meta_idx["resistant"].notna().values
    yl = meta_idx.loc[lab_mask, "resistant"].astype(int).values
    cohorts = np.asarray(meta_idx.loc[lab_mask, "cohort"])
    lab_idx = np.where(lab_mask)[0]

    print("Building feature matrix (pass 1, placeholder imputation)...")
    X_pre = build_matrix(recs)
    Xl_pre = X_pre.loc[lab_mask, FEATURE_NAMES].astype(float).values
    X_tr, X_tmp, y_tr, y_tmp, c_tr, c_tmp, i_tr, i_tmp = train_test_split(
        Xl_pre, yl, cohorts, lab_idx, test_size=0.4, stratify=yl, random_state=42)
    X_cal, X_te, y_cal, y_te, c_cal, c_te, i_cal, i_te = train_test_split(
        X_tmp, y_tmp, c_tmp, i_tmp, test_size=0.5, stratify=y_tmp, random_state=42)
    print(f"train {len(X_tr)} | cal {len(X_cal)} | test {len(X_te)}")

    # Imputation medians come from the TRAIN split only — medians computed over
    # the full corpus would leak evaluation-set statistics into the serving
    # path. They are then baked into every record's vector so the training
    # data and any later inference call impute identically (no train/serve
    # skew). The i_* indices are absolute record positions, so pass-2 rows are
    # selected with iloc on the full matrix, not the labeled subset.
    medians = dict(zip(FEATURE_NAMES, np.median(X_tr, axis=0).tolist()))

    print("Building feature matrix (pass 2, train-split median imputation)...")
    X_all = build_matrix(recs, medians)
    X_all["patient_id"] = meta_idx["patient_id"].values
    # cohort-qualified uid — bare P-XXXXXXX ids collide across IMPACT/CHORD,
    # so downstream joins must key on this column, not patient_id.
    X_all["uid"] = [record_uid(r) for r in recs]
    for col in ("cohort", "cancer_type", "os_months", "os_status", "resistant"):
        X_all[col] = meta_idx[col].values
    X_all.to_parquet(MATRIX_OUT, index=False)

    Xl = X_all.loc[lab_mask, FEATURE_NAMES].astype(float).values  # numpy: arrow-safe
    X_tr = X_all.iloc[i_tr][FEATURE_NAMES].astype(float).values
    X_cal = X_all.iloc[i_cal][FEATURE_NAMES].astype(float).values
    X_te = X_all.iloc[i_te][FEATURE_NAMES].astype(float).values

    print(f"Training ensemble of {N_ENSEMBLE} HGBs...")
    rng = np.random.default_rng(42)
    models = []
    for k in range(N_ENSEMBLE):
        idx = rng.choice(len(X_tr), size=int(0.85 * len(X_tr)), replace=True)
        m = HistGradientBoostingClassifier(random_state=100 + k, **HGB_PARAMS)
        m.fit(X_tr[idx], y_tr[idx])
        models.append(m)
        print(f"  model {k}: iter={m.n_iter_}")

    def ens_proba(X):
        return np.mean([m.predict_proba(np.asarray(X))[:, 1] for m in models], axis=0)

    p_cal = ens_proba(X_cal)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.001, y_max=0.999)
    iso.fit(p_cal, y_cal)

    p_te_raw = ens_proba(X_te)
    p_te = iso.predict(p_te_raw)

    auc = roc_auc_score(y_te, p_te)
    pr = average_precision_score(y_te, p_te)
    brier = brier_score_loss(y_te, p_te)
    acc = accuracy_score(y_te, p_te >= 0.5)
    f1 = f1_score(y_te, p_te >= 0.5)
    per_cohort = {}
    for c in np.unique(c_te):
        m = c_te == c
        if len(np.unique(y_te[m])) > 1:
            per_cohort[c] = {"n": int(m.sum()),
                             "auc": float(roc_auc_score(y_te[m], p_te[m])),
                             "brier": float(brier_score_loss(y_te[m], p_te[m]))}

    # calibration table
    bins = np.linspace(0, 1, 11)
    cal_table = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        sel = (p_te >= lo) & (p_te < hi + (hi == 1.0))
        if sel.sum() > 0:
            cal_table.append({"bin": f"{lo:.1f}-{hi:.1f}", "mean_pred": float(p_te[sel].mean()),
                              "observed": float(y_te[sel].mean()), "n": int(sel.sum())})
    ece = float(np.mean([abs(r["mean_pred"] - r["observed"]) for r in cal_table]))

    fpr, tpr, _ = roc_curve(y_te, p_te)
    roc_pts = [{"fpr": float(a), "tpr": float(b)} for a, b in
               zip(fpr[:: max(1, len(fpr) // 200)], tpr[:: max(1, len(tpr) // 200)])]
    prec, reca, _ = precision_recall_curve(y_te, p_te)
    pr_pts = [{"recall": float(a), "precision": float(b)} for a, b in
              zip(reca[:: max(1, len(reca) // 200)], prec[:: max(1, len(prec) // 200)])]
    tn, fp, fn, tp = confusion_matrix(y_te, p_te >= 0.5).ravel()

    print("Permutation importance (top features)...")
    base = models[0]
    pi = permutation_importance(base, np.asarray(X_te), y_te, n_repeats=4,
                                random_state=42, scoring="roc_auc", n_jobs=-1)
    imp = sorted(zip(FEATURE_NAMES, pi.importances_mean), key=lambda x: -x[1])
    top_importance = [{"feature": f, "delta_auc": float(v)} for f, v in imp[:25] if v > 0]

    # per-cancer-type performance (i_te holds absolute record positions)
    ct_perf = []
    ct_te = np.asarray(meta_idx["cancer_type"])[i_te]
    for c in pd.unique(ct_te):
        sel = ct_te == c
        if sel.sum() >= 50 and len(np.unique(y_te[sel])) > 1:
            ct_perf.append({"cancer_type": c, "n": int(sel.sum()),
                            "auc": float(roc_auc_score(y_te[sel], p_te[sel]))})
    ct_perf.sort(key=lambda x: -x["n"])

    metrics = {
        "n_train": int(len(X_tr)), "n_cal": int(len(X_cal)), "n_test": int(len(X_te)),
        "n_labeled": int(len(yl)), "positive_rate": float(yl.mean()),
        "roc_auc": float(auc), "pr_auc": float(pr), "brier": float(brier),
        "ece": ece, "accuracy": float(acc), "f1": float(f1),
        "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "per_cohort": per_cohort, "per_cancer_type": ct_perf[:15],
        "calibration": cal_table, "roc_curve": roc_pts, "pr_curve": pr_pts,
        "top_importance": top_importance,
        "cohorts": {"impact2017": int((cohorts == "impact2017").sum()),
                    "chord": int((cohorts == "chord").sum())},
        "model": {"type": "HistGradientBoosting x%d ensemble + isotonic" % N_ENSEMBLE,
                  "features": len(FEATURE_NAMES)},
    }

    # Risk-stratum KM curves must not score patients with a model that saw
    # their label — 5-fold out-of-fold predictions give every labeled patient
    # an honest held-out risk estimate. Quartile assignment uses the raw OOF
    # probability (isotonic is monotone, so strata are identical either way);
    # displayed risk values are passed through the calibrator.
    print("Out-of-fold predictions for KM strata (5-fold CV)...")
    p_oof = cross_val_predict(
        HistGradientBoostingClassifier(random_state=777, **HGB_PARAMS),
        Xl, yl, cv=StratifiedKFold(5, shuffle=True, random_state=42),
        method="predict_proba")[:, 1]
    p_oof_cal = iso.predict(p_oof)
    strata = pd.qcut(p_oof_cal, 4, labels=["Q1-low", "Q2", "Q3", "Q4-high"])
    os_t = meta_idx.loc[lab_mask, "os_months"].values
    os_e = meta_idx.loc[lab_mask, "os_status"].fillna(0).values
    km_out = []
    for s in strata.categories:
        sel = np.asarray(strata == s)
        t, S = km_curve(os_t[sel], os_e[sel])
        km_out.append({"stratum": str(s), "n": int(sel.sum()), "t": t, "S": S})
    t, S = km_curve(os_t, os_e)
    cohort_stats = {
        "km_by_risk": km_out, "km_all": {"t": t, "S": S, "n": int(len(os_t))},
        "cancer_type_counts": meta_idx["cancer_type"].value_counts().to_dict(),
        "label_counts": {"total": int(len(yl)),
                         "resistant": int(yl.sum()),
                         "sensitive": int((1 - yl).sum())},
        # out-of-fold over ALL labeled patients — not training scores
        "risk_quantiles": [float(q) for q in np.quantile(p_oof_cal, [0.25, 0.5, 0.75])],
        "prediction_source": "5-fold out-of-fold (km/quantiles); "
                             "held-out test set (cohort_risk percentiles)",
    }

    artifact = {
        "feature_names": FEATURE_NAMES, "medians": medians,
        "models": models, "isotonic": iso,
        # percentile reference = calibrated held-out test predictions only —
        # a new patient's percentile is read against scores the model never
        # trained on, not in-sample fits.
        "cohort_risk": np.sort(p_te),
        "meta": {"version": "v9", "label_rate": float(yl.mean()),
                 "n_training": int(len(yl)),
                 "cohort_risk_source": "held_out_test",
                 "cohort_risk_n": int(len(p_te)),
                 "sklearn_version": sklearn.__version__},
    }
    os.makedirs(ART_DIR, exist_ok=True)
    with open(MODEL_OUT, "wb") as f:
        pickle.dump(artifact, f)
    with open(METRICS_OUT, "w") as f:
        json.dump(metrics, f, indent=2)
    with open(COHORT_OUT, "w") as f:
        json.dump(cohort_stats, f)

    print(f"\nAUC={auc:.4f} PR-AUC={pr:.4f} Brier={brier:.4f} ECE={ece:.4f}")
    print(json.dumps(per_cohort, indent=2))
    print("Top features:", [x["feature"] for x in top_importance[:10]])
    print(f"Saved -> {MODEL_OUT}, {METRICS_OUT}, {COHORT_OUT}")


if __name__ == "__main__":
    train()
