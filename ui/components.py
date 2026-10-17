"""Reusable HTML-rendered components. Every data-derived value interpolated
into `unsafe_allow_html` is escaped here — uploaded report fields (gene
names, cancer types, filenames) are not trusted markup."""
import html
import re

import streamlit as st

from .theme import ACCENT, NEG, POS, WARN


def esc(s):
    return html.escape(str(s))


def eyebrow(text, top=None):
    style = f' style="margin-top:{top}"' if top else ""
    st.markdown(f'<div class="eyebrow"{style}>{esc(text)}</div>',
                unsafe_allow_html=True)


def notice():
    st.markdown(
        '<div class="notice">Investigational use only — research prototype · '
        'not a diagnostic device · all outputs require oncologist review</div>',
        unsafe_allow_html=True)


def masthead(n_corpus, auc_txt):
    corpus_meta = (f"MSK-IMPACT + MSK-CHORD · {n_corpus:,} labeled patients"
                   if n_corpus else "MSK-IMPACT + MSK-CHORD")
    st.markdown(f"""
<div class="masthead">
    <div>
        <div class="eyebrow">Molecular tumor board decision support</div>
        <h1 class="mast-title">ResistanceAI</h1>
        <div class="mast-sub">Calibrated treatment-resistance risk from tumor genomics</div>
    </div>
    <div class="mast-meta">
        model v9.0 · 8-model ensemble + isotonic calibration<br>
        {corpus_meta}{auc_txt}
    </div>
</div>
""", unsafe_allow_html=True)


def case_line(fd):
    """One-line patient descriptor under the case title. cancer_type/stage/
    sample_type arrive verbatim from uploaded NGS reports — escape them."""
    site_label = (fd.get('cancer_type_detailed') or fd.get('cancer_type')
                  or 'Unspecified cancer type').title()
    tmb_disp = (f"{fd['tmb']:.1f} mut/Mb" if isinstance(fd.get('tmb'), (int, float))
                else "not reported")
    # Corpus stages arrive as "STAGE 1-3"/"STAGE 4" — drop the redundant word
    # so the line reads "Stage IV / Stage 1-3", not "Stage STAGE 1-3".
    stage = re.sub(r"(?i)^stage\s*[:.-]?\s*", "",
                   str(fd.get("stage") or "").strip()) or "not reported"
    st.markdown(
        f'<div class="case-line"><b>{esc(site_label)}</b> · '
        f'Stage <b>{esc(stage)}</b> · '
        f'TMB <b>{tmb_disp}</b> · '
        f'{esc(fd.get("sample_type") or "sample type not reported")}</div>',
        unsafe_allow_html=True)


def risk_hero(res):
    """The focal readout for the whole app: calibrated risk, tier, ensemble
    interval, cohort placement — plus a plain-language takeaway."""
    ci_lo, ci_hi = res.get('risk_ci', [res['risk_score'], res['risk_score']])
    pct = int(round(res.get('cohort_percentile', 0)))
    suf = "th" if 11 <= pct % 100 <= 13 else \
        {1: "st", 2: "nd", 3: "rd"}.get(pct % 10, "th")
    n_mech = len([x for x in res.get('mechanisms', []) if not x.get('sensitivity')])
    n_sens = len([x for x in res.get('mechanisms', []) if x.get('sensitivity')])
    tier_color = {"HIGH": NEG, "MODERATE": WARN, "LOW": POS}.get(
        res['risk_tier'], ACCENT)

    # Plain-language takeaway: model interpretation + the alterations that
    # most raise this patient's score — judges and clinicians alike get the
    # "so what" without reading the ablation chart.
    drivers = [c['display'] for c in res.get('feature_contributions', [])
               if c['weight'] > 0][:2]
    note = esc(res.get('interpretation', ''))
    if drivers:
        note += f" Largest contributors: {esc(' and '.join(drivers))}."

    st.markdown(f"""
    <div class="hero">
        <div class="eyebrow">Resistance risk estimate</div>
        <div style="display:flex;align-items:flex-end;gap:16px;flex-wrap:wrap">
            <div class="hero-num">{res['risk_score']}<small>%</small></div>
            <div class="hero-sub">
                <span class="tag" style="color:{tier_color};border-color:{tier_color}">{esc(res['risk_tier'])}</span>
                ensemble interval {ci_lo}–{ci_hi}%
            </div>
        </div>
        <div class="risktrack">
            <div class="riskfill" style="width:{res['risk_score']}%;background:{tier_color}"></div>
            <div class="tick" style="left:40%"></div>
            <div class="tick" style="left:70%"></div>
        </div>
        <div class="statrow">
            <div><span class="k">Cohort percentile</span><span class="v">{pct}{suf}</span></div>
            <div><span class="k">Mechanisms</span><span class="v">{n_mech}</span></div>
            <div><span class="k">Sensitivity signals</span><span class="v">{n_sens}</span></div>
            <div><span class="k">Interval spread</span><span class="v">+{ci_hi - res['risk_score']}/−{res['risk_score'] - ci_lo} pp</span></div>
        </div>
        <div class="hero-note">{note}</div>
    </div>""", unsafe_allow_html=True)


