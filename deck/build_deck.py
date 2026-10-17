"""Build the ResistanceAI presentation deck (16:9 PPTX).

Regenerates ResistanceAI_Presentation_v9.pptx in the project root using the
app's own design tokens (DESIGN.md): slate background, one blue accent,
mono numerals. Screenshots live in docs/screenshots/ (v9_* captures of the
running app). Run:

    python deck/build_deck.py

Requires python-pptx. Fonts: Segoe UI (body) + Consolas (code/numerals) —
both stock on Windows so the file presents identically on the demo machine.
"""
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "docs" / "screenshots"
OUT = ROOT / "ResistanceAI_Presentation_v9.pptx"

# --- design tokens (DESIGN.md) ---
BG = RGBColor(0x0F, 0x17, 0x2A)
SURFACE = RGBColor(0x1E, 0x29, 0x3B)
INSET = RGBColor(0x14, 0x1F, 0x36)
CODE_BG = RGBColor(0x0B, 0x12, 0x20)
BORDER = RGBColor(0x2B, 0x3A, 0x52)
ACCENT = RGBColor(0x3B, 0x82, 0xF6)
ACCENT_TXT = RGBColor(0x60, 0xA5, 0xFA)
TEXT = RGBColor(0xF1, 0xF5, 0xF9)
MUTED = RGBColor(0x94, 0xA3, 0xB8)
FAINT = RGBColor(0x7D, 0x92, 0xAB)
POS = RGBColor(0x10, 0xB9, 0x81)
WARN = RGBColor(0xF5, 0x9E, 0x0B)
NEG = RGBColor(0xF8, 0x71, 0x71)

BODY = "Segoe UI"
MONO = "Consolas"

EMU_W, EMU_H = Inches(13.333), Inches(7.5)

prs = Presentation()
prs.slide_width = EMU_W
prs.slide_height = EMU_H
BLANK = prs.slide_layouts[6]


def slide():
    s = prs.slides.add_slide(BLANK)
    r = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, EMU_W, EMU_H)
    r.fill.solid()
    r.fill.fore_color.rgb = BG
    r.line.fill.background()
    r.shadow.inherit = False
    return s


def _set(run, text, size, color=TEXT, font=BODY, bold=False, italic=False):
    run.text = text
    f = run.font
    f.name, f.size, f.bold, f.italic = font, Pt(size), bold, italic
    f.color.rgb = color


def box(s, x, y, w, h, anchor=MSO_ANCHOR.TOP):
    tb = s.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    return tb, tf


def para(tf, first=False):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.space_before = p.space_after = Pt(0)
    return p


def text(s, x, y, w, h, runs, size=14, color=TEXT, bold=False, font=BODY,
         align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, spacing=None):
    """runs: str or list of (txt, dict-overrides) tuples on one paragraph."""
    _, tf = box(s, x, y, w, h, anchor)
    p = para(tf, first=True)
    p.alignment = align
    if spacing is not None:
        p.line_spacing = spacing
    if isinstance(runs, str):
        runs = [(runs, {})]
    for txt, ov in runs:
        _set(p.add_run(), txt, ov.get("size", size), ov.get("color", color),
             ov.get("font", font), ov.get("bold", bold), ov.get("italic", False))
    return tf


def eyebrow(s, x, y, txt, color=MUTED):
    text(s, x, y, Inches(6), Inches(0.3), txt.upper(), size=10.5,
         color=color, bold=True)


def card(s, x, y, w, h, fill=SURFACE, line=BORDER, radius=0.055):
    c = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    try:
        c.adjustments[0] = radius
    except Exception:
        pass
    c.fill.solid()
    c.fill.fore_color.rgb = fill
    if line is None:
        c.line.fill.background()
    else:
        c.line.color.rgb = line
        c.line.width = Pt(1)
    c.shadow.inherit = False
    return c


def hline(s, x, y, w, color=BORDER):
    ln = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, Emu(9525))  # ~1px
    ln.fill.solid()
    ln.fill.fore_color.rgb = color
    ln.line.fill.background()
    ln.shadow.inherit = False


def tag(s, x, y, txt, color=ACCENT_TXT, w=None):
    w = w or Inches(0.16 + 0.062 * len(txt))
    t = card(s, x, y, w, Inches(0.3), fill=INSET, line=color, radius=0.5)
    tf = t.text_frame
    tf.word_wrap = False
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    _set(p.add_run(), txt.upper(), 8, color, MONO, True)
    return x + w + Inches(0.08)


