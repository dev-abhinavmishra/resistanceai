"""
Flask API for ResistanceAI v9 — calibrated multi-omic resistance prediction.

Endpoints:
  GET  /health            liveness
  GET  /model/info        model version + held-out metrics
  POST /predict           calibrated risk for one clinical input
  POST /predict/batch     up to 1000 clinical inputs
  POST /cohort/query      aggregate biomarker-cohort analytics over the corpus

Security notes:
  * Set RESISTANCEAI_API_KEY to require an `X-API-Key` header on the data
    endpoints. If unset, the API runs in open development mode.
  * /cohort/query returns aggregate statistics only — no row-level records.
  * /predict validates types and required content before inference; malformed
    payloads get a 400 with a field-level error list.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.exceptions import RequestEntityTooLarge
import os
import sys
import hmac
import json
import time
import threading
from pathlib import Path
from typing import Dict, Any, List, Tuple

sys.path.append(str(Path(__file__).parent.parent))

from backend.predictor import get_predictor
from backend.features import canonical_cancer_type

app = Flask(__name__)
# Reject oversized request bodies — a genomic payload is a few KB, and a
# full 1000-case batch still fits well under this bound.
app.config["MAX_CONTENT_LENGTH"] = int(
    os.environ.get("RESISTANCEAI_MAX_BODY_BYTES", 5 * 1024 * 1024))
# CORS: comma-separated allowlist via RESISTANCEAI_CORS_ORIGINS, e.g.
# "https://mtb.hospital.org". "*" (default) is dev-mode only.
CORS(app, origins=[o.strip() for o in
                   os.environ.get("RESISTANCEAI_CORS_ORIGINS", "*").split(",")])

API_KEY = os.environ.get("RESISTANCEAI_API_KEY")
MODEL_DIR = os.environ.get("RESISTANCEAI_MODEL_DIR", "backend/artifacts")

# Per-client sliding-window rate limits (requests/minute) on the inference
# endpoints — each /predict performs ~100 model evaluations for ablation
# attribution, so unbounded call rates are a real DoS surface. 0 disables.
_RATE_LIMITS = {
    "predict": int(os.environ.get("RESISTANCEAI_RL_PREDICT", "120")),
    "predict_batch": int(os.environ.get("RESISTANCEAI_RL_BATCH", "10")),
    "cohort_query": int(os.environ.get("RESISTANCEAI_RL_COHORT", "30")),
}
_RATE_LOCK = threading.Lock()
_RATE_HITS: Dict[str, List[float]] = {}
# X-Forwarded-For is only meaningful behind a reverse proxy we control —
# trusting it unconditionally lets any caller rotate spoofed IPs and evade
# the limiter. Opt in explicitly for proxied deployments.
_TRUST_PROXY = os.environ.get("RESISTANCEAI_TRUST_PROXY", "").lower() in \
    ("1", "true", "yes")


def _client_key() -> str:
    if _TRUST_PROXY:
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _rate_limited(bucket: str):
    """True (with a 429 tuple) when the caller exceeds the per-minute cap."""
    limit = _RATE_LIMITS[bucket]
    if limit <= 0:
        return None
    now = time.time()
    key = f"{bucket}:{_client_key()}"
    with _RATE_LOCK:
        # Bound memory if a client rotates source keys to churn the map.
        if len(_RATE_HITS) > 20000:
            _RATE_HITS.clear()
        hits = [t for t in _RATE_HITS.get(key, []) if now - t < 60]
        if len(hits) >= limit:
            _RATE_HITS[key] = hits
            return jsonify({"error": "rate limit exceeded — retry shortly"}), 429
        hits.append(now)
        _RATE_HITS[key] = hits
        return None

_NUMERIC_FIELDS = {
    "age_at_diagnosis", "tmb", "msi_score", "tumor_purity", "n_mut",
    "n_indel_frac", "fga", "n_amp", "n_deepdel", "sv_count",
    "ct_transition_pct", "n_met_sites", "os_months",
}
_LIST_OF_STR_FIELDS = {"gene_mutations", "detected_variants",
                       "variant_hints", "tx_agents"}
_VALID_STAGES = {"I", "II", "III", "IV", "STAGE 1-3", "STAGE 4"}
_KNOWN_FIELDS = _NUMERIC_FIELDS | _LIST_OF_STR_FIELDS | {
    "cancer_type", "cancer_type_canonical", "cancer_type_detailed", "stage",
    "sex", "smoking_history", "sample_type", "msi_type", "hr_deficiency",
    "cna", "fusions", "substitution_spectrum", "spectrum_fractions",
    "pdl1_status", "oncotree_code",
    "metastatic_site", "patient_id", "patient_name", "her2_positive",
    "tmb_level", "structural_variant_burden", "mutation_details",
    "os_status", "display", "label_source",
}


def _auth_error():
    """Optional API-key guard; open when RESISTANCEAI_API_KEY is unset."""
    if API_KEY:
        provided = request.headers.get("X-API-Key", "")
        if not hmac.compare_digest(provided, API_KEY):
            return jsonify({"error": "unauthorized — provide a valid X-API-Key header"}), 401
    return None


def _validate_clinical_input(data: Any) -> Tuple[List[str], List[str]]:
    """Type/shape validation for a clinical-input payload.

    Returns (errors, warnings). Errors -> HTTP 400; warnings are surfaced in
    the response so callers know when the model ran on degraded input.
    """
    errors: List[str] = []
    warnings: List[str] = []
    if not isinstance(data, dict) or not data:
        return ["payload must be a non-empty JSON object"], warnings

    unknown = set(data) - _KNOWN_FIELDS
    if unknown:
        warnings.append(f"ignored unknown fields: {sorted(unknown)}")

    for f in _NUMERIC_FIELDS:
        v = data.get(f)
        # bool is a subclass of int — reject it explicitly so {"tmb": true}
        # can't slip through as a numeric value
        if v is not None and (isinstance(v, bool) or
                              not isinstance(v, (int, float))):
            errors.append(f"'{f}' must be numeric, got {type(v).__name__}")
    for f in _LIST_OF_STR_FIELDS:
        v = data.get(f)
        if v is not None and (
                not isinstance(v, list) or
                not all(isinstance(x, str) for x in v)):
            errors.append(f"'{f}' must be a list of gene symbols (strings)")
    cna = data.get("cna")
    if cna is not None:
        if not isinstance(cna, dict) or not all(
                isinstance(k, str) and isinstance(v, (int, float))
                for k, v in cna.items()):
            errors.append("'cna' must be an object mapping gene -> numeric call "
                          "(e.g. {\"MET\": 2, \"PTEN\": -2})")
    fusions = data.get("fusions")
    if fusions is not None:
        if not isinstance(fusions, list):
            errors.append("'fusions' must be a list of gene-pair objects "
                          "or \"A-B\" strings")
        else:
            for i, fz in enumerate(fusions):
                if isinstance(fz, str):
                    # Pair strings ("EML4-ALK"/"EML4_ALK") — a single bare
                    # token would otherwise be interpreted as a fusion
                    # involving that gene, fabricating fusion_any=1.
                    if len([t for t in fz.replace("_", "-").split("-")
                            if t]) < 2:
                        errors.append(
                            f"'fusions[{i}]' string must name a gene pair "
                            "(e.g. \"EML4-ALK\")")
                        break
                    continue
                # dicts carry one or both partner genes — one-sided
                # rearrangements legitimately have only gene1 (the corpus
                # itself produces them). Each present gene must be a string
                # and at least one must be non-empty; arbitrary dicts would
                # reach the feature builder unchecked otherwise.
                if not isinstance(fz, dict) or \
                        any(k in fz and not isinstance(fz[k], str)
                            for k in ("gene1", "gene2")) or \
                        not (fz.get("gene1") or fz.get("gene2")):
                    errors.append(
                        f"'fusions[{i}]' must be a string or an object with "
                        "string 'gene1'/'gene2' (at least one non-empty)")
                    break
    spec = data.get("substitution_spectrum")
    if spec is not None:
        if not isinstance(spec, dict) or not all(
                isinstance(k, str) and isinstance(v, (int, float))
                for k, v in spec.items()):
            errors.append("'substitution_spectrum' must be an object mapping "
                          "substitution class -> count (e.g. {\"C>T\": 12})")
    fracs = data.get("spectrum_fractions")
    if fracs is not None:
        if not isinstance(fracs, dict) or not all(
                isinstance(k, str) and isinstance(v, (int, float)) and 0 <= v <= 1
                for k, v in fracs.items()):
            errors.append("'spectrum_fractions' must be an object mapping "
                          "substitution class -> fraction in [0,1] "
                          "(e.g. {\"C>T\": 0.42})")
    stage = data.get("stage")
    if stage is not None and str(stage).upper().strip() not in _VALID_STAGES:
        errors.append(f"'stage' must be one of {sorted(_VALID_STAGES)}")
    age = data.get("age_at_diagnosis")
    if age is not None and isinstance(age, (int, float)) and not (0 < age <= 130):
        errors.append("'age_at_diagnosis' must be in (0, 130]")

    has_signal = any(
        data.get(f) not in (None, [], {})
        for f in
        ("gene_mutations", "cna", "fusions", "tmb", "age_at_diagnosis",
         "stage", "detected_variants", "substitution_spectrum",
         "spectrum_fractions"))
    if not has_signal:
        errors.append("no clinically meaningful fields supplied — provide at "
                      "least one of: cancer_type + stage, tmb, gene_mutations, "
                      "cna, fusions, age_at_diagnosis")

    if not errors:
        canon = data.get("cancer_type_canonical") or \
            canonical_cancer_type(data.get("cancer_type"))
        if canon == "other":
            if data.get("cancer_type"):
                warnings.append(
                    f"unrecognized cancer_type '{data['cancer_type']}' — "
                    "treated as 'other'")
            else:
                warnings.append("no cancer_type provided — treated as 'other'")
    return errors, warnings


@app.route('/health', methods=['GET'])
def health_check() -> Dict[str, str]:
    return {"status": "ok"}


@app.route('/model/info', methods=['GET'])
def model_info() -> Dict[str, Any]:
    # Authenticated like the data endpoints when RESISTANCEAI_API_KEY is set —
    # model internals are not public metadata on a guarded deployment.
    auth = _auth_error()
    if auth:
        return auth
    p = get_predictor()
    metrics_path = Path(MODEL_DIR) / "model_metrics.json"
    metrics = {}
    if metrics_path.exists():
        metrics = json.loads(metrics_path.read_text())
    return jsonify({
        "version": p.meta.get("version") if p else "fallback",
        "features": len(p.feature_names) if p else 0,
        "n_training": (p.meta or {}).get("n_training") if p else 0,
        "roc_auc": metrics.get("roc_auc"),
        "brier": metrics.get("brier"),
        "pr_auc": metrics.get("pr_auc"),
        "model": metrics.get("model"),
        "auth": "api-key" if API_KEY else "open-dev",
    })


@app.route('/predict', methods=['POST'])
def predict() -> Dict[str, Any]:
    """
    Predict calibrated resistance risk.

    Accepts the v9 clinical-input schema (any subset; missing values are
    median-imputed):
    {
        "cancer_type": "non-small cell lung cancer" or "lung",
        "stage": "I|II|III|IV",
        "age_at_diagnosis": int,
        "sex": "Male|Female",
        "smoking_history": "Never|Former/Current",
        "sample_type": "Primary|Metastasis",
        "tumor_purity": float (0-100),
        "tmb": float (mut/Mb),
        "msi_type": "Stable|Unstable",
        "gene_mutations": ["EGFR", "TP53", ...],
        "cna": {"MET": 2, "CDKN2A": -2, ...},
        "fusions": [{"gene1": "EML4", "gene2": "ALK"}] or ["EML4-ALK"],
        "substitution_spectrum": {"C>T": 12, "C>A": 4, ...},
        "sv_count": int, "hr_deficiency": "present|absent"
    }

    Legacy 7-feature payloads are auto-mapped for backward compatibility.

    Pass-through fields (`patient_id`, `display`, `mutation_details`,
    `tx_agents`, `os_months`, `os_status`, `label_source`, `n_met_sites`,
    `metastatic_site`, `oncotree_code`, `pdl1_status`) are accepted so corpus
    records round-trip unchanged, but are ignored by the model — outcome
    fields cannot influence the score.
    """
    auth = _auth_error()
    if auth:
        return auth
    limited = _rate_limited("predict")
    if limited:
        return limited
    p = get_predictor()
    if not p:
        return jsonify({"error": "model artifact unavailable — "
                                 "run backend/models/train_v2.py"}), 503
    try:
        data = request.get_json(force=True, silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "payload must be a JSON object"}), 400
        errors, warnings = _validate_clinical_input(data)
        if errors:
            return jsonify({"error": "invalid clinical input",
                            "details": errors}), 400
        result = p.predict_resistance(data)
        if warnings:
            result["warnings"] = warnings
        return jsonify(result)
    except RequestEntityTooLarge:
        raise  # let the 413 handler return the JSON size error
    except Exception:
        app.logger.exception("predict failed")
        return jsonify({"error": "internal server error"}), 500


@app.route('/predict/batch', methods=['POST'])
def predict_batch() -> Dict[str, Any]:
    """Batch scoring: {"cases": [clinical_input, ...]} -> list of results."""
    auth = _auth_error()
    if auth:
        return auth
    limited = _rate_limited("predict_batch")
    if limited:
        return limited
    try:
        data = request.get_json(force=True, silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "payload must be a JSON object "
                                     "with a 'cases' list"}), 400
        cases = data.get("cases", [])
        if not isinstance(cases, list) or len(cases) > 1000:
            return jsonify({"error": "cases must be a list of <=1000 inputs"}), 400
        per_case = [_validate_clinical_input(c) for c in cases]
        bad = {i: errs for i, (errs, _) in enumerate(per_case) if errs}
        if bad:
            return jsonify({"error": "invalid clinical input",
                            "details": bad}), 400
        p = get_predictor()
        if not p:
            return jsonify({"error": "model not loaded"}), 503
        results = []
        for c, (_, warn) in zip(cases, per_case):
            r = p.predict_resistance(c)
            if warn:
                r["warnings"] = warn
            results.append(r)
        return jsonify({"results": results})
    except RequestEntityTooLarge:
        raise
    except Exception:
        app.logger.exception("predict/batch failed")
        return jsonify({"error": "internal server error"}), 500


@app.route('/cohort/query', methods=['POST'])
def cohort_query() -> Dict[str, Any]:
    """Pharma cohort analytics: biomarker-defined cohort over the corpus.

    Aggregate statistics only. Outcome/genomic detail is suppressed when the
    matched cohort has 1-4 patients (see MIN_COHORT_FOR_STATS) so individual
    records cannot be re-identified through query differencing.
    """
    auth = _auth_error()
    if auth:
        return auth
    limited = _rate_limited("cohort_query")
    if limited:
        return limited
    try:
        from backend.cohort_analytics import get_engine
        body = request.get_json(force=True, silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "payload must be a JSON object"}), 400
        verr = _validate_cohort_query(body)
        if verr:
            return jsonify({"error": "invalid cohort query",
                            "details": verr}), 400
        res = get_engine().query(
            cancer_types=body.get("cancer_types"),
            genes=body.get("genes"),
            amps=body.get("amps"),
            dels=body.get("dels"),
            tmb_min=body.get("tmb_min"),
            tmb_max=body.get("tmb_max"),
            msi=body.get("msi"),
            stage_iv=body.get("stage_iv", False),
            hrd=body.get("hrd"),
        )
        return jsonify(res)
    except RequestEntityTooLarge:
        raise
    except Exception:
        app.logger.exception("cohort/query failed")
        return jsonify({"error": "internal server error"}), 500


def _validate_cohort_query(body: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    for f in ("cancer_types", "genes", "amps", "dels"):
        v = body.get(f)
        if v is not None and (
                not isinstance(v, list) or
                not all(isinstance(x, str) for x in v)):
            errors.append(f"'{f}' must be a list of strings")
    for f in ("tmb_min", "tmb_max"):
        v = body.get(f)
        if v is not None and not isinstance(v, (int, float)):
            errors.append(f"'{f}' must be numeric")
    if body.get("msi") is not None and \
            str(body["msi"]).lower() not in ("unstable", "stable"):
        errors.append("'msi' must be 'unstable' or 'stable'")
    for f in ("stage_iv", "hrd"):
        if body.get(f) is not None and not isinstance(body[f], bool):
            errors.append(f"'{f}' must be a boolean")
    return errors


@app.errorhandler(413)
def too_large(_e):
    return jsonify({"error": "request body too large"}), 413


@app.errorhandler(500)
def internal_error(_e):
    # Generic response — internal exception text stays in the server log,
    # never on the wire.
    return jsonify({"error": "internal server error"}), 500


if __name__ == "__main__":
    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs(os.environ.get("RESISTANCEAI_DATA_DIR", "backend/data"),
                exist_ok=True)
    app.run(host="0.0.0.0", port=5000, debug=False)