def mechanism_card(mech):
    tag_cls = "pos" if mech.get("sensitivity") else "neg"
    tag_txt = "sensitivity" if mech.get("sensitivity") else mech['category']
    ev = ", ".join(esc(e) for e in mech.get('evidence', [])[:3])
    meta = f'<div class="meta">Evidence: {ev}</div>' if ev else ""
    st.markdown(f"""<div class="card">
        <div><span class="tag {tag_cls}">{esc(tag_txt)}</span>
             <span class="tag">{esc(mech['level'])}</span></div>
        <h4>{esc(mech['mechanism'])}</h4>
        <div class="body">{esc(mech['implication'])}</div>
        {meta}
    </div>""", unsafe_allow_html=True)


def therapy_card(t):
    rn = (f'<div class="meta" style="color:{WARN}">Resistance note: '
          f'{esc(t["resistance_note"])}</div>'
          if t.get('resistance_note') else "")
    st.markdown(f"""
    <div class="card">
        <h4>{esc(t['name'])}</h4>
        <div>
            <span class="tag acc">{esc(t.get('evidence_level','—'))}</span>
            <span class="tag">{esc(t.get('guideline_tier','—'))}</span>
            <span class="tag">{esc(t.get('line','—'))}</span>
            <span class="tag">matched: {esc(t.get('matched_biomarker','—'))}</span>
        </div>
        <div class="body">{esc(t.get('rationale',''))}</div>{rn}
    </div>""", unsafe_allow_html=True)


def landing(n_corpus, m):
    """First-run experience: the problem, the method in three steps, and the
    real corpus behind it — all from loaded artifacts, nothing fabricated."""
    auc_txt = (f"{m['roc_auc']:.2f}" if m.get('roc_auc') is not None else "—")
    n_feats = (m.get('model') or {}).get('features', 201)
    # Public deployments without the licensed corpus shouldn't print "0".
    n_lbl = f"{n_corpus:,}" if n_corpus else "—"
    corpus_txt = (f"{n_corpus:,} real sequenced patients" if n_corpus
                  else "real sequenced patient cohorts")
    st.markdown(f"""
<div class="landing">
    <div class="land-panel">
        <div class="eyebrow">The problem</div>
        <div class="land-title">Cancer learns to resist treatment.</div>
        <p>About 2 million Americans are diagnosed with cancer each year. In
        advanced disease, <b>acquired drug resistance is a leading cause of
        treatment failure</b> — and the next therapy is chosen by reading the
        tumor's genome. Molecular tumor boards do that review, but their
        expertise is scarce outside major cancer centers.</p>
        <p><b>ResistanceAI puts that review into software:</b> a calibrated
        model trained on {corpus_txt} estimates the
        risk that the next regimen fails, explains which alterations drive
        it, and links the profile to evidence-matched therapies, recruiting
        trials, and outcomes of similar real patients.</p>
    </div>
    <div class="land-panel land-stats">
        <div><span class="v">{n_lbl}</span>
            <span class="k">Labeled patients (MSK-IMPACT + CHORD)</span></div>
        <div><span class="v">{auc_txt}</span>
            <span class="k">Held-out ROC-AUC</span></div>
        <div><span class="v">{n_feats}</span>
            <span class="k">Genomic + clinical features</span></div>
    </div>
</div>
<div class="how">
    <div class="eyebrow">How it works</div>
    <div class="steps">
        <div class="step"><div class="n">01</div>
            <div class="t">Load a patient</div>
            <div class="d">Pick a case from the sidebar worklist — real corpus
            patients plus built-in demos — or upload an NGS report (JSON).</div></div>
        <div class="step"><div class="n">02</div>
            <div class="t">Read the assessment</div>
            <div class="d">Calibrated resistance risk with an ensemble interval,
            the escape mechanisms behind it, and which features drive this
            patient's score.</div></div>
        <div class="step"><div class="n">03</div>
            <div class="t">Compare the options</div>
            <div class="d">Evidence-ranked therapies, live recruiting trials,
            outcomes of similar real patients, and a board-ready dossier.</div></div>
    </div>
</div>
""", unsafe_allow_html=True)


def intake_help():
    st.markdown("""
<div class="empty">
    <div class="eyebrow">Ways to load a case</div>
    <ol>
        <li>Pick a case from the <b>worklist</b> in the sidebar — corpus
            patients are labeled <b>impact2017</b> or <b>chord</b>;
            PX-* entries are built-in demos.</li>
        <li>Upload an <b>NGS report (JSON)</b> under <b>Case intake</b> —
            <span class="mono">sample_genomic_report.json</span> shows the
            expected schema.</li>
    </ol>
</div>
""", unsafe_allow_html=True)


def footer():
    st.markdown("""
<div class="footer">
    ResistanceAI · investigational research prototype · trained on MSK-IMPACT + MSK-CHORD<br>
    All outputs require review by a qualified oncologist. Not a diagnostic device.
</div>
""", unsafe_allow_html=True)