def bullets(s, x, y, w, h, items, size=13, gap=0.62, lead_color=ACCENT_TXT):
    """items: list of (lead, rest) or plain strings."""
    for i, it in enumerate(items):
        iy = y + Inches(gap * i)
        if isinstance(it, tuple):
            lead, rest = it
            text(s, x, iy, w, Inches(gap), [
                (lead + " — ", {"color": TEXT, "bold": True}),
                (rest, {"color": MUTED})], size=size, spacing=1.12)
        else:
            text(s, x, iy, w, Inches(gap), it, size=size, color=MUTED,
                 spacing=1.12)


def header(s, eyebrow_txt, title_txt, sub=None):
    eyebrow(s, Inches(0.62), Inches(0.42), eyebrow_txt, ACCENT_TXT)
    text(s, Inches(0.6), Inches(0.68), Inches(12), Inches(0.7), title_txt,
         size=30, bold=True)
    if sub:
        text(s, Inches(0.62), Inches(1.28), Inches(11.8), Inches(0.4), sub,
             size=13, color=MUTED)
    hline(s, Inches(0.62), Inches(1.72), Inches(12.1))


def footer(s, page_no):
    text(s, Inches(0.62), Inches(7.12), Inches(9), Inches(0.3),
         "ResistanceAI · investigational research prototype — not a diagnostic "
         "device", size=9, color=FAINT)
    text(s, Inches(12.2), Inches(7.12), Inches(0.5), Inches(0.3), str(page_no),
         size=9, color=FAINT, align=PP_ALIGN.RIGHT)


def picture(s, path, x, y, w=None, h=None):
    return s.shapes.add_picture(str(path), x, y, width=w, height=h)


def img_w_for(path, x, y, w=None, h=None):
    """Return add_picture kwargs preserving aspect for the given bound."""
    iw, ih = Image.open(path).size
    if w and not h:
        h = Emu(int(w * ih / iw))
    elif h and not w:
        w = Emu(int(h * iw / ih))
    return w, h


def stat_card(s, x, y, w, value, label, vcolor=TEXT, num_size=26):
    c = card(s, x, y, w, Inches(1.05))
    text(s, x + Inches(0.22), y + Inches(0.16), w - Inches(0.4), Inches(0.5),
         value, size=num_size, color=vcolor, font=MONO, bold=True)
    text(s, x + Inches(0.22), y + Inches(0.66), w - Inches(0.4), Inches(0.3),
         label.upper(), size=8.5, color=MUTED, bold=True)


PY_KEYWORDS = {"def", "for", "in", "if", "else", "elif", "return", "import",
               "from", "with", "as", "self", "True", "False", "None", "not",
               "and", "or", "float", "int", "str", "len", "print", "raise"}


def code_card(s, x, y, w, h, title, lines, size=10.5):
    """Dark code panel: mono text, comment/string/keyword tinting."""
    card(s, x, y, w, h, fill=CODE_BG, line=BORDER)
    text(s, x + Inches(0.25), y + Inches(0.14), w - Inches(0.5), Inches(0.3),
         title, size=9.5, color=FAINT, font=MONO, bold=True)
    _, tf = box(s, x + Inches(0.25), y + Inches(0.5), w - Inches(0.5),
                h - Inches(0.6))
    for i, raw in enumerate(lines):
        p = para(tf, first=(i == 0))
        p.line_spacing = 1.05
        # crude per-line tokenizer: comment tail, quoted strings, keywords
        buf, in_str, q = "", False, ""
        segs = []
        j = 0
        while j < len(raw):
            ch = raw[j]
            if in_str:
                buf += ch
                if ch == q:
                    in_str = False
                    segs.append(("str", buf))
                    buf = ""
            elif ch in "\"'":
                if buf:
                    segs.append(("plain", buf))
                buf, in_str, q = ch, True, ch
            elif ch == "#":
                if buf:
                    segs.append(("plain", buf))
                segs.append(("com", raw[j:]))
                buf = ""
                break
            else:
                buf += ch
            j += 1
        if buf:
            segs.append(("str" if in_str else "plain", buf))
        for kind, seg in segs:
            if kind == "com":
                _set(p.add_run(), seg, size, FAINT, MONO, italic=True)
            elif kind == "str":
                _set(p.add_run(), seg, size, POS, MONO)
            else:
                # keyword tinting on word boundaries
                for tok in __import__("re").split(r"(\W)", seg):
                    if not tok:
                        continue
                    col = ACCENT_TXT if tok in PY_KEYWORDS else TEXT
                    _set(p.add_run(), tok, size, col, MONO)


