import streamlit as st
import pandas as pd
import json
import os
import re
import plotly.graph_objects as go
import plotly.express as px
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from backend.predictor import ResistancePredictor
from backend.data_ingestion import ClinicalDataIngestor, CaseQueueManager
from backend.institutional_db import InstitutionalDB
from backend.trial_engine import ClinicalTrialEngine

# --- PERFORMANCE OPTIMIZATION: GLOBAL RESOURCE CACHING ---
@st.cache_resource
def load_clinical_resources():
    try:
        predictor = ResistancePredictor(
            model_dir=os.environ.get("RESISTANCEAI_MODEL_DIR", "backend/artifacts"))
    except Exception as e:
        # Missing/unreadable model artifact degrades to the landing page with
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

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="ResistanceAI | Frontier Oncology Intelligence",
    page_icon="🧬",
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
    st.toast("Switching Clinical Context...", icon="🧬")

# --- THEME CONSTANTS ---
accent_color = "#3b82f6"
bg_color = "#0f172a"
card_bg = "rgba(30, 41, 59, 0.7)"
text_primary = "#f1f5f9"
text_secondary = "#94a3b8"
border_color = "rgba(255, 255, 255, 0.1)"

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Outfit:wght@600;700&display=swap');
    html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
    .stApp {{ background: {bg_color}; }}
    h1, h2, h3, h4 {{ font-family: 'Outfit', sans-serif !important; color: {text_primary} !important; }}
    [data-testid="stSidebar"] {{ background-color: #1e293b; border-right: 1px solid {border_color}; }}
    .worklist-item {{ background: rgba(255,255,255,0.03); border: 1px solid {border_color}; padding: 10px; border-radius: 8px; margin-bottom: 8px; cursor: pointer; }}
    .worklist-item:hover {{ background: rgba(59, 130, 246, 0.1); }}
    [data-testid="stMetric"], .metric-card {{ background: {card_bg} !important; backdrop-filter: blur(12px); border: 1px solid {border_color} !important; border-radius: 1rem; padding: 1rem; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); }}
    div[data-baseweb="select"], .stTextInput input, .stNumberInput input {{ background-color: #334155 !important; color: {text_primary} !important; border: 1px solid {border_color} !important; }}
    .stTabs [data-baseweb="tab-list"] {{ gap: 1.4rem; }}
    .stTabs [data-baseweb="tab"] {{ color: {text_secondary} !important; font-weight: 600; }}
    .stTabs [aria-selected="true"] {{ color: {accent_color} !important; border-bottom-color: {accent_color} !important; }}
    .therapy-card {{ background: rgba(59, 130, 246, 0.05); border: 1px solid rgba(59, 130, 246, 0.2); border-left: 5px solid {accent_color}; border-radius: 1rem; padding: 1.3rem; margin-bottom: 1rem; }}
    .mech-card {{ background: rgba(239, 68, 68, 0.05); border: 1px solid rgba(239, 68, 68, 0.25); border-left: 5px solid #ef4444; border-radius: 0.8rem; padding: 1rem; margin-bottom: 0.8rem; }}
    .mech-card.sens {{ background: rgba(16, 185, 129, 0.05); border-color: rgba(16,185,129,0.25); border-left-color: #10b981; }}
    .therapy-header {{ color: {accent_color} !important; font-weight: 700; font-size: 1.05rem; margin-bottom: 0.4rem; }}
    .rationale-text {{ font-size: 0.85rem; color: #cbd5e1 !important; line-height: 1.5; font-style: italic; margin-top: 0.8rem; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 0.8rem; }}
    .evidence-tag {{ display: inline-block; background: rgba(16, 185, 129, 0.2); color: #10b981 !important; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 700; margin-right: 8px; }}
    .guideline-tag {{ display: inline-block; background: rgba(59, 130, 246, 0.2); color: {accent_color} !important; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 700; margin-right: 6px; }}
    .warn-tag {{ display: inline-block; background: rgba(245, 158, 11, 0.2); color: #f59e0b !important; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 700; margin-right: 6px; }}
    .footer {{ text-align: center; border-top: 1px solid {border_color}; margin-top: 50px; padding: 30px 0; color: {text_secondary} !important; }}
    .investigational-banner {{
        background: rgba(245, 158, 11, 0.12);
        border: 1px solid rgba(245, 158, 11, 0.4);
        color: #f59e0b !important;
        text-align: center; font-weight: 700; font-size: 0.75rem;
        letter-spacing: 0.05em; padding: 6px 12px; border-radius: 6px;
        margin-bottom: 12px;
    }}
</style>
<div class="investigational-banner">INVESTIGATIONAL USE ONLY — NOT FOR CLINICAL DIAGNOSTIC USE WITHOUT BOARD APPROVAL</div>
""", unsafe_allow_html=True)


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
        st.error(f"Engine Inference Error: {e}")


# --- HEADER SECTION ---
_ART_DIR = os.environ.get("RESISTANCEAI_MODEL_DIR", "backend/artifacts")
m = load_json(os.path.join(_ART_DIR, "model_metrics.json")) or {}
cohort_stats = load_json(os.path.join(_ART_DIR, "cohort_stats.json")) or {}
n_corpus = (cohort_stats.get("label_counts", {}) or {}).get("total", 0)
st.markdown(f"""
<div style="display: flex; align-items: center; gap: 20px; margin-bottom: 20px;">
    <div style="background: {accent_color}; padding: 12px; border-radius: 18px; display: flex; align-items: center; justify-content: center;">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5">
            <path d="m8 8 8 8"/><path d="m16 8-8 8"/><path d="M12 2v4"/><path d="M12 18v4"/><path d="M4.93 4.93 7.76 7.76"/><path d="m16.24 16.24 2.83 2.83"/><path d="M2 12h4"/><path d="M18 12h4"/><path d="m4.93 19.07 2.83-2.83"/><path d="m16.24 7.76 2.83-2.83"/>
        </svg>
    </div>
    <div>
        <h1 style="margin: 0; padding: 0;">ResistanceAI Frontier</h1>
        <p style="color: {text_secondary}; margin: 0; font-size: 0.9rem;">Multi-Omic Oncology Intelligence • v9.0 • Trained on MSK-IMPACT + MSK-CHORD</p>
    </div>
    <div style="margin-left: auto; text-align: right;">
        <span style="color: #10b981; font-weight: 600;">● Corpus: {n_corpus:,} labeled patients</span><br>
        <span style="color: {text_secondary}; font-size: 0.7rem;">AUC {m.get('roc_auc', 0):.3f} · Brier {m.get('brier', 0):.3f} · Calibrated ensemble</span>
    </div>
</div>
""", unsafe_allow_html=True)

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("### 🔌 Institutional Bridge")
    if st.button("🔄 Force Live EHR Sync (Epic)", width="stretch"):
        st.toast("Syncing Patient Notes, Labs, & Meds from EHR...", icon="📥")

    with st.expander("📄 Upload Genomic Report (NGS JSON)", expanded=False):
        up = st.file_uploader("Illumina/Foundation-style report", type=["json"], label_visibility="collapsed")
        if up is not None and st.button("Ingest Report", width="stretch"):
            try:
                parsed = ClinicalDataIngestor.ingest_genomic_report(up.read().decode())
                st.session_state.form_data = {k: v for k, v in parsed.items() if v is not None}
                st.session_state.form_data["patient_name"] = up.name
                # Switch clinical context to the uploaded patient: deselect any
                # queued case (runs before the selectbox instantiates below, so
                # the widget renders empty) and mark the source so the queue
                # block can't overwrite the report's data on this rerun.
                st.session_state.case_select_main = None
                st.session_state.ingested_id = f"report:{up.name}"
                trigger_inference()
                st.success("Report ingested.")
            except Exception as e:
                st.error(str(e))

    st.divider()
    st.markdown("### 🏢 Core Systems")
    v_mode = st.radio("Access Level / Validation Mode",
                      ["Standard Care (Pilot)", "Shadow Mode (Silent)"],
                      help="MISSION CRITICAL: Pilot for board decisions. Shadow for background validation.",
                      index=0)
    st.session_state.validation_mode = v_mode

    st.divider()
    st.markdown("### 📂 Patient Office")
    search_query = st.text_input("🔍 Cohort Search", placeholder="ID or site", key="search_main").lower()
    queue_df = pd.DataFrame(st.session_state.case_queue)
    mask = (queue_df.apply(lambda r: search_query in str(r.values).lower(), axis=1)
            if search_query and len(queue_df)
            else pd.Series(True, index=queue_df.index))
    filtered = queue_df[mask]

    def _queue_label(x):
        # Real corpus entries carry pid + cohort (bare P-XXXXXXX ids collide
        # across IMPACT/CHORD); mock entries fall back to their demo id.
        r = filtered.loc[x]
        pid = r["pid"] if "pid" in r and pd.notna(r["pid"]) else r["id"]
        co = r["cohort"] if "cohort" in r and pd.notna(r["cohort"]) else None
        return f"{pid} ({co}) | {r['site']}" if co else f"{pid} | {r['site']}"

    selected_idx = st.selectbox(f"Active Queue ({len(filtered)})",
                               options=filtered.index,
                               format_func=_queue_label,
                               index=None,
                               key="case_select_main",
                               on_change=reset_case_state,
                               help="Select a patient. Real MSK-IMPACT/CHORD cases plus curated demos.")
    if selected_idx is not None:
        # 'id' is the cohort-qualified uid for real records ("chord:P-0001")
        # — the only key that uniquely identifies the patient.
        cid = filtered.loc[selected_idx, 'id']
        if st.session_state.ingested_id != cid:
            # Ingest only when the selection actually changes. selectbox values
            # persist across reruns, so re-ingesting here on every interaction
            # would overwrite uploaded reports and stress-test perturbations —
            # and spam the shadow log with duplicate entries.
            patient_data = ClinicalDataIngestor.ingest_ehr_patient(cid)
            st.session_state.form_data = {k: v for k, v in patient_data.items() if v is not None}
            st.session_state.form_data['patient_id'] = cid
            st.session_state.ingested_id = cid
            trigger_inference()
            if v_mode == "Shadow Mode (Silent)" and st.session_state.prediction_result:
                core_db.log_shadow_entry(cid, st.session_state.prediction_result)
                st.toast("Shadow Entry Logged", icon="🛰️")

    with st.expander("Scenario Stress Test (What-If)", expanded=False):
        st.caption("Perturb the profile and re-score.")
        fd_now = st.session_state.form_data
        cur_stage = str(fd_now.get('stage') or 'III')
        if cur_stage not in ('I', 'II', 'III', 'IV'):
            cur_stage = 'III'
        new_stage = st.select_slider("Stage", ['I', 'II', 'III', 'IV'],
                                     value=cur_stage)
        cur_tmb = fd_now.get('tmb')
        new_tmb = st.number_input("TMB (mut/Mb)", 0.0, 500.0,
                                  float(cur_tmb if cur_tmb is not None else 5.0))
        if st.button("Re-score", width="stretch"):
            st.session_state.form_data.update({'stage': new_stage, 'tmb': new_tmb})
            trigger_inference()
            if st.session_state.prediction_result:
                st.metric("Simulated Risk",
                          f"{st.session_state.prediction_result['risk_score']}%")

# --- MAIN DASHBOARD ---
if st.session_state.prediction_result:
    res = st.session_state.prediction_result
    fd = st.session_state.form_data

    tabs = st.tabs(["🎯 SNAPSHOT", "💊 PATHWAYS", "🧬 WORKBENCH", "👥 DIGITAL TWIN",
                    "📽️ MTB PACKET", "📈 INSTITUTIONAL RWE", "🧪 VALIDATION", "🏭 PHARMA"])

    # ================= SNAPSHOT =================
    with tabs[0]:
        st.markdown(f"## Patient Instance: {fd.get('patient_name', fd.get('patient_id', 'Case Ingested'))}")
        st.caption("Calibrated multi-omic risk prediction with mechanistic reasoning.")

        col1, col2 = st.columns([1.4, 1])
        with col1:
            site_label = (fd.get('cancer_type_detailed') or fd.get('cancer_type') or '').title()
            tmb_disp = f"{fd['tmb']:.1f} mut/Mb" if fd.get('tmb') is not None else "n/a"
            st.info(f"🧬 **Diagnosis:** {site_label} | **Stage:** {fd.get('stage','?')} | "
                    f"**TMB:** {tmb_disp} | "
                    f"**Sample:** {fd.get('sample_type','?')}")

            m1, m2, m3, m4 = st.columns(4)
            ci_lo, ci_hi = res.get('risk_ci', [res['risk_score'], res['risk_score']])
            m1.metric("RESISTANCE RISK", f"{res['risk_score']}%",
                      delta=f"±{ci_hi - res['risk_score']}% (ensemble interval)",
                      delta_color="off",
                      help="Calibrated probability of treatment failure / early progression. Interval = disagreement across the 8-model ensemble.")
            pct = int(round(res.get('cohort_percentile', 0)))
            suf = "th" if 11 <= pct % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(pct % 10, "th")
            m2.metric("COHORT PERCENTILE", f"{pct}{suf}",
                      help="Risk placement vs held-out test patients from the labeled MSK corpus.")
            n_mech = len([x for x in res.get('mechanisms', []) if not x.get('sensitivity')])
            m3.metric("MECHANISMS", n_mech, help="Established/emerging resistance hypotheses detected.")
            n_sens = len([x for x in res.get('mechanisms', []) if x.get('sensitivity')])
            m4.metric("SENSITIVITY SIGNALS", n_sens, help="Alterations predicting therapy benefit.")

            st.divider()
            st.markdown("#### 🧠 Patient-Specific Attribution")
            st.caption("Leave-one-out ablation: impact of each feature on THIS patient's risk.")
            contribs = res.get('feature_contributions', [])
            if contribs:
                cdf = pd.DataFrame(contribs)
                cdf["color"] = cdf["weight"].apply(lambda w: "#ef4444" if w > 0 else "#10b981")
                fig = go.Figure(go.Bar(
                    x=cdf["weight"] * 100, y=cdf["display"], orientation='h',
                    marker_color=cdf["color"]))
                fig.update_layout(xaxis_title="Δ risk (percentage points)",
                                  height=300, margin=dict(l=0, r=0, t=10, b=0),
                                  paper_bgcolor="rgba(0,0,0,0)", template="plotly_dark")
                st.plotly_chart(fig, width="stretch")
                st.caption("Red = raises this patient's risk · Green = protective context")

        with col2:
            st.markdown("#### Risk Gauge")
            gauge = go.Figure(go.Indicator(
                mode="gauge+number",
                value=res['risk_score'],
                number={'suffix': '%'},
                gauge={'axis': {'range': [0, 100]},
                       'bar': {'color': accent_color},
                       'steps': [{'range': [0, 40], 'color': "rgba(16,185,129,0.15)"},
                                 {'range': [40, 70], 'color': "rgba(245,158,11,0.12)"},
                                 {'range': [70, 100], 'color': "rgba(239,68,68,0.15)"}],
                       'threshold': {'line': {'color': "#f59e0b", 'width': 3},
                                     'thickness': 0.8, 'value': res['risk_score']}},
                title={'text': f"{res['risk_tier']} · interval {ci_lo}–{ci_hi}%"}))
            gauge.update_layout(height=230, margin=dict(t=60, b=0, l=20, r=20),
                                paper_bgcolor="rgba(0,0,0,0)", template="plotly_dark")
            st.plotly_chart(gauge, width="stretch")

            st.markdown("#### 🔬 Resistance Mechanisms")
            mechs = res.get('mechanisms', [])
            if mechs:
                for mech in mechs[:4]:
                    cls = "mech-card sens" if mech.get("sensitivity") else "mech-card"
                    tag = "SENSITIVITY" if mech.get("sensitivity") else mech['category'].upper()
                    st.markdown(f"""<div class="{cls}">
                        <b>{mech['mechanism']}</b> <span class="warn-tag">{tag}</span><br>
                        <span style="font-size:0.8rem;color:#cbd5e1">{mech['implication']}</span><br>
                        <span style="font-size:0.75rem;color:{text_secondary}">Evidence: {', '.join(mech['evidence'][:3])}</span>
                    </div>""", unsafe_allow_html=True)
            else:
                st.caption("No established escape mechanism detected in this profile.")

        km_by = (cohort_stats.get("km_by_risk") or [])
        if km_by:
            st.divider()
            st.markdown("#### 📉 Real-World Survival by Predicted Risk Stratum")
            st.caption(f"Kaplan-Meier overall survival of {sum(s['n'] for s in km_by):,} labeled corpus patients, "
                       "stratified by out-of-fold predicted risk quartile (each patient scored by a model that never saw their record).")
            figkm = go.Figure()
            colors = ["#10b981", "#84cc16", "#f59e0b", "#ef4444"]
            for s, c in zip(km_by, colors):
                figkm.add_trace(go.Scatter(x=s["t"], y=s["S"], mode='lines',
                                           name=f"{s['stratum']} (n={s['n']})",
                                           line=dict(color=c, width=3, shape='hv')))
            figkm.update_layout(xaxis_title="Months", yaxis_title="Overall survival",
                                height=300, template="plotly_dark",
                                paper_bgcolor="rgba(0,0,0,0)",
                                margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(figkm, width="stretch")

    # ================= PATHWAYS =================
    with tabs[1]:
        st.markdown("### 💊 Evidence-Matched Therapies")
        st.caption("Regimens matched to this patient's alterations — biomarker, CNA, fusion, and signature-level.")
        for t in res['recommendation']['therapies']:
            rn = f"<br><span style='font-size:0.75rem;color:#f59e0b'>⚠ {t['resistance_note']}</span>" if t.get('resistance_note') else ""
            st.markdown(f"""
            <div class="therapy-card">
                <div class="therapy-header">{t['name']}</div>
                <div>
                    <span class="evidence-tag">{t.get('evidence_level','—')}</span>
                    <span class="guideline-tag">{t.get('guideline_tier','—')}</span>
                    <span class="guideline-tag">{t.get('line','—')}</span>
                    <span class="warn-tag">MATCH: {t.get('matched_biomarker','—')}</span>
                </div>
                <div class="rationale-text">{t.get('rationale','')}</div>{rn}
            </div>""", unsafe_allow_html=True)

        st.divider()
        st.markdown("### 🧬 Trial Discovery Engine")
        st.caption("Live ClinicalTrials.gov v2 — filtered by patient biomarkers.")
        current_site = fd.get('cancer_type_canonical') or fd.get('cancer_type', 'lung')
        current_variants = [g for g in (fd.get('gene_mutations') or fd.get('detected_variants', []))][:6]
        t_col1, t_col2 = st.columns([3, 1])
        with t_col1:
            custom_biomarker = st.text_input("🧬 Additional biomarker filter", placeholder="e.g. MET amplification")
        with t_col2:
            limit_results = st.number_input("Limit", 10, 100, 40)
        search_terms = current_variants + ([custom_biomarker] if custom_biomarker else [])
        try:
            with st.spinner("Querying live trial database..."):
                engine_results = core_trials.fetch_trials(current_site, search_terms, limit=limit_results)
            if engine_results:
                st.write(f"**{len(engine_results)}** recruiting/active trials matched.")
                st.dataframe(pd.DataFrame(engine_results), width="stretch", hide_index=True)
            else:
                broad = core_trials.fetch_trials(current_site, limit=limit_results)
                st.dataframe(pd.DataFrame(broad), width="stretch", hide_index=True)
        except Exception as e:
            st.error(f"Discovery engine offline: {e}")
            with open("backend/knowledge_base/trials.json") as f:
                st.dataframe(pd.DataFrame(json.load(f)['trials']), width="stretch", hide_index=True)

    # ================= WORKBENCH =================
    with tabs[2]:
        st.markdown("### 🧬 Molecular Workbench")
        st.caption("Real alteration calls from the sequenced tumor — SNVs, CNAs, fusions, and the mutational spectrum.")
        disp = fd.get('display', {}) or {}
        w1, w2 = st.columns([1.4, 1])

        with w1:
            st.markdown("#### Detected Variants")
            variants = disp.get('variants') or []
            if not variants and fd.get('gene_mutations'):
                variants = [{"gene": g, "variant_class": "reported", "protein_change": "", "change": ""}
                            for g in fd['gene_mutations']]
            if variants:
                vdf = pd.DataFrame(variants).rename(columns={
                    "gene": "Gene", "variant_class": "Class",
                    "protein_change": "Protein", "change": "Ref>Alt"})
                st.dataframe(vdf, width="stretch", hide_index=True)
            else:
                st.info("No mutation calls attached to this case.")

            st.markdown("#### Copy-Number & Structural Events")
            cna_events = disp.get('cna_events') or []
            if not cna_events and fd.get('cna'):
                cna_events = [{"gene": g, "call": v,
                               "event": "Amplification" if v >= 2 else ("Gain" if v == 1 else ("Deep deletion" if v <= -2 else "Loss"))}
                              for g, v in fd['cna'].items() if v != 0]
            if cna_events:
                cdf2 = pd.DataFrame(cna_events).rename(columns={
                    "gene": "Gene", "event": "Event", "call": "Call"})
                st.dataframe(cdf2, width="stretch", hide_index=True)
            fusions = disp.get('fusions') or fd.get('fusions') or []
            if fusions:
                st.markdown("#### Fusions / Structural Variants")
                fdf = pd.DataFrame(fusions)
                if not fdf.empty:
                    st.dataframe(fdf, width="stretch", hide_index=True)

        with w2:
            st.markdown("#### Substitution Spectrum")
            spec = fd.get('substitution_spectrum') or {}
            if spec:
                order = ["C>A", "C>G", "C>T", "T>A", "T>C", "T>G"]
                xs = [k for k in order if k in spec]
                ys = [spec.get(k, 0) for k in xs]
                fig_sig = px.bar(x=ys, y=xs, orientation='h',
                                 color=xs, color_discrete_map={
                                     "C>A": "#22d3ee", "C>G": "#f8fafc", "C>T": "#ef4444",
                                     "T>A": "#94a3b8", "T>C": "#a3e635", "T>G": "#f472b6"})
                fig_sig.update_layout(showlegend=False, height=240,
                                      xaxis_title="Count", margin=dict(l=0, r=0, t=10, b=0),
                                      paper_bgcolor="rgba(0,0,0,0)", template="plotly_dark")
                st.plotly_chart(fig_sig, width="stretch")
                ct = spec.get("C>T", 0); ca = spec.get("C>A", 0); cg = spec.get("C>G", 0)
                tot = sum(spec.values()) or 1
                st.caption(f"Interpretation: aging/clock-like C>T share {ct/tot*100:.0f}% · "
                           f"smoking-linked C>A {ca/tot*100:.0f}% · "
                           f"APOBEC-window C>T+C>G {(ct+cg)/tot*100:.0f}%")

            st.markdown("#### Genomic Burden")
            b1, b2 = st.columns(2)
            b1.metric("TMB (mut/Mb)", f"{(fd.get('tmb') or 0):.1f}" if fd.get('tmb') is not None else "n/a")
            b2.metric("FGA (% genome)", f"{(fd.get('fga') or 0)*100:.0f}" if fd.get('fga') is not None else "n/a")
            b3, b4 = st.columns(2)
            b3.metric("Amps", int(fd.get('n_amp') or 0))
            b4.metric("Deep dels", int(fd.get('n_deepdel') or 0))
            st.metric("Mutational context",
                      f"MSI {fd.get('msi_type') or 'n/a'} · "
                      f"HRD {'present' if fd.get('hr_deficiency') == 'present' else 'absent'}")

    # ================= DIGITAL TWIN =================
    with tabs[3]:
        st.markdown("### 👥 Digital Twin Analysis")
        st.caption("Nearest real patients in multi-omic space (importance-weighted), with observed outcomes.")
        try:
            twin_engine = get_twin_engine()
            same_site = st.checkbox("Restrict to same cancer type", value=True)
            k = st.slider("Neighbors", 5, 20, 8)
            twins = twin_engine.find_twins(fd, core_predictor.medians, k=k,
                                           same_site=same_site)
            summ = twins["summary"]
            if summ.get("n"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Similar patients", summ["n"])
                c2.metric("Median OS (twins)",
                          f"{summ['median_os']:.1f} mo" if summ.get('median_os') else "n/a")
                c3.metric("Failure rate (twins)",
                          f"{summ['failure_rate']*100:.0f}%" if summ.get('failure_rate') is not None else "n/a")

                km_t = summ.get("km", {})
                km_all = cohort_stats.get("km_all", {})
                figt = go.Figure()
                if km_all.get("t"):
                    figt.add_trace(go.Scatter(x=km_all["t"], y=km_all["S"], mode='lines',
                                              name=f"Labeled corpus (n={km_all['n']:,})",
                                              line=dict(color="#64748b", dash='dash')))
                figt.add_trace(go.Scatter(x=km_t["t"], y=km_t["S"], mode='lines',
                                          name="Digital twins", line=dict(color="#3b82f6", width=4)))
                figt.update_layout(xaxis_title="Months", yaxis_title="Survival",
                                   height=280, template="plotly_dark",
                                   paper_bgcolor="rgba(0,0,0,0)",
                                   margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(figt, width="stretch")

                tdf = pd.DataFrame(twins["twins"])
                if not tdf.empty:
                    tdf["OS (mo)"] = tdf["os_months"].round(1)
                    tdf["Failed tx"] = tdf["resistant"].map({1: "Yes", 0: "No"})
                    tdf["Drivers"] = tdf["drivers"].apply(lambda l: ", ".join(l[:4]))
                    tdf["Similarity"] = (tdf["similarity"] * 100).round(0).astype(int).astype(str) + "%"
                    tdf["Tx agents"] = tdf["tx_agents"].apply(lambda l: ", ".join(l[:3]) or "—")
                    st.dataframe(tdf[["pid", "cohort", "cancer_type", "stage", "Drivers",
                                      "OS (mo)", "Failed tx", "Tx agents", "Similarity"]],
                                 width="stretch", hide_index=True)
        except Exception as e:
            st.warning(f"Digital twin engine unavailable: {e}")

    # ================= MTB PACKET =================
    with tabs[4]:
        st.markdown("### 📋 Molecular Tumor Board (MTB) Readiness")
        flow_col1, flow_col2 = st.columns(2)
        with flow_col1:
            st.markdown("#### 📄 Clinical Documentation")
            if st.button("Generate & Dispatch Pre-Board Packet", width="stretch"):
                mech_lines = "\n".join(f"  - {x['mechanism']} ({x['category']}): {x['strategy']}"
                                       for x in res.get('mechanisms', [])[:5])
                tx_lines = "\n".join(f"  - {t['name']} [{t.get('matched_biomarker','')}]"
                                     for t in res['recommendation']['therapies'][:5])
                packet = f"""RESISTANCEAI v9 — MTB DOSSIER
==============================
Patient: {fd.get('patient_id', 'N/A')} | Source: {fd.get('patient_name', 'EHR')}
Site: {fd.get('cancer_type_detailed') or fd.get('cancer_type')} | Stage: {fd.get('stage')}
TMB: {fd.get('tmb')} mut/Mb | MSI: {fd.get('msi_type')} | FGA: {fd.get('fga')}

RISK ASSESSMENT
  Calibrated risk: {res['risk_score']}% (ensemble interval {res['risk_ci'][0]}-{res['risk_ci'][1]}%)
  Cohort percentile: {res.get('cohort_percentile')}%
  Tier: {res['risk_tier']}
  {res['interpretation']}

RESISTANCE MECHANISM HYPOTHESES
{mech_lines or '  None detected'}

EVIDENCE-MATCHED THERAPIES
{tx_lines}

Attribution drivers (ablation):
{chr(10).join(f'  - {c["display"]}: {c["weight"]*100:+.1f}pp' for c in res.get('feature_contributions', [])[:8])}
"""
                safe_pid = re.sub(r"[^A-Za-z0-9._-]+", "_",
                                  str(fd.get('patient_id', 'case')))
                st.download_button("Download Dossier", data=packet,
                                   file_name=f"MTB_Dossier_{safe_pid}.txt",
                                   width="stretch")
                st.toast("Dossier generated.", icon="📧")
            if st.button("Generate EHR SOAP Note", width="stretch"):
                soap = (f"S: Genomic profiling for therapy resistance.\n"
                        f"O: {fd.get('cancer_type')} Stage {fd.get('stage')}. TMB {fd.get('tmb')}, "
                        f"MSI {fd.get('msi_type')}.\n"
                        f"A: Calibrated resistance risk {res['risk_score']}% "
                        f"(interval {res['risk_ci'][0]}-{res['risk_ci'][1]}%); {res['risk_tier']} tier.\n"
                        f"P: MTB review; lead therapy option "
                        f"{res['recommendation']['therapies'][0]['name']}.")
                st.text_area("EHR-ready note", value=soap, height=160)

        with flow_col2:
            st.markdown("#### ✅ Decision Capture")
            board_resolution = st.selectbox("Consensus Decision",
                ["Accept AI Proposal", "Standard Protocol", "Palliative Care", "Other Clinical Trial"])
            board_notes = st.text_area("Discussion Highlights")
            if st.button("Finalize Board Record", width="stretch"):
                core_db.archive_mtb_decision(fd.get('patient_id', 'UNSPEC'), {
                    "decision": board_resolution,
                    "ai_suggestion": res['recommendation']['therapies'][0]['name'],
                    "risk_score": res['risk_score'],
                    "cancer_type": fd.get('cancer_type'),
                    "notes": board_notes})
                st.success("Board conclusion saved to institutional archive.")

    # ================= RWE =================
    with tabs[5]:
        st.markdown("### 📈 Closed-Loop Real-World Evidence")
        stat1, stat2, stat3 = st.columns(3)
        stat1.metric("Deployed Case Cohort", f"n={len(core_db.list_cases())}",
                     delta="this instance", delta_color="off")
        stat2.metric("Labeled corpus", f"{n_corpus:,}", delta="MSK-IMPACT+CHORD",
                     delta_color="off")
        stat3.metric("Model AUC (held-out)",
                     f"{m.get('roc_auc', 0):.3f}" if m.get('roc_auc') else "n/a",
                     delta="real test set", delta_color="off")
        st.caption("Real-world evidence here reflects (a) cases recorded through this deployment's "
                   "audit ledger and (b) the public sequenced corpus — not multi-site hospital outcomes.")

        st.divider()
        r_col1, r_col2 = st.columns([1.8, 1])
        with r_col1:
            st.markdown("#### Corpus-level survival context")
            km_all = cohort_stats.get("km_all", {})
            if km_all.get("t"):
                fig_rwe = go.Figure()
                fig_rwe.add_trace(go.Scatter(
                    x=km_all["t"], y=km_all["S"], mode='lines',
                    name=f"Labeled corpus (n={km_all['n']:,})", line=dict(color="#3b82f6", width=3)))
                fig_rwe.update_layout(xaxis_title="Months since sequencing",
                                      yaxis_title="Overall survival", height=320,
                                      template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_rwe, width="stretch")
        with r_col2:
            st.markdown("#### Evidence Persistence Ledger")
            records = core_db.list_cases(10)
            if records:
                st.dataframe(pd.DataFrame(records), width="stretch", hide_index=True)
            else:
                st.info("No audit records yet.")

    # ================= VALIDATION =================
    with tabs[6]:
        st.markdown("### 🧪 Model Validation (held-out, real metrics)")
        if m:
            v1, v2, v3, v4 = st.columns(4)
            v1.metric("ROC-AUC", f"{m['roc_auc']:.3f}", f"n_test={m['n_test']:,}", delta_color="off")
            v2.metric("PR-AUC", f"{m['pr_auc']:.3f}", f"prevalence {m['positive_rate']*100:.0f}%", delta_color="off")
            v3.metric("Brier", f"{m['brier']:.3f}", f"ECE {m['ece']:.3f}", delta_color="off")
            v4.metric("Features", m['model']['features'], m['model']['type'], delta_color="off")

            g1, g2 = st.columns(2)
            with g1:
                roc = m.get('roc_curve', [])
                if roc:
                    fig_roc = go.Figure()
                    fig_roc.add_trace(go.Scatter(x=[p['fpr'] for p in roc],
                                                 y=[p['tpr'] for p in roc],
                                                 mode='lines', name=f"AUC={m['roc_auc']:.3f}",
                                                 line=dict(color='#3b82f6', width=3)))
                    fig_roc.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode='lines',
                                                 line=dict(dash='dash', color='#64748b'), showlegend=False))
                    fig_roc.update_layout(title="ROC (held-out)", xaxis_title="FPR",
                                          yaxis_title="TPR", height=280, template="plotly_dark",
                                          paper_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig_roc, width="stretch")
            with g2:
                cal = m.get('calibration', [])
                if cal:
                    fig_cal = go.Figure()
                    fig_cal.add_trace(go.Scatter(
                        x=[c['mean_pred'] for c in cal], y=[c['observed'] for c in cal],
                        mode='markers+lines', marker=dict(size=[max(4, c['n']/200) for c in cal]),
                        name='observed', line=dict(color='#10b981', width=3)))
                    fig_cal.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode='lines',
                                                 line=dict(dash='dash', color='#64748b'), showlegend=False))
                    fig_cal.update_layout(title="Calibration (held-out, bubble=n)",
                                          xaxis_title="Predicted risk", yaxis_title="Observed rate",
                                          height=280, template="plotly_dark",
                                          paper_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig_cal, width="stretch")

            with st.expander("Per-cohort & per-cancer-type performance"):
                pc = m.get('per_cohort', {})
                st.write("**By cohort**")
                st.dataframe(pd.DataFrame(pc).T, width="stretch")
                ct = m.get('per_cancer_type', [])
                if ct:
                    st.write("**By cancer type (n≥50)**")
                    st.dataframe(pd.DataFrame(ct), width="stretch", hide_index=True)
            with st.expander("Top permutation importances"):
                ti = m.get('top_importance', [])
                if ti:
                    st.dataframe(pd.DataFrame(ti), width="stretch", hide_index=True)
        else:
            st.info("Train v9 first (backend/models/train_v2.py) to populate real metrics.")

    # ================= PHARMA =================
    with tabs[7]:
        st.markdown("### 🏭 Biomarker Cohort Analytics")
        st.caption("Trial-feasibility style queries over the full sequenced corpus.")
        try:
            ca = get_cohort_engine()
            p1, p2, p3 = st.columns(3)
            with p1:
                sites = st.multiselect("Cancer types",
                    ["lung", "breast", "colorectal", "prostate", "ovarian", "melanoma",
                     "pancreatic", "bladder", "renal", "cns", "esophagogastric",
                     "endometrial", "sarcoma", "head_neck", "hepatobiliary"],
                    default=["lung"])
            with p2:
                genes_in = st.multiselect("Mutated genes (all required)",
                    ["TP53", "KRAS", "EGFR", "BRAF", "PIK3CA", "ERBB2", "ALK", "MET",
                     "BRCA1", "BRCA2", "STK11", "KEAP1", "RB1", "ARID1A", "POLE",
                     "MSH2", "APC", "PTEN", "ESR1", "AR"])
            with p3:
                tmb_min = st.slider("Min TMB (mut/Mb)", 0, 100, 0)
                stage_iv = st.checkbox("Stage IV only")

            q = ca.query(cancer_types=sites or None, genes=genes_in or None,
                         tmb_min=tmb_min if tmb_min else None, stage_iv=stage_iv)
            if q.get("suppressed_small_n"):
                st.info("Cohort has <5 patients — outcome statistics suppressed "
                        "to protect patient privacy.")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Patients", f"{q['n']:,}", f"{q['prevalence_pct']:.1f}% of corpus", delta_color="off")
            c2.metric("Failure rate",
                      f"{q['failure_rate']*100:.0f}%" if q['failure_rate'] is not None else "n/a",
                      f"n={q['n_labeled']:,}", delta_color="off")
            c3.metric("Median OS",
                      f"{q['median_os']:.1f} mo" if q['median_os'] else "n/a")
            c4.metric("Median TMB",
                      f"{q['median_tmb']:.1f}" if q['median_tmb'] else "n/a")

            pk1, pk2 = st.columns([1.4, 1])
            with pk1:
                figp = go.Figure()
                figp.add_trace(go.Scatter(x=q['km']['t'], y=q['km']['S'], mode='lines',
                                          name=f"Selected cohort (n={q['n']:,})",
                                          line=dict(color='#3b82f6', width=3)))
                km_all = cohort_stats.get('km_all', {})
                if km_all.get('t'):
                    figp.add_trace(go.Scatter(x=km_all['t'], y=km_all['S'], mode='lines',
                                              name="Labeled corpus", line=dict(color='#64748b', dash='dash')))
                figp.update_layout(xaxis_title="Months", yaxis_title="Overall survival",
                                   height=300, template="plotly_dark",
                                   paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(figp, width="stretch")
            with pk2:
                st.markdown("#### Top co-alterations")
                tc = pd.DataFrame(q['top_coalterations'])
                if not tc.empty:
                    figc = px.bar(tc, x='pct', y='gene', orientation='h',
                                  labels={'pct': '% of cohort'})
                    figc.update_layout(height=300, showlegend=False,
                                       paper_bgcolor="rgba(0,0,0,0)", template="plotly_dark",
                                       margin=dict(l=0, r=0, t=10, b=0))
                    st.plotly_chart(figc, width="stretch")
        except Exception as e:
            st.warning(f"Pharma analytics unavailable: {e}")

else:
    st.markdown(f"""
    <div style="text-align: center; padding: 120px 0; opacity: 0.8;">
        <svg width="80" height="80" viewBox="0 0 24 24" fill="none" stroke="{accent_color}" stroke-width="1.5" style="margin-bottom: 20px;">
            <circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>
        </svg>
        <h2 style="color: {text_primary} !important;">Frontier Command Center</h2>
        <p style="color: {text_secondary} !important; font-size: 1.1rem;">Awaiting case intake — select a patient or upload an NGS report.</p>
    </div>
    """, unsafe_allow_html=True)

st.markdown("""
<div class="footer">
    <b>ResistanceAI Frontier Oncology Intelligence</b><br>
    Multi-omic CDS • Calibrated ensemble (MSK-IMPACT + MSK-CHORD) • Local audit ledger<br>
    <div style="margin-top:10px; font-size: 0.7rem; opacity: 0.6;">
        Investigational only. All findings require oncologist validation.
    </div>
</div>
""", unsafe_allow_html=True)
