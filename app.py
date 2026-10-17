"""ResistanceAI — Streamlit entry point.

This module is the wiring layer: cached resources, session state, sidebar
inputs, and tab dispatch. Presentation lives in ui/ (theme, components,
tabs); model logic lives in backend/.
"""
import json
import math
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).parent))

from backend.predictor import ResistancePredictor
from backend.data_ingestion import ClinicalDataIngestor, CaseQueueManager
from backend.institutional_db import InstitutionalDB
from backend.trial_engine import ClinicalTrialEngine
from ui import components, tabs as tabs_ui, theme


# --- Shared resources (cached process-wide) ---
@st.cache_resource
def load_clinical_resources():
    try:
        predictor = ResistancePredictor(
            model_dir=os.environ.get("RESISTANCEAI_MODEL_DIR", "backend/artifacts"))
    except Exception as e:
        # Missing/unreadable model artifact degrades to the landing state with
        # instructions instead of taking down the whole app.
        print(f"Model artifact unavailable: {e}")
        predictor = None
    inst_db = InstitutionalDB()
    trial_engine = ClinicalTrialEngine()
    return predictor, inst_db, trial_engine


@st.cache_resource
def get_twin_engine():
    from backend.digital_twin import DigitalTwinEngine
    return DigitalTwinEngine()


@st.cache_resource
def get_cohort_engine():
    from backend.cohort_analytics import CohortAnalytics
    return CohortAnalytics()


@st.cache_resource
def get_institutional_queue():
    return CaseQueueManager().queue


