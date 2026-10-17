"""One render function per dashboard tab. Engine/database objects are passed
in by app.py so each function stays free of app-level state."""
import json
import re

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from .components import (case_line, eyebrow, mechanism_card, risk_hero,
                         therapy_card)
from .theme import ACCENT, FAINT, MUTED, NEG, POS, WARN, esc_md, style_fig


def summary(res, fd, cohort_stats):
    """Risk summary — the focal screen: risk hero, attribution chart,
    mechanism cards, observed-outcome KM by predicted stratum."""
    patient_label = fd.get('patient_name') or fd.get('patient_id') or 'Uploaded case'
    st.markdown(f"## {esc_md(patient_label)}")
    st.caption("Calibrated probability of treatment failure or early "
               "progression on the first post-sequencing regimen.")
    case_line(fd)
    risk_hero(res)

    col1, col2 = st.columns([1.4, 1])
    with col1:
        eyebrow("Largest risk contributors")
        st.caption("Leave-one-out ablation — change in this patient's score "
                   "when each feature is reset to the population median.")
        contribs = res.get('feature_contributions', [])
        if contribs:
            cdf = pd.DataFrame(contribs)
            cdf["color"] = cdf["weight"].apply(lambda w: NEG if w > 0 else POS)
            fig = go.Figure(go.Bar(
                x=cdf["weight"] * 100, y=cdf["display"], orientation='h',
                marker_color=cdf["color"]))
            style_fig(fig, xaxis_title="Δ risk (percentage points)", height=300)
            st.plotly_chart(fig, width="stretch")
            st.caption("Red raises this patient's estimate; green lowers it.")

    with col2:
        eyebrow("Mechanism hypotheses")
        mechs = res.get('mechanisms', [])
        if mechs:
            for mech in mechs[:4]:
                mechanism_card(mech)
        else:
            st.caption("No established escape mechanism detected in this profile.")

    km_by = (cohort_stats.get("km_by_risk") or [])
    if km_by:
        eyebrow("Observed outcomes", top="1.2rem")
        st.caption(f"Kaplan–Meier overall survival for "
                   f"{sum(s['n'] for s in km_by):,} labeled corpus patients, "
                   "grouped by out-of-fold predicted-risk quartile — each patient "
                   "was scored by a model that never saw their record.")
        figkm = go.Figure()
        colors = [POS, "#84cc16", WARN, NEG]
        for s, c in zip(km_by, colors):
            figkm.add_trace(go.Scatter(x=s["t"], y=s["S"], mode='lines',
                                       name=f"{s['stratum']} (n={s['n']})",
                                       line=dict(color=c, width=2.5, shape='hv')))
        style_fig(figkm, xaxis_title="Months", yaxis_title="Overall survival",
                  height=300)
        st.plotly_chart(figkm, width="stretch")


def therapies(res, fd, trials_engine):
    """Therapy options — KB-matched regimens + live ClinicalTrials.gov query."""
    st.markdown("## Therapy options")
    st.caption("Regimens matched to this patient's alterations by the internal "
               "knowledge base. Evidence level and guideline tier describe the "
               "cited source — not a treatment recommendation.")
    for t in res['recommendation']['therapies']:
        therapy_card(t)

    st.markdown("## Recruiting clinical trials")
    st.caption("Live ClinicalTrials.gov v2 query for this cancer type, "
               "filtered by the patient's biomarkers.")
    current_site = fd.get('cancer_type_canonical') or fd.get('cancer_type', 'lung')
    current_variants = [g for g in (fd.get('gene_mutations')
                                    or fd.get('detected_variants', []))][:6]
    t_col1, t_col2 = st.columns([3, 1])
    with t_col1:
        custom_biomarker = st.text_input(
            "Additional search term", placeholder="e.g. MET amplification")
    with t_col2:
        limit_results = st.number_input("Max results", 10, 100, 40)
    search_terms = current_variants + ([custom_biomarker] if custom_biomarker else [])
    try:
        with st.spinner("Searching ClinicalTrials.gov…"):
            engine_results = trials_engine.fetch_trials(
                current_site, search_terms, limit=limit_results)
        if engine_results:
            st.write(f"**{len(engine_results)}** recruiting or active trials matched.")
            st.dataframe(pd.DataFrame(engine_results), width="stretch",
                         hide_index=True)
        else:
            broad = trials_engine.fetch_trials(current_site, limit=limit_results)
            if broad:
                st.caption("No biomarker-matched trials — showing all trials "
                           "for this cancer type.")
                st.dataframe(pd.DataFrame(broad), width="stretch", hide_index=True)
            else:
                st.info("No recruiting trials found for this cancer type.")
    except Exception as e:
        st.error(f"ClinicalTrials.gov query failed: {e}")
        with open("backend/knowledge_base/trials.json") as f:
            st.dataframe(pd.DataFrame(json.load(f)['trials']),
                         width="stretch", hide_index=True)