# =====================================================================
# SLIDE 1 — TITLE
# =====================================================================
s = slide()

# accent square mark
mk = card(s, Inches(0.62), Inches(0.55), Inches(0.62), Inches(0.62),
          fill=INSET, line=ACCENT)
mtf = mk.text_frame
mtf.vertical_anchor = MSO_ANCHOR.MIDDLE
mp = mtf.paragraphs[0]
mp.alignment = PP_ALIGN.CENTER
_set(mp.add_run(), "R", 26, TEXT, BODY, True)

text(s, Inches(1.42), Inches(0.68), Inches(6), Inches(0.35),
     "CONGRESSIONAL APP CHALLENGE", size=11, color=ACCENT_TXT, bold=True)
text(s, Inches(0.62), Inches(1.75), Inches(12), Inches(1.2),
     [("ResistanceAI", {})], size=60, bold=True)
text(s, Inches(0.64), Inches(2.9), Inches(11.5), Inches(0.8),
     "Predicting which cancer treatments will fail — before patients "
     "start them.", size=21, color=MUTED, spacing=1.15)
text(s, Inches(0.64), Inches(3.85), Inches(11.8), Inches(0.7),
     "A calibrated machine-learning model trained on real sequenced "
     "tumors estimates the risk that the next regimen fails, shows the "
     "genomic reasons, and links each patient to evidence-matched "
     "therapies and recruiting trials.", size=14, color=FAINT, spacing=1.25)

# stat strip
y = Inches(5.0)
stats = [("26,064", "labeled patients", "MSK-IMPACT + MSK-CHORD"),
         ("0.781", "held-out ROC-AUC", "5,213-patient test set"),
         ("201", "genomic + clinical", "model features"),
         ("8", "HGB models", "+ isotonic calibration")]
for i, (v, l1, l2) in enumerate(stats):
    x = Inches(0.62) + Inches(3.05) * i
    card(s, x, y, Inches(2.85), Inches(1.15))
    text(s, x + Inches(0.2), y + Inches(0.14), Inches(2.5), Inches(0.45),
         v, size=24, color=ACCENT_TXT, font=MONO, bold=True)
    text(s, x + Inches(0.2), y + Inches(0.6), Inches(2.55), Inches(0.5),
         [(l1.upper() + "\n", {"color": TEXT, "bold": True, "size": 9.5}),
          (l2, {"color": MUTED, "size": 9})], spacing=1.15)

hline(s, Inches(0.62), Inches(6.65), Inches(12.1))
text(s, Inches(0.62), Inches(6.8), Inches(12), Inches(0.35),
     "Abhinav Mishra · built with Python, scikit-learn, and Streamlit · "
     "trained on public de-identified data (cBioPortal)", size=10.5,
     color=MUTED)

# =====================================================================
# SLIDE 2 — PROBLEM
# =====================================================================
s = slide()
header(s, "The problem", "Cancer treatment is still guesswork.",
       "About 2 million Americans are diagnosed with cancer each year. In "
       "advanced disease, acquired drug resistance is a leading cause of "
       "treatment failure.")

cards = [
    ("Too much data",
     "A tumor's sequencing report lists hundreds of alterations. No tumor "
     "board can deeply review every patient's genome."),
    ("Too slow",
     "Choosing the post-progression regimen can take days — and molecular "
     "tumor boards exist mostly at major cancer centers."),
    ("No foresight",
     "Clinicians can't see which regimen is likely to fail until the "
     "patient has already failed it."),
]
for i, (t, d) in enumerate(cards):
    x = Inches(0.62) + Inches(4.12) * i
    card(s, x, Inches(2.1), Inches(3.9), Inches(2.5))
    hline(s, x, Inches(2.1), Inches(0.08), ACCENT)
    text(s, x + Inches(0.28), Inches(2.4), Inches(3.4), Inches(0.4), t,
         size=17, bold=True)
    text(s, x + Inches(0.28), Inches(2.95), Inches(3.35), Inches(1.5), d,
         size=12.5, color=MUTED, spacing=1.3)