@st.cache_data
def load_json(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


st.set_page_config(
    page_title="ResistanceAI — treatment-resistance decision support",
    page_icon=str(Path(__file__).parent / "docs" / "mark.svg"),
    layout="wide",
    initial_sidebar_state="expanded"
)

core_predictor, core_db, core_trials = load_clinical_resources()

if 'history' not in st.session_state:
    st.session_state.history = []
if 'form_data' not in st.session_state:
    st.session_state.form_data = {}
if 'prediction_result' not in st.session_state:
    st.session_state.prediction_result = None
if 'case_queue' not in st.session_state:
    st.session_state.case_queue = get_institutional_queue()
if 'ingested_id' not in st.session_state:
    # uid of the case whose data currently populates form_data (queue uid or a
    # "report:<file>" sentinel) — lets the queue block ingest ONLY on a real
    # selection change instead of on every widget rerun.
    st.session_state.ingested_id = None


def reset_case_state():
    st.session_state.prediction_result = None
    st.toast("Loading case…")


theme.inject_css()
components.notice()


def trigger_inference():
    """Run v9 ensemble inference on the current clinical input."""
    if core_predictor is None:
        st.error("Model artifact missing — run `python backend/models/train_v2.py` "
                 "to build it (or set RESISTANCEAI_MODEL_DIR to a directory "
                 "containing resistance_model_v2.pkl).")
        return
    try:
        fd = st.session_state.form_data
        st.session_state.prediction_result = core_predictor.predict_resistance(fd)
        core_db.log_audit("INFERENCE_TRIGGERED",
                          f"Profile: {fd.get('cancer_type_canonical') or fd.get('cancer_type')}")
    except Exception as e:
        # Clear the stale result: form_data was already replaced, so keeping the
        # previous prediction would show one patient's risk under another's
        # context.
        st.session_state.prediction_result = None
        st.error(f"Prediction failed: {e}")


def _set_case(patient_data, uid, deselect=False):
    st.session_state.form_data = {k: v for k, v in patient_data.items()
                                  if v is not None}
    st.session_state.form_data['patient_id'] = uid
    st.session_state.ingested_id = uid
    if deselect and 'case_select_main' in st.session_state:
        # Del is the sanctioned widget reset: assigning session_state to a
        # widget key after the widget instantiated this run raises
        # StreamlitAPIException — and the landing CTA runs after the sidebar
        # block where the selectbox is created.
        del st.session_state['case_select_main']
    trigger_inference()


def load_demo_case():
    """One-click demo for evaluators: load the richest curated worklist case.
    Prefer a Lung entry — its ALK/EGFR driver story exercises mechanisms,
    matched therapies, and similar patients alike. Falls back to any real
    case, then to the built-in demo patients."""
    queue = st.session_state.case_queue
    uid = next((e.get('id') for e in queue
                if e.get('_real') and e.get('id')
                and 'Lung' in str(e.get('site', ''))), None)
    if uid is None:
        uid = next((e.get('id') for e in queue
                    if e.get('_real') and e.get('id')), 'PX-1109')
    _set_case(ClinicalDataIngestor.ingest_ehr_patient(uid), uid, deselect=True)


# --- Header -------------------------------------------------------------
_ART_DIR = os.environ.get("RESISTANCEAI_MODEL_DIR", "backend/artifacts")
m = load_json(os.path.join(_ART_DIR, "model_metrics.json")) or {}
cohort_stats = load_json(os.path.join(_ART_DIR, "cohort_stats.json")) or {}
n_corpus = (cohort_stats.get("label_counts", {}) or {}).get("total", 0)
_auc_txt = (f" · held-out AUC {m['roc_auc']:.3f}"
            if m.get('roc_auc') is not None else "")
components.masthead(n_corpus, _auc_txt)

# --- Sidebar -------------------------------------------------------------
with st.sidebar:
    components.eyebrow("Case intake")
    if st.button("Load a demo patient", key="demo_side", width="stretch"):
        load_demo_case()
        if st.session_state.prediction_result:
            st.toast("Demo patient loaded")
    with st.expander("Upload an NGS report (JSON)", expanded=False):
        up = st.file_uploader("Illumina/Foundation-style report",
                              type=["json"], label_visibility="collapsed")
        if up is not None and st.button("Load report", width="stretch"):
            try:
                parsed = ClinicalDataIngestor.ingest_genomic_report(up.read().decode())
                parsed["patient_name"] = up.name
                _set_case(parsed, f"report:{up.name}", deselect=True)
                st.success("Report loaded.")
            except Exception as e:
                st.error(str(e))

    components.eyebrow("Validation mode", top="1.5rem")
    v_mode = st.radio("Validation mode",
                      ["Standard (pilot)", theme.SHADOW_LABEL],
                      help="Standard: the assessment is shown for board review. "
                           "Shadow: the assessment is written to the audit "
                           "ledger without changing the workflow.",
                      index=0, label_visibility="collapsed")
    st.session_state.validation_mode = v_mode

    components.eyebrow("Worklist", top="1.5rem")
    search_query = st.text_input("Filter worklist",
                                 placeholder="Patient id, site, or alteration",
                                 key="search_main",
                                 label_visibility="collapsed").lower()
    queue_df = pd.DataFrame(st.session_state.case_queue)
    mask = (queue_df.apply(lambda r: search_query in str(r.values).lower(), axis=1)
            if search_query and len(queue_df)
            else pd.Series(True, index=queue_df.index))
    filtered = queue_df[mask]

    def _queue_label(x):
        # Real corpus entries carry pid + cohort (bare P-XXXXXXX ids collide
        # across IMPACT/CHORD); demo entries are labeled as such. Keys beyond
        # 'id' are best-effort — a persisted custom case may lack them.
        r = filtered.loc[x]
        pid = r["pid"] if "pid" in r and pd.notna(r["pid"]) else \
            (r["id"] if "id" in r and pd.notna(r["id"]) else "?")
        co = r["cohort"] if "cohort" in r and pd.notna(r["cohort"]) else None
        site = r["site"] if "site" in r and pd.notna(r["site"]) else "Unspecified"
        return f"{pid} ({co}) | {site}" if co else f"{pid} | {site} · demo"

    selected_idx = st.selectbox(f"Case worklist ({len(filtered)})",
                                options=filtered.index,
                                format_func=_queue_label,
                                index=None,
                                key="case_select_main",
                                on_change=reset_case_state,
                                help="Sequenced MSK-IMPACT/CHORD patients and built-in demo cases.")
    if selected_idx is not None:
        # 'id' is the cohort-qualified uid for real records ("chord:P-0001")
        # — the only key that uniquely identifies the patient.
        cid = filtered.loc[selected_idx].get('id')
        if pd.notna(cid) and st.session_state.ingested_id != cid:
            # Ingest only when the selection actually changes. selectbox values
            # persist across reruns, so re-ingesting here on every interaction
            # would overwrite uploaded reports and stress-test perturbations —
            # and spam the shadow log with duplicate entries.
            _set_case(ClinicalDataIngestor.ingest_ehr_patient(cid), cid)
            if v_mode == theme.SHADOW_LABEL and st.session_state.prediction_result:
                core_db.log_shadow_entry(cid, st.session_state.prediction_result)
                st.toast("Logged to shadow ledger")

    with st.expander("What-if analysis"):
        st.caption("Adjust stage or TMB and re-score the loaded profile.")
        fd_now = st.session_state.form_data
        cur_stage = str(fd_now.get('stage') or 'III')
        if cur_stage not in ('I', 'II', 'III', 'IV'):
            cur_stage = 'III'
        new_stage = st.select_slider("Stage", ['I', 'II', 'III', 'IV'],
                                     value=cur_stage)
        cur_tmb = fd_now.get('tmb')
        cur_tmb = (float(cur_tmb) if isinstance(cur_tmb, (int, float))
                   and math.isfinite(cur_tmb) else 5.0)
        # The widget bound must cover the loaded value: a hypermutated report
        # (POLE/MSI-H cases can exceed 500 mut/Mb) fed in raw raises
        # StreamlitValueAboveMaxError on every rerun; negatives raise
        # BelowMinError the same way.
        new_tmb = st.number_input("TMB (mut/Mb)", 0.0, max(500.0, cur_tmb),
                                  max(0.0, cur_tmb))
        if st.button("Re-score", width="stretch"):
            st.session_state.form_data.update({'stage': new_stage, 'tmb': new_tmb})
            trigger_inference()
            if st.session_state.prediction_result:
                st.metric("Simulated risk",
                          f"{st.session_state.prediction_result['risk_score']}%")

# --- Main dashboard -------------------------------------------------------
if st.session_state.prediction_result:
    res = st.session_state.prediction_result
    fd = st.session_state.form_data

    tabs = st.tabs(["Risk summary", "Therapy options", "Molecular profile",
                    "Similar patients", "Board packet", "Institutional record",
                    "Model performance", "Cohort analytics"])

    with tabs[0]:
        tabs_ui.summary(res, fd, cohort_stats)
    with tabs[1]:
        tabs_ui.therapies(res, fd, core_trials)
    with tabs[2]:
        tabs_ui.molecular_profile(fd)
    with tabs[3]:
        # Engine accessors, not instances: a failed engine load degrades to a
        # tab-local warning instead of taking down the whole dashboard.
        tabs_ui.similar_patients(fd, core_predictor, get_twin_engine, cohort_stats)
    with tabs[4]:
        tabs_ui.board_packet(res, fd, core_db)
    with tabs[5]:
        tabs_ui.institutional(core_db, m, cohort_stats, n_corpus)
    with tabs[6]:
        tabs_ui.model_performance(m, cohort_stats)
    with tabs[7]:
        tabs_ui.cohort_analytics(get_cohort_engine, cohort_stats)

else:
    components.landing(n_corpus, m)
    c1, c2, _ = st.columns([1, 1, 2.4])
    with c1:
        if st.button("Load a demo patient", key="demo_cta", width="stretch"):
            load_demo_case()
            if st.session_state.prediction_result:
                st.toast("Demo patient loaded")
            # This button sits inside the else branch — prediction_result was
            # already resolved as falsy for this run, so without an explicit
            # rerun the click only flashes a toast and the landing stays up
            # until a second interaction.
            st.rerun()
    with c2:
        st.caption("Loads a real sequenced patient — every tab populates "
                   "with its actual data.")
    components.intake_help()

components.footer()