def molecular_profile(fd):
    """Molecular profile — variant calls, CNA events, fusions, spectrum."""
    st.markdown("## Molecular profile")
    st.caption("Alteration calls from the sequenced tumor — variants, copy-number "
               "events, fusions, and the substitution spectrum.")
    disp = fd.get('display', {}) or {}
    w1, w2 = st.columns([1.4, 1])

    with w1:
        eyebrow("Variants")
        variants = disp.get('variants') or []
        if not variants and fd.get('gene_mutations'):
            variants = [{"gene": g, "variant_class": "reported",
                         "protein_change": "", "change": ""}
                        for g in fd['gene_mutations']]
        if variants:
            vdf = pd.DataFrame(variants).rename(columns={
                "gene": "Gene", "variant_class": "Class",
                "protein_change": "Protein", "change": "Ref>Alt"})
            st.dataframe(vdf, width="stretch", hide_index=True)
        else:
            st.info("No variant calls attached to this case.")

        eyebrow("Copy-number events", top="1.2rem")
        cna_events = disp.get('cna_events') or []
        if not cna_events and fd.get('cna'):
            cna_events = [{"gene": g, "call": v,
                           "event": "Amplification" if v >= 2 else (
                               "Gain" if v == 1 else (
                                   "Deep deletion" if v <= -2 else "Loss"))}
                          for g, v in fd['cna'].items() if v != 0]
        if cna_events:
            cdf2 = pd.DataFrame(cna_events).rename(columns={
                "gene": "Gene", "event": "Event", "call": "Call"})
            st.dataframe(cdf2, width="stretch", hide_index=True)
        else:
            st.caption("No copy-number events reported.")
        fusions = disp.get('fusions') or fd.get('fusions') or []
        if fusions:
            eyebrow("Fusions & structural variants", top="1.2rem")
            fdf = pd.DataFrame(fusions)
            if not fdf.empty:
                st.dataframe(fdf, width="stretch", hide_index=True)

    with w2:
        eyebrow("Substitution spectrum")
        spec = fd.get('substitution_spectrum') or {}
        if spec:
            order = ["C>A", "C>G", "C>T", "T>A", "T>C", "T>G"]
            xs = [k for k in order if k in spec]
            ys = [spec.get(k, 0) for k in xs]
            fig_sig = px.bar(x=ys, y=xs, orientation='h',
                             color=xs, color_discrete_map={
                                 "C>A": "#22d3ee", "C>G": "#f8fafc", "C>T": NEG,
                                 "T>A": MUTED, "T>C": "#a3e635", "T>G": "#f472b6"})
            style_fig(fig_sig, showlegend=False, height=240, xaxis_title="Count")
            st.plotly_chart(fig_sig, width="stretch")
            ct = spec.get("C>T", 0)
            ca = spec.get("C>A", 0)
            cg = spec.get("C>G", 0)
            tot = sum(spec.values()) or 1
            st.caption(f"Aging/clock-like C>T {ct/tot*100:.0f}% · "
                       f"smoking-linked C>A {ca/tot*100:.0f}% · "
                       f"APOBEC-window C>T+C>G {(ct+cg)/tot*100:.0f}%")
        else:
            st.caption("No substitution spectrum on this case.")

        eyebrow("Genomic burden", top="1.2rem")
        b1, b2 = st.columns(2)
        b1.metric("TMB (mut/Mb)",
                  f"{fd['tmb']:.1f}" if isinstance(fd.get('tmb'), (int, float))
                  else "n/a")
        b2.metric("FGA",
                  f"{fd['fga']*100:.0f}%" if isinstance(fd.get('fga'), (int, float))
                  else "n/a")
        b3, b4 = st.columns(2)
        b3.metric("Amplifications", int(fd.get('n_amp') or 0))
        b4.metric("Deep deletions", int(fd.get('n_deepdel') or 0))
        st.metric("Mutational context",
                  f"MSI {fd.get('msi_type') or 'n/a'} · "
                  f"HRD {'present' if fd.get('hr_deficiency') == 'present' else 'absent'}")


