"""Design tokens and shared chrome — see DESIGN.md for the system spec."""
import re

import streamlit as st

ACCENT = "#3b82f6"      # interactive accent — borders, fills, chart lines
ACCENT_TXT = "#60a5fa"  # accent rendered as text on dark surfaces (AA ≥4.5)
BG = "#0f172a"          # page background
SURFACE = "#1e293b"     # cards, sidebar, inputs
BORDER = "rgba(255, 255, 255, 0.09)"
TEXT = "#f1f5f9"
MUTED = "#94a3b8"
FAINT = "#7d92ab"       # tertiary/meta text, reference chart lines (AA ≥4.5)
POS = "#10b981"         # sensitivity / low risk
WARN = "#f59e0b"        # moderate risk / notices
NEG = "#f87171"         # high risk / resistance mechanisms (AA ≥4.5)
RADIUS = "6px"

SHADOW_LABEL = "Shadow (silent log)"


def inject_css():
    """Global stylesheet: tokens above are the single source of truth."""
    st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
    .stApp {{ background: {BG}; }}
    h1, h2, h3, h4 {{ font-family: 'Inter', sans-serif !important;
                     color: {TEXT} !important; letter-spacing: -0.01em; }}
    [data-testid="stSidebar"] {{ background: {SURFACE}; border-right: 1px solid {BORDER}; }}

    /* --- controls ----------------------------------------------------- */
    .stButton > button, .stDownloadButton > button {{
        background: transparent; color: {TEXT};
        border: 1px solid rgba(255,255,255,0.16); border-radius: {RADIUS};
        font-weight: 600; min-height: 40px;
    }}
    .stButton > button:hover, .stDownloadButton > button:hover {{
        border-color: {ACCENT}; color: {ACCENT_TXT}; background: transparent;
    }}
    .stButton > button:active, .stDownloadButton > button:active {{
        background: rgba(59, 130, 246, 0.08);
    }}
    .stButton > button:disabled {{ opacity: 0.45; cursor: not-allowed; }}
    div[data-baseweb="select"] > div,
    .stTextInput input, .stNumberInput input, .stTextArea textarea {{
        background-color: #141f36 !important; color: {TEXT} !important;
        border: 1px solid {BORDER} !important; border-radius: {RADIUS} !important;
    }}
    .stTabs [data-baseweb="tab-list"] {{ gap: 1.6rem; border-bottom: 1px solid {BORDER}; }}
    .stTabs [data-baseweb="tab"] {{ color: {MUTED} !important; font-weight: 600;
        font-size: 0.9rem; padding-bottom: 0.55rem; }}
    .stTabs [aria-selected="true"] {{ color: {ACCENT} !important;
        border-bottom-color: {ACCENT} !important; }}

    /* --- metrics ------------------------------------------------------ */
    [data-testid="stMetric"] {{
        background: {SURFACE}; border: 1px solid {BORDER};
        border-radius: {RADIUS}; padding: 0.7rem 0.9rem;
    }}
    [data-testid="stMetricLabel"] p {{
        color: {MUTED}; font-size: 0.68rem; font-weight: 600;
        letter-spacing: 0.09em; text-transform: uppercase;
    }}
    [data-testid="stMetricValue"] {{
        font-family: 'IBM Plex Mono', monospace; font-size: 1.45rem;
    }}

    /* --- shared components -------------------------------------------- */
    .eyebrow {{ color: {MUTED}; font-size: 0.66rem; font-weight: 700;
        letter-spacing: 0.16em; text-transform: uppercase; margin-bottom: 0.35rem; }}
    .card {{ background: {SURFACE}; border: 1px solid {BORDER};
        border-radius: {RADIUS}; padding: 1rem 1.25rem; margin-bottom: 0.75rem; }}
    .card h4 {{ margin: 0 0 0.45rem 0; font-size: 1rem; }}
    .card .body {{ font-size: 0.86rem; color: #cbd5e1; line-height: 1.55; }}
    .card .meta {{ font-size: 0.78rem; color: {MUTED}; margin-top: 0.65rem;
        border-top: 1px solid {BORDER}; padding-top: 0.6rem; }}
    .tag {{ display: inline-block; font-size: 0.64rem; font-weight: 600;
        letter-spacing: 0.07em; text-transform: uppercase;
        border: 1px solid rgba(255,255,255,0.15); color: {MUTED};
        padding: 2px 7px; border-radius: 4px; margin: 0 6px 6px 0; }}
    .tag.pos {{ color: {POS}; border-color: rgba(16,185,129,0.45); }}
    .tag.neg {{ color: {NEG}; border-color: rgba(248,113,113,0.45); }}
    .tag.warn {{ color: {WARN}; border-color: rgba(245,158,11,0.45); }}
    .tag.acc {{ color: {ACCENT_TXT}; border-color: rgba(96,165,250,0.5); }}
    .notice {{ border: 1px solid rgba(245,158,11,0.35);
        background: rgba(245,158,11,0.05); color: {WARN};
        text-align: center; font-size: 0.68rem; font-weight: 600;
        letter-spacing: 0.1em; text-transform: uppercase;
        padding: 7px 12px; border-radius: 4px; margin-bottom: 1.1rem; }}
    .case-line {{ color: {MUTED}; font-size: 0.92rem; margin: 0.2rem 0 1rem; }}
    .case-line b {{ color: {TEXT}; font-weight: 600; }}

    .masthead {{ display: flex; align-items: center; gap: 20px;
        border-bottom: 1px solid {BORDER}; padding-bottom: 1.05rem;
        margin-bottom: 1.4rem; }}
    .mast-title {{ font-size: 1.5rem; font-weight: 700; margin: 0;
        letter-spacing: -0.02em; color: {TEXT}; }}
    .mast-sub {{ color: {MUTED}; font-size: 0.85rem; margin-top: 3px; }}
    .mast-meta {{ margin-left: auto; text-align: right; color: {FAINT};
        font-size: 0.74rem; line-height: 1.55;
        font-family: 'IBM Plex Mono', monospace; }}

    .hero {{ background: {SURFACE}; border: 1px solid {BORDER};
        border-radius: {RADIUS}; padding: 1.2rem 1.4rem; margin: 0.4rem 0 1.4rem; }}
    .hero-num {{ font-family: 'IBM Plex Mono', monospace;
        font-size: clamp(2.4rem, 5vw, 3.2rem); font-weight: 600;
        line-height: 1; letter-spacing: -0.02em; }}
    .hero-num small {{ font-size: 1.3rem; color: {MUTED}; }}
    .hero-sub {{ color: {MUTED}; font-size: 0.88rem; margin-left: 4px; }}
    .hero-note {{ color: #cbd5e1; font-size: 0.9rem; line-height: 1.55;
        margin-top: 1rem; border-top: 1px solid {BORDER}; padding-top: 0.8rem;
        max-width: 62ch; }}
    .risktrack {{ position: relative; height: 6px;
        background: rgba(255,255,255,0.08); border-radius: 3px;
        margin-top: 1.05rem; }}
    .riskfill {{ height: 100%; border-radius: 3px; }}
    .risktrack .tick {{ position: absolute; top: -3px; bottom: -3px;
        width: 1px; background: rgba(255,255,255,0.3); }}
    .statrow {{ display: flex; gap: 2.2rem; flex-wrap: wrap; margin-top: 0.95rem; }}
    .statrow .k {{ display: block; color: {MUTED}; font-size: 0.64rem;
        text-transform: uppercase; letter-spacing: 0.1em; font-weight: 600; }}
    .statrow .v {{ display: block; font-family: 'IBM Plex Mono', monospace;
        font-size: 1.1rem; color: {TEXT}; margin-top: 2px; }}

    /* --- landing (no case loaded) -------------------------------------- */
    .landing {{ display: grid; grid-template-columns: 1.55fr 1fr; gap: 1rem;
        margin-top: 4vh; }}
    .land-panel {{ background: {SURFACE}; border: 1px solid {BORDER};
        border-radius: {RADIUS}; padding: 1.6rem 1.8rem; }}
    .land-title {{ font-size: 1.65rem; font-weight: 700; color: {TEXT};
        letter-spacing: -0.02em; margin: 0.2rem 0 0.8rem; }}
    .land-panel p {{ color: {MUTED}; font-size: 0.95rem; line-height: 1.65;
        margin: 0 0 0.8rem; }}
    .land-panel p:last-child {{ margin-bottom: 0; }}
    .land-panel b {{ color: {TEXT}; }}
    .land-stats {{ display: flex; flex-direction: column; gap: 1.1rem;
        justify-content: center; }}
    .land-stats .v {{ font-family: 'IBM Plex Mono', monospace; font-size: 1.6rem;
        color: {TEXT}; display: block; }}
    .land-stats .k {{ display: block; color: {MUTED}; font-size: 0.64rem;
        text-transform: uppercase; letter-spacing: 0.1em; font-weight: 600;
        margin-top: 2px; }}
    .how {{ border: 1px solid {BORDER}; border-radius: {RADIUS};
        padding: 1.3rem 1.8rem 1.5rem; margin-top: 1rem; }}
    .steps {{ display: grid; grid-template-columns: repeat(3, 1fr);
        gap: 1.6rem; margin-top: 0.8rem; }}
    .step .n {{ font-family: 'IBM Plex Mono', monospace; color: {ACCENT_TXT};
        font-size: 0.8rem; font-weight: 600; }}
    .step .t {{ color: {TEXT}; font-weight: 600; font-size: 0.92rem;
        margin: 0.15rem 0 0.35rem; }}
    .step .d {{ color: {MUTED}; font-size: 0.85rem; line-height: 1.55; }}

    .empty {{ border: 1px dashed rgba(255,255,255,0.2); border-radius: {RADIUS};
        padding: 1.6rem 1.8rem; max-width: 720px; }}
    .empty h3 {{ margin: 0.25rem 0 0.7rem; }}
    .empty p, .empty li {{ color: {MUTED}; font-size: 0.92rem; line-height: 1.6; }}
    .empty ol {{ padding-left: 1.15rem; }}
    .empty li {{ margin-bottom: 0.4rem; }}
    .empty b {{ color: {TEXT}; }}
    .mono {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.85em;
        color: {TEXT}; }}

    .footer {{ border-top: 1px solid {BORDER}; margin-top: 3.5rem;
        padding: 1.4rem 0 2rem; color: {FAINT}; font-size: 0.75rem;
        text-align: center; line-height: 1.7; }}

    /* --- states -------------------------------------------------------- */
    *:focus-visible {{ outline: 2px solid {ACCENT} !important;
        outline-offset: 1px; border-radius: 4px; }}
    @media (prefers-reduced-motion: reduce) {{
        * {{ transition: none !important; animation: none !important; }}
    }}
    @media (max-width: 640px) {{
        .masthead {{ flex-direction: column; align-items: flex-start; gap: 8px; }}
        .mast-meta {{ margin-left: 0; text-align: left; }}
        .hero {{ padding: 1rem; }}
        .statrow {{ gap: 1.3rem; }}
        .landing {{ grid-template-columns: 1fr; margin-top: 2vh; }}
        .steps {{ grid-template-columns: 1fr; gap: 1rem; }}
        .empty {{ padding: 1.4rem; }}
        .stTabs [data-baseweb="tab-list"] {{ gap: 1rem; overflow-x: auto;
            scrollbar-width: none; }}
    }}
</style>
""", unsafe_allow_html=True)


def style_fig(fig, **kw):
    """Shared chart chrome: dark template, transparent canvas, Inter type,
    tight margins. Per-figure kwargs layer on top."""
    base = dict(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter"),
                margin=dict(l=0, r=0, t=10, b=0))
    base.update(kw)
    fig.update_layout(**base)
    return fig


def esc_md(s):
    """Escape markdown metacharacters in user-derived display text so a
    report filename or patient id can't mangle a heading (the markdown
    renderer already escapes HTML; this keeps literal punctuation literal)."""
    return re.sub(r"([\\`*_{}\[\]#])", r"\\\1", str(s))