card(s, Inches(0.62), Inches(5.1), Inches(12.1), Inches(1.35), fill=INSET)
text(s, Inches(0.95), Inches(5.4), Inches(11.5), Inches(0.8),
     [("The next therapy is chosen by reading the tumor's genome. ",
       {"color": TEXT, "bold": True}),
      ("Molecular tumor boards do that review today — but their expertise "
       "is scarce, slow, and unevenly available. ResistanceAI puts that "
       "review into software.", {"color": MUTED})],
     size=14.5, spacing=1.3)
footer(s, 2)

# =====================================================================
# SLIDE 3 — SOLUTION
# =====================================================================
s = slide()
header(s, "The solution", "A tumor-board workup, in software.")

bullets(s, Inches(0.62), Inches(2.15), Inches(6.6), Inches(4),
        [("Calibrated risk",
          "the probability the next regimen fails — a real percentage, "
          "not a black-box score"),
         ("The reasons",
          "which of this patient's alterations raise or lower the "
          "estimate, plus the escape mechanisms behind them"),
         ("The options",
          "evidence-ranked regimens and live recruiting trials matched "
          "to the profile"),
         ("The receipts",
          "what actually happened to the most similar real patients")],
        size=14, gap=0.95)

sx = Inches(7.7)
for i, (v, l) in enumerate([("26,064", "labeled patients — MSK-IMPACT + CHORD"),
                            ("0.781", "held-out ROC-AUC · PR-AUC 0.815"),
                            ("201", "genomic + clinical features"),
                            ("20", "curated resistance-mechanism rules")]):
    x = sx + Inches(2.55) * (i % 2)
    yy = Inches(2.15) + Inches(1.25) * (i // 2)
    stat_card(s, x, yy, Inches(2.4), v, l, vcolor=ACCENT_TXT, num_size=22)

text(s, sx, Inches(4.95), Inches(4.95), Inches(1.4),
     "Every number on screen is computed live from the loaded patient — "
     "nothing is mocked or hard-coded.", size=12, color=FAINT, spacing=1.3)
footer(s, 3)

# =====================================================================
# SLIDE 4 — SEE IT LIVE
# =====================================================================
s = slide()
header(s, "Live demo", "One click. A real patient. Every tab.")

p = SHOTS / "v9_landing.png"
w, h = img_w_for(p, 0, 0, w=Inches(7.4))
picture(s, p, Inches(0.62), Inches(1.95), w, h)

rx = Inches(8.35)
steps = [
    ("01", "Load a case",
     "80-case worklist of real sequenced patients, an NGS report upload, "
     "or the one-click demo patient."),
    ("02", "Read the assessment",
     "Calibrated risk + interval, the driving alterations, mechanism "
     "hypotheses, observed outcomes."),
    ("03", "Compare the options",
     "Matched therapies, recruiting trials, similar-patient outcomes, "
     "and a board-ready dossier."),
]
for i, (n, t, d) in enumerate(steps):
    yy = Inches(2.0) + Inches(1.5) * i
    text(s, rx, yy, Inches(0.7), Inches(0.5), n, size=20, color=ACCENT_TXT,
         font=MONO, bold=True)
    text(s, rx + Inches(0.75), yy + Inches(0.02), Inches(4), Inches(0.4), t,
         size=15.5, bold=True)
    text(s, rx + Inches(0.75), yy + Inches(0.42), Inches(4.15), Inches(0.95),
         d, size=11.5, color=MUTED, spacing=1.2)

card(s, rx, Inches(6.0), Inches(4.35), Inches(0.75), fill=INSET)
text(s, rx + Inches(0.22), Inches(6.18), Inches(4.0), Inches(0.5),
     "The demo patient is a real de-identified MSK-CHORD case — "
     "P-0045862, lung adenocarcinoma.", size=10.5, color=FAINT, spacing=1.15)
footer(s, 4)

# =====================================================================
# SLIDE 5 — INSIDE THE ASSESSMENT
# =====================================================================
s = slide()
header(s, "What the board sees", "The assessment: a number you can defend.")

p = SHOTS / "v9_risk.png"
w, h = img_w_for(p, 0, 0, w=Inches(7.9))
picture(s, p, Inches(0.62), Inches(1.95), w, h)

rx = Inches(8.9)
callouts = [
    ("Calibrated 53%",
     "isotonic-calibrated probability + ensemble interval — the model "
     "flags its own uncertainty"),
    ("Plain-language takeaway",
     "one sentence a clinician can read aloud"),
    ("Ablation chart",
     "each feature's measured effect on this patient's score"),
    ("Mechanism hypotheses",
     "published escape routes, each citing the alterations detected"),
    ("Observed outcomes",
     "survival of 26,064 patients by predicted-risk quartile"),
]
for i, (t, d) in enumerate(callouts):
    yy = Inches(2.0) + Inches(0.98) * i
    hline(s, rx, yy + Inches(0.05), Inches(0.06), ACCENT)
    text(s, rx + Inches(0.2), yy, Inches(3.9), Inches(0.35), t, size=13,
         bold=True)
    text(s, rx + Inches(0.2), yy + Inches(0.32), Inches(3.8), Inches(0.6),
         d, size=10.5, color=MUTED, spacing=1.12)
footer(s, 5)

# =====================================================================
# SLIDE 6 — RISK TO ACTION
# =====================================================================
s = slide()
header(s, "From risk to action", "Options, ranked — with receipts.")

p1 = SHOTS / "v9_therapies.png"
w, h = img_w_for(p1, 0, 0, w=Inches(6.05))
picture(s, p1, Inches(0.62), Inches(1.95), w, h)
text(s, Inches(0.62), Inches(6.15), Inches(6.1), Inches(0.5),
     "Evidence-ranked regimens — OncoKB level, NCCN tier, matched "
     "biomarker, and a resistance caveat on every card.", size=10.5,
     color=MUTED, spacing=1.15)

p2 = SHOTS / "v9_twins.png"
w, h = img_w_for(p2, 0, 0, w=Inches(6.05))
picture(s, p2, Inches(6.95), Inches(1.95), w, h)
text(s, Inches(6.95), Inches(6.15), Inches(6.1), Inches(0.5),
     "The 8 most similar real patients — 38% observed failure rate — "
     "and live ClinicalTrials.gov matches for the same biomarkers.",
     size=10.5, color=MUTED, spacing=1.15)
footer(s, 6)

# =====================================================================
# SLIDE 7 — PIPELINE
# =====================================================================
s = slide()
header(s, "Under the hood", "How it works end-to-end.")

flow = [
    ("Case intake", "worklist · NGS JSON\nupload · what-if"),
    ("Normalize", "201-column\nfeature vector"),
    ("Ensemble", "HistGradient-\nBoosting ×8"),
    ("Calibrate", "isotonic\nregression"),
    ("Explain", "ablation +\nmechanism rules"),
    ("Act", "therapies ·\ntrials · twins"),
]
bx, bw, gap = Inches(0.62), Inches(1.88), Inches(0.16)
for i, (t, d) in enumerate(flow):
    x = bx + (bw + gap) * i
    card(s, x, Inches(2.15), bw, Inches(1.5))
    text(s, x, Inches(2.35), bw, Inches(0.4), t, size=13.5, bold=True,
         align=PP_ALIGN.CENTER)
    text(s, x, Inches(2.8), bw, Inches(0.75), d, size=9.5, color=MUTED,
         align=PP_ALIGN.CENTER, font=MONO, spacing=1.1)
    if i < len(flow) - 1:
        text(s, x + bw - Inches(0.02), Inches(2.7), gap + Inches(0.1),
             Inches(0.5), "›", size=20, color=ACCENT, bold=True,
             align=PP_ALIGN.CENTER)

eyebrow(s, Inches(0.62), Inches(4.15), "backend/ — the pure-logic layer "
        "behind every screen")
mods = [("predictor.py", "calibrated ensemble + interval + attribution"),
        ("features.py", "201-col schema · input normalization"),
        ("mechanisms.py", "20 published escape-mechanism rules"),
        ("digital_twin.py", "k-nearest real patients + outcomes"),
        ("trial_engine.py", "live ClinicalTrials.gov v2 client"),
        ("cohort_analytics.py", "biomarker queries + KM survival"),
        ("data_ingestion.py", "NGS report + corpus ingest"),
        ("institutional_db.py", "audit + decision ledger")]
for i, (f, d) in enumerate(mods):
    x = Inches(0.62) + Inches(3.1) * (i % 4)
    yy = Inches(4.55) + Inches(0.95) * (i // 4)
    text(s, x, yy, Inches(3.0), Inches(0.35), f, size=11.5, color=ACCENT_TXT,
         font=MONO, bold=True)
    text(s, x, yy + Inches(0.3), Inches(2.95), Inches(0.6), d, size=9.5,
         color=MUTED, spacing=1.1)
footer(s, 7)

# =====================================================================
# SLIDE 8 — CODE: MODEL
# =====================================================================
s = slide()
header(s, "Behind the scenes — the model",
       "A calibrated ensemble, not a black box.")

code_card(s, Inches(0.62), Inches(1.95), Inches(7.3), Inches(4.3),
          "backend/predictor.py",
          ["ens = np.array([m.predict_proba(x)[:, 1][0]",
           "                 for m in self.models])   # 8 bagged models",
           "raw = float(ens.mean())",
           "proba = float(self.isotonic.predict([raw])[0])",
           "spread = float(ens.std())   # ensemble disagreement",
           "risk_score = int(round(proba * 100))",
           "ci_half = max(2, int(round(1.645 * spread * 100)))",
           "percentile = np.searchsorted(",
           "    self.cohort_risk, proba) / len(self.cohort_risk) * 100",
           "",
           "# ... then: mechanisms, ablation attributions,",
           "# therapy matching, risk tier + interpretation"])

rx = Inches(8.25)
notes = [
    ("Ensemble vote",
     "8 HistGradientBoosting models trained on 15,638 patients vote "
     "independently."),
    ("Isotonic calibration",
     "a regression fit on held-out folds maps votes to true "
     "probabilities — 53% really means ~53% (ECE 0.017)."),
    ("Honest interval",
     "ensemble disagreement becomes the ± band; unusual profiles get "
     "wide intervals, not fake precision."),
    ("Cohort percentile",
     "the score is placed against 5,213 real held-out patients — "
     "nobody is scored by a model that saw their record."),
]
for i, (t, d) in enumerate(notes):
    yy = Inches(2.0) + Inches(1.12) * i
    text(s, rx, yy, Inches(4.4), Inches(0.35), t, size=13, bold=True,
         color=ACCENT_TXT)
    text(s, rx, yy + Inches(0.32), Inches(4.45), Inches(0.75), d, size=10.5,
         color=MUTED, spacing=1.15)
footer(s, 8)

# =====================================================================
# SLIDE 9 — CODE: REASONING
# =====================================================================
s = slide()
header(s, "Behind the scenes — the reasoning",
       "Mechanism rules + evidence matching.")

code_card(s, Inches(0.62), Inches(1.95), Inches(7.3), Inches(4.3),
          "backend/mechanisms.py — one of 20 curated rules",
          ["{",
           "  \"id\": \"sclc_transformation\",",
           "  \"mechanism\": \"Neuroendocrine (SCLC) transformation\",",
           "  \"when\": {\"genes_all\": {\"RB1\", \"TP53\"},",
           "             \"genes_driver\": {\"EGFR\", \"ALK\", \"ROS1\"}},",
           "  \"implication\": \"Complete RB1 loss with TP53 in an",
           "     EGFR/ALK-driven adenocarcinoma is the genomic",
           "     signature of small-cell transformation.\",",
           "  \"strategy\": \"Re-biopsy; platinum-etoposide",
           "     + atezolizumab if transformed.\",",
           "  \"level\": \"established\",",
           "}  # fires only if EVERY 'when' clause holds —",
           "  # and must cite the detected alterations as evidence"])

rx = Inches(8.25)
notes = [
    ("Curated, not learned",
     "20 escape mechanisms from the literature — bypass tracks, "
     "on-target reactivation, lineage transformation, immune exclusion."),
    ("Evidence or silence",
     "a hypothesis renders only with the patient's alterations listed "
     "beside it — no evidence, no claim."),
    ("Counterweights",
     "sensitivity rules (BRCA/HRD → PARP, MSI/POLE → checkpoint) "
     "balance the resistance story."),
    ("Therapy matcher",
     "the same alterations query a curated knowledge base — OncoKB "
     "levels, NCCN tiers, line of therapy."),
]
for i, (t, d) in enumerate(notes):
    yy = Inches(2.0) + Inches(1.12) * i
    text(s, rx, yy, Inches(4.4), Inches(0.35), t, size=13, bold=True,
         color=ACCENT_TXT)
    text(s, rx, yy + Inches(0.32), Inches(4.45), Inches(0.75), d, size=10.5,
         color=MUTED, spacing=1.15)
footer(s, 9)

# =====================================================================
# SLIDE 10 — TRUST / RESULTS
# =====================================================================
s = slide()
header(s, "Does it hold up?", "Honest numbers, built-in safeguards.")

p = SHOTS / "v9_model.png"
w, h = img_w_for(p, 0, 0, w=Inches(7.0))
picture(s, p, Inches(0.62), Inches(1.95), w, h)

rx = Inches(8.0)
l_items = [
    ("Held-out only", "every metric comes from 5,213 test patients the "
     "model never trained on"),
    ("Calibrated", "the calibration curve hugs the diagonal — "
     "ECE 0.017, Brier 0.183"),
    ("Leakage-safe", "survival curves use out-of-fold predictions; "
     "twins can't match themselves"),
    ("Privacy floor", "cohorts under 5 patients suppress outcome stats"),
    ("Accountable", "local audit ledger logs every inference and board "
     "decision"),
]
for i, (t, d) in enumerate(l_items):
    yy = Inches(2.0) + Inches(0.98) * i
    hline(s, rx, yy + Inches(0.05), Inches(0.06), POS)
    text(s, rx + Inches(0.2), yy, Inches(4.3), Inches(0.35), t, size=13,
         bold=True)
    text(s, rx + Inches(0.2), yy + Inches(0.32), Inches(4.3), Inches(0.6),
         d, size=10.5, color=MUTED, spacing=1.12)
footer(s, 10)

# =====================================================================
# SLIDE 11 — CLOSE
# =====================================================================
s = slide()

eyebrow(s, Inches(0.62), Inches(0.7), "ResistanceAI", ACCENT_TXT)
text(s, Inches(0.6), Inches(1.15), Inches(12.4), Inches(1.4),
     "From a genome to a defensible\nnext step.", size=44, bold=True,
     spacing=1.05)
text(s, Inches(0.64), Inches(2.85), Inches(11.5), Inches(0.6),
     "Every screen in this video is the running app — real data, real "
     "model, real code. Nothing mocked.", size=15, color=MUTED, spacing=1.25)

recap = [("Risk", "calibrated % + interval"),
         ("Why", "ablation + mechanism rules"),
         ("Options", "therapies + live trials"),
         ("Evidence", "similar-patient outcomes"),
         ("Safeguards", "audit, privacy floor, banner")]
for i, (t, d) in enumerate(recap):
    x = Inches(0.62) + Inches(2.48) * i
    card(s, x, Inches(4.0), Inches(2.3), Inches(1.0))
    text(s, x + Inches(0.18), Inches(4.14), Inches(2.0), Inches(0.35), t,
         size=13, bold=True, color=ACCENT_TXT)
    text(s, x + Inches(0.18), Inches(4.5), Inches(2.0), Inches(0.45), d,
         size=9.5, color=MUTED, spacing=1.1)

card(s, Inches(0.62), Inches(5.5), Inches(12.1), Inches(0.9), fill=INSET)
text(s, Inches(0.95), Inches(5.72), Inches(11.5), Inches(0.5),
     [("DEMO — running live:  ", {"color": ACCENT_TXT, "bold": True}),
      ("Load a demo patient → Risk summary → Therapy options → "
       "Similar patients → Model performance", {"color": TEXT})],
     size=13.5, spacing=1.1)

hline(s, Inches(0.62), Inches(6.75), Inches(12.1))
text(s, Inches(0.62), Inches(6.9), Inches(12.1), Inches(0.35),
     "Investigational research prototype — all outputs require oncologist "
     "review. Trained on public de-identified MSK-IMPACT + MSK-CHORD data.",
     size=9.5, color=FAINT)

prs.save(OUT)
print(f"wrote {OUT} ({len(prs.slides.__iter__.__self__._sldIdLst)} slides)")