def similar_patients(fd, predictor, twin_engine_fn, cohort_stats):
    """Similar patients — nearest real corpus patients + their outcomes.

    `twin_engine_fn` is the cached accessor (app.get_twin_engine), invoked
    lazily inside the try so an engine-load failure degrades this tab only."""
    st.markdown("## Similar patients")
    st.caption("The nearest real corpus patients by genomic similarity, with "
               "their observed outcomes. The loaded patient is excluded from "
               "its own neighbor set.")
    try:
        twin_engine = twin_engine_fn()
        same_site = st.checkbox("Same cancer type only", value=True)
        k = st.slider("Neighbors to retrieve", 5, 20, 8)
        twins = twin_engine.find_twins(fd, predictor.medians, k=k,
                                       same_site=same_site)
        summ = twins["summary"]
        if summ.get("n"):
            c1, c2, c3 = st.columns(3)
            c1.metric("Similar patients", summ["n"])
            c2.metric("Median OS",
                      f"{summ['median_os']:.1f} mo" if summ.get('median_os') else "n/a")
            c3.metric("Observed failure rate",
                      f"{summ['failure_rate']*100:.0f}%" if summ.get('failure_rate') is not None else "n/a")

            km_t = summ.get("km", {})
            km_all = cohort_stats.get("km_all", {})
            figt = go.Figure()
            if km_all.get("t"):
                figt.add_trace(go.Scatter(x=km_all["t"], y=km_all["S"], mode='lines',
                                          name=f"Labeled corpus (n={km_all['n']:,})",
                                          line=dict(color=FAINT, dash='dash')))
            figt.add_trace(go.Scatter(x=km_t["t"], y=km_t["S"], mode='lines',
                                      name="Similar patients", line=dict(color=ACCENT, width=3)))
            style_fig(figt, xaxis_title="Months", yaxis_title="Survival", height=280)
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
        else:
            st.info("No sufficiently similar patients found in the corpus.")
    except Exception as e:
        st.warning(f"Similar-patient engine unavailable: {e}")


def board_packet(res, fd, db):
    """Tumor board packet — dossier download, SOAP note, decision capture."""
    st.markdown("## Tumor board packet")
    flow_col1, flow_col2 = st.columns(2)
    with flow_col1:
        eyebrow("Documents")
        if st.button("Generate board dossier", width="stretch"):
            mech_lines = "\n".join(
                f"  - {x['mechanism']} ({x['category']}): {x['strategy']}"
                for x in res.get('mechanisms', [])[:5])
            tx_lines = "\n".join(
                f"  - {t['name']} [{t.get('matched_biomarker','')}]"
                for t in res['recommendation']['therapies'][:5])
            packet = f"""RESISTANCEAI — TUMOR BOARD DOSSIER
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

Largest risk contributors (ablation):
{chr(10).join(f'  - {c["display"]}: {c["weight"]*100:+.1f}pp' for c in res.get('feature_contributions', [])[:8])}
"""
            safe_pid = re.sub(r"[^A-Za-z0-9._-]+", "_",
                              str(fd.get('patient_id', 'case')))
            st.download_button("Download dossier (.txt)", data=packet,
                               file_name=f"MTB_Dossier_{safe_pid}.txt",
                               width="stretch")
            st.toast("Dossier ready")
        if st.button("Draft assessment note", width="stretch"):
            soap = (f"S: Genomic profiling for therapy-resistance assessment.\n"
                    f"O: {fd.get('cancer_type')} Stage {fd.get('stage')}. TMB {fd.get('tmb')}, "
                    f"MSI {fd.get('msi_type')}.\n"
                    f"A: Calibrated resistance risk {res['risk_score']}% "
                    f"(interval {res['risk_ci'][0]}-{res['risk_ci'][1]}%); {res['risk_tier']} tier.\n"
                    f"P: MTB review; lead therapy option "
                    f"{res['recommendation']['therapies'][0]['name']}.")
            st.text_area("Note (SOAP format)", value=soap, height=160)

    with flow_col2:
        eyebrow("Decision")
        board_resolution = st.selectbox("Consensus decision",
            ["Accept AI Proposal", "Standard Protocol", "Palliative Care",
             "Other Clinical Trial"])
        board_notes = st.text_area("Discussion notes")
        if st.button("Record decision", width="stretch"):
            db.archive_mtb_decision(fd.get('patient_id', 'UNSPEC'), {
                "decision": board_resolution,
                "ai_suggestion": res['recommendation']['therapies'][0]['name'],
                "risk_score": res['risk_score'],
                "cancer_type": fd.get('cancer_type'),
                "notes": board_notes})
            st.success("Decision recorded to the local archive.")


def institutional(db, m, cohort_stats, n_corpus):
    """Institutional record — decisions archived on this deployment + corpus KM."""
    st.markdown("## Institutional record")
    stat1, stat2, stat3 = st.columns(3)
    stat1.metric("Decisions archived", f"{len(db.list_cases())}",
                 delta="this deployment", delta_color="off")
    stat2.metric("Labeled corpus", f"{n_corpus:,}", delta="MSK-IMPACT+CHORD",
                 delta_color="off")
    stat3.metric("Held-out AUC",
                 f"{m.get('roc_auc', 0):.3f}" if m.get('roc_auc') else "n/a",
                 delta="real test set", delta_color="off")
    st.caption("Archived entries are board decisions recorded on this deployment "
               "(local JSON ledger). Corpus statistics come from the public MSK "
               "datasets — not multi-site outcomes.")

    r_col1, r_col2 = st.columns([1.8, 1])
    with r_col1:
        eyebrow("Corpus survival context")
        km_all = cohort_stats.get("km_all", {})
        if km_all.get("t"):
            fig_rwe = go.Figure()
            fig_rwe.add_trace(go.Scatter(
                x=km_all["t"], y=km_all["S"], mode='lines',
                name=f"Labeled corpus (n={km_all['n']:,})",
                line=dict(color=ACCENT, width=2.5)))
            style_fig(fig_rwe, xaxis_title="Months since sequencing",
                      yaxis_title="Overall survival", height=320)
            st.plotly_chart(fig_rwe, width="stretch")
    with r_col2:
        eyebrow("Recent board decisions")
        records = db.list_cases(10)
        if records:
            st.dataframe(pd.DataFrame(records), width="stretch", hide_index=True)
        else:
            st.info("No decisions recorded yet.")


def model_performance(m, cohort_stats):
    """Model performance — real held-out metrics + method/limitations."""
    st.markdown("## Model performance")
    st.caption("Held-out evaluation on the real test split — no training-set scores.")
    if m:
        v1, v2, v3, v4 = st.columns(4)
        v1.metric("ROC-AUC", f"{m['roc_auc']:.3f}",
                  f"n_test={m['n_test']:,}", delta_color="off")
        v2.metric("PR-AUC", f"{m['pr_auc']:.3f}",
                  f"prevalence {m['positive_rate']*100:.0f}%", delta_color="off")
        v3.metric("Brier", f"{m['brier']:.3f}",
                  f"ECE {m['ece']:.3f}", delta_color="off")
        model_meta = m.get('model', {})
        v4.metric("Features", model_meta.get('features', 'n/a'),
                  model_meta.get('type'), delta_color="off")

        g1, g2 = st.columns(2)
        with g1:
            roc = m.get('roc_curve', [])
            if roc:
                fig_roc = go.Figure()
                fig_roc.add_trace(go.Scatter(x=[p['fpr'] for p in roc],
                                             y=[p['tpr'] for p in roc],
                                             mode='lines', name=f"AUC={m['roc_auc']:.3f}",
                                             line=dict(color=ACCENT, width=2.5)))
                fig_roc.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode='lines',
                                             line=dict(dash='dash', color=FAINT),
                                             showlegend=False))
                style_fig(fig_roc, title="ROC (held-out)", xaxis_title="FPR",
                          yaxis_title="TPR", height=280)
                st.plotly_chart(fig_roc, width="stretch")
        with g2:
            cal = m.get('calibration', [])
            if cal:
                fig_cal = go.Figure()
                fig_cal.add_trace(go.Scatter(
                    x=[c['mean_pred'] for c in cal], y=[c['observed'] for c in cal],
                    mode='markers+lines',
                    marker=dict(size=[max(4, c['n']/200) for c in cal]),
                    name='observed', line=dict(color=POS, width=2.5)))
                fig_cal.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode='lines',
                                             line=dict(dash='dash', color=FAINT),
                                             showlegend=False))
                style_fig(fig_cal, title="Calibration (held-out, bubble = n)",
                          xaxis_title="Predicted risk", yaxis_title="Observed rate",
                          height=280)
                st.plotly_chart(fig_cal, width="stretch")

        with st.expander("Per-cohort and per-cancer-type results"):
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

        # label_counts.total is absent when cohort_stats.json isn't mounted —
        # `or 0` matches app.py's n_corpus fallback (a bare None would crash
        # the :,-format below since the expander body always executes).
        n_labeled = (cohort_stats.get("label_counts") or {}).get("total") or 0
        with st.expander("How the model works — and its limits"):
            st.markdown(f"""
- **Training data.** {n_labeled:,} sequenced patients with post-sequencing
  treatment-failure labels, from MSK-IMPACT 2017 and MSK-CHORD 2024
  (cBioPortal, public de-identified data).
- **Model.** {model_meta.get('type', 'ensemble')} over
  {model_meta.get('features', '—')} genomic and clinical features; the
  ensemble mean is calibrated with isotonic regression so the percentage is
  a probability, not a score.
- **Validation.** 5-fold out-of-fold predictions drive the risk-stratum
  survival curves; headline metrics are computed on a held-out test set
  (n={m['n_test']:,}). No patient is scored by a model that saw their record.
- **Uncertainty.** The interval beside each estimate is the disagreement
  across the 8 bagged models — wide intervals mean the profile is unusual.
- **Limits.** Retrospective labels from a tertiary cancer-center population;
  the estimate is a statistical association, not a causal prediction. It has
  not been prospectively validated — investigational use only.
""")
    else:
        st.info("Model metrics unavailable — run backend/models/train_v2.py first.")


def cohort_analytics(get_engine, cohort_stats):
    """Cohort analytics — aggregate feasibility queries over the corpus.

    `get_engine` is the cached accessor (app.get_cohort_engine), invoked
    lazily inside the try so an engine-load failure degrades this tab only."""
    st.markdown("## Cohort analytics")
    st.caption("Aggregate feasibility queries over the combined corpus. Outcome "
               "statistics are suppressed for cohorts under 5 patients to "
               "prevent re-identification.")
    try:
        ca = get_engine()
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
            tmb_min = st.slider("Minimum TMB (mut/Mb)", 0, 100, 0)
            stage_iv = st.checkbox("Stage IV only")

        q = ca.query(cancer_types=sites or None, genes=genes_in or None,
                     tmb_min=tmb_min if tmb_min else None, stage_iv=stage_iv)
        if q.get("suppressed_small_n"):
            st.info("Fewer than 5 patients match — outcome statistics are "
                    "suppressed to prevent re-identification.")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Patients", f"{q['n']:,}",
                  f"{q['prevalence_pct']:.1f}% of corpus", delta_color="off")
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
                                      line=dict(color=ACCENT, width=2.5)))
            km_all = cohort_stats.get('km_all', {})
            if km_all.get('t'):
                figp.add_trace(go.Scatter(x=km_all['t'], y=km_all['S'], mode='lines',
                                          name="Labeled corpus",
                                          line=dict(color=FAINT, dash='dash')))
            style_fig(figp, xaxis_title="Months", yaxis_title="Overall survival",
                      height=300)
            st.plotly_chart(figp, width="stretch")
        with pk2:
            eyebrow("Top co-alterations")
            tc = pd.DataFrame(q['top_coalterations'])
            if not tc.empty:
                figc = px.bar(tc, x='pct', y='gene', orientation='h',
                              labels={'pct': '% of cohort'})
                figc.update_traces(marker_color=ACCENT)
                style_fig(figc, height=300, showlegend=False)
                st.plotly_chart(figc, width="stretch")
    except Exception as e:
        st.warning(f"Cohort analytics unavailable: {e}")
