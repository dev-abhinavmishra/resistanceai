"""
Builds ResistanceAI_Presentation_v9.pptx for the Congressional App Challenge video.

Written for a general audience: no oncology background assumed.
Slide titles are full sentences; detail lives in speaker notes.

Run:  python deck/build_deck.py
Deps: pip install python-pptx pillow
"""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from PIL import Image
from pathlib import Path

# ---------- theme: 2 fonts, 1 dark + 1 light + 1 accent ----------
BG     = RGBColor(0x0F, 0x17, 0x2A)
SURF   = RGBColor(0x1E, 0x29, 0x3B)
LINE   = RGBColor(0x2B, 0x3A, 0x52)
TXT    = RGBColor(0xF1, 0xF5, 0xF9)
MUT    = RGBColor(0x94, 0xA3, 0xB8)
ACC    = RGBColor(0x3B, 0x82, 0xF6)
ACCTXT = RGBColor(0x60, 0xA5, 0xFA)

UI   = "Segoe UI"
MONO = "Consolas"

ROOT = Path(__file__).resolve().parents[1]
SHOT = ROOT / "docs" / "screenshots"
OUT  = ROOT / "ResistanceAI_Presentation_v9.pptx"

prs = Presentation()
prs.slide_width  = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]


def slide():
    s = prs.slides.add_slide(BLANK)
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = BG
    return s


def box(s, x, y, w, h, fill=SURF, line=None, round_=False):
    shp = s.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if round_ else MSO_SHAPE.RECTANGLE,
        Inches(x), Inches(y), Inches(w), Inches(h))
    if round_:
        try:
            shp.adjustments[0] = 0.05
        except Exception:
            pass
    if fill is None:
        shp.fill.background()
    else:
        shp.fill.solid()
        shp.fill.fore_color.rgb = fill
    if line:
        shp.line.color.rgb = line
        shp.line.width = Pt(1)
    else:
        shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def text(s, x, y, w, h, runs, size=24, bold=False, color=TXT, font=UI,
         align=PP_ALIGN.LEFT, spacing=1.08, sp_after=8, anchor=MSO_ANCHOR.TOP,
         wrap=True):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = wrap
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    if isinstance(runs, str):
        runs = [runs]
    first = True
    for run in runs:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.alignment = align
        p.line_spacing = spacing
        p.space_after = Pt(sp_after)
        if isinstance(run, tuple):
            t, kw = run
        else:
            t, kw = run, {}
        r = p.add_run()
        r.text = t
        f = r.font
        f.size = Pt(kw.get("size", size))
        f.bold = kw.get("bold", bold)
        f.color.rgb = kw.get("color", color)
        f.name = kw.get("font", font)
    return tb


def title(s, txt, sub=None):
    text(s, 0.75, 0.55, 11.85, 1.0, txt, size=40, bold=True, spacing=1.0)
    if sub:
        text(s, 0.78, 1.55, 11.6, 0.5, sub, size=20, color=MUT)


def src_line(s, txt, y=7.05):
    text(s, 0.75, y, 11.85, 0.35, txt, size=12, color=MUT)


def pic(s, path, x, y, w, line=True):
    with Image.open(path) as im:
        ih = w * im.height / im.width
    s.shapes.add_picture(path, Inches(x), Inches(y), width=Inches(w))
    if line:
        box(s, x, y, w, ih, fill=None, line=LINE)
    return ih


def notes(s, txt):
    s.notes_slide.notes_text_frame.text = txt


# ================= 1. TITLE =================
s = slide()
box(s, 0, 0, 13.333, 0.09, fill=ACC)
text(s, 0.75, 1.7, 11.8, 0.5, "CONGRESSIONAL APP CHALLENGE",
     size=18, color=ACCTXT, bold=True)
text(s, 0.75, 2.35, 11.8, 1.4, "ResistanceAI", size=66, bold=True)
text(s, 0.78, 3.75, 10.8, 1.2,
     "Software that helps cancer doctors choose treatments "
     "less likely to fail.", size=30, color=MUT, spacing=1.15)
text(s, 0.78, 5.9, 11.8, 0.5,
     "Abhinav Mishra     Python and Streamlit     trained on free public data",
     size=18, color=MUT)
notes(s, "Hi, I'm Abhinav. Doctors who treat cancer face a hard problem: even "
         "with a tumor's DNA report in hand, it is hard to know which drug will "
         "actually work. I built a small app that estimates that up front. "
         "In about three minutes I will show you the whole thing, live.")

# ================= 2. WHAT CANCER IS =================
s = slide()
title(s, "Cancer starts when DNA instructions go wrong.")
text(s, 0.85, 2.15, 11.2, 4.0, [
    "A tumor's DNA is its damaged instruction manual.",
    "Labs can now read that damage letter by letter.",
    "Some DNA errors have drugs built to block them.",
    "Matching the error to the drug is precision oncology.",
], size=26, sp_after=20)
notes(s, "A quick primer for anyone without a biology background. Cancer begins "
         "when a cell's DNA is damaged and the cell grows out of control. "
         "Clinics now sequence a tumor's DNA, and for many of the errors they "
         "find, called mutations, there is a drug designed to hit that exact "
         "weakness. That matching is called precision oncology.")

# ================= 3. THE GAP =================
s = slide()
title(s, "Knowing which drug will work takes experts most hospitals lack.")
text(s, 0.85, 2.15, 7.1, 4.4, [
    "A sequencing report can list hundreds of mutations.",
    "Specialist panels read them, mostly at big centers.",
    "A community oncologist often reads it alone.",
    "A wrong first choice can cost months.",
], size=26, sp_after=20)
box(s, 8.45, 2.1, 4.1, 4.3, round_=True)
text(s, 8.85, 2.55, 3.35, 0.5, "WHAT AN ONCOLOGIST IS",
     size=13, color=ACCTXT, bold=True)
text(s, 8.85, 3.05, 3.35, 3.2, [
    "The doctor who treats cancer.",
    "When the DNA report lands, they choose the drug, often alone.",
], size=24, color=MUT, spacing=1.2)
notes(s, "When a tumor report comes back, a panel of specialists called a "
         "molecular tumor board can review it and recommend a drug. Those "
         "panels mostly exist at large academic cancer centers. The oncologist, "
         "the cancer doctor treating most patients, is often reading that "
         "report alone under time pressure, and a drug that cannot work still "
         "costs the patient weeks on the clock.")

# ================= 4. BIG NUMBER =================
s = slide()
title(s, "So the model learned from real patients, not rules I wrote.")
text(s, 0.75, 2.35, 7.4, 2.2, "26,064", size=120, bold=True, font=MONO,
     color=ACCTXT)
text(s, 0.8, 4.95, 7.4, 1.2,
     "cancer patients whose tumors were sequenced, "
     "with outcomes on record.", size=26, color=TXT, spacing=1.15)
box(s, 8.5, 2.55, 4.05, 3.5, round_=True)
text(s, 8.9, 2.95, 3.3, 0.45, "WHERE THE DATA CAME FROM",
     size=13, color=ACCTXT, bold=True)
text(s, 8.9, 3.45, 3.3, 2.4,
     "Two public datasets from Memorial Sloan Kettering, "
     "one of the largest cancer centers in the world.",
     size=24, color=MUT, spacing=1.2)
src_line(s, "Source: MSK-IMPACT (Zehir et al., Nat Med 2017) and MSK-CHORD "
            "(Nature 2024) via cBioPortal.")
notes(s, "Instead of writing rules by hand, I trained the model on two public "
         "datasets from Memorial Sloan Kettering Cancer Center: MSK-IMPACT "
         "and MSK-CHORD. After cleaning, 26,064 patients had both a sequenced "
         "tumor and a recorded outcome. Every number the app produces traces "
         "back to those real cases.")

# ================= 5. THE PRODUCT =================
s = slide()
title(s, "It estimates the chance the next treatment fails.")
pic(s, str(SHOT / "v9_risk_full.png"), 0.7, 1.95, 8.25)
text(s, 9.3, 2.4, 3.3, 3.8, [
    "Load a patient in one click.",
    "One read: 53 percent.",
    "Plus an honest range.",
], size=24, sp_after=20)
notes(s, "Here it is running. I load a real lung cancer patient and the app "
         "scores a 53 percent chance the next treatment fails. Notice the "
         "range beside it: the model is honest that this profile is unusual, "
         "and unusual is exactly when a doctor should slow down.")

# ================= 6. IT SHOWS ITS WORK =================
s = slide()
title(s, "It shows exactly which evidence moved the number.")
pic(s, str(SHOT / "v9_attrib.png"), 1.75, 1.8, 9.85)
text(s, 0.85, 6.95, 11.6, 0.45,
     "Left: what moved the score.   Right: the cited evidence.",
     size=24, color=MUT, align=PP_ALIGN.CENTER)
notes(s, "Judges and doctors ask the same question: why this number. The chart "
         "on the left removes each feature one at a time and measures how much "
         "the score moves. The cards on the right name biological escape "
         "routes the tumor might use, and each card cites the specific "
         "mutation it found in this patient's DNA.")

# ================= 7. WHAT TO TRY NEXT =================
s = slide()
title(s, "Then it lines up what is worth trying next.")
pic(s, str(SHOT / "v9_therapies.png"), 0.75, 1.75, 6.0)
pic(s, str(SHOT / "v9_twins.png"),     6.95, 1.75, 5.9)
text(s, 0.85, 6.35, 11.6, 0.9,
     "Drugs matched to this tumor's mutations.   "
     "Recruiting trials, searched live.   "
     "Outcomes of similar patients.",
     size=24, color=MUT)
notes(s, "A risk score alone does not help anyone act. So the app maps the "
         "patient's mutations to treatment regimens with their evidence "
         "grades, searches ClinicalTrials.gov live for recruiting studies, "
         "and shows what actually happened to the eight most similar patients "
         "in the data.")

# ================= 8. HOW IT WORKS (diagram) =================
s = slide()
title(s, "Behind the screen, four steps a doctor can inspect.")
steps = [("DNA report", "sequencing file"),
         ("201 signals", "mutations and history"),
         ("8 models vote", "each sees different patients"),
         ("Probability", "calibrated, with a range")]
bx, bw, bh = 0.85, 2.55, 2.1
for i, (t1, t2) in enumerate(steps):
    x = bx + i * 3.13
    box(s, x, 2.6, bw, bh, round_=True)
    text(s, x, 2.85, bw, 0.7, str(i + 1), size=30, bold=True,
         color=ACCTXT, font=MONO, align=PP_ALIGN.CENTER)
    text(s, x + 0.15, 3.5, bw - 0.3, 0.7, t1, size=24, bold=True,
         align=PP_ALIGN.CENTER)
    text(s, x + 0.15, 4.15, bw - 0.3, 0.55, t2, size=15, color=MUT,
         align=PP_ALIGN.CENTER)
    if i < 3:
        text(s, x + bw + 0.06, 3.25, 0.6, 0.7, "›", size=36,
             color=ACCTXT, align=PP_ALIGN.CENTER)
text(s, 0.85, 5.35, 11.5, 1.3,
     "Nothing is hidden. Each step leaves a record a clinician can audit.",
     size=24, color=TXT)
notes(s, "Technically the pipeline is four steps. The DNA report is cleaned "
         "into a fixed list of 201 signals. Eight gradient boosting models, "
         "each trained on a different slice of patients, each make a "
         "prediction. A final calibration step turns their average vote into "
         "a true probability: 60 percent means about 60 percent of similar "
         "patients really did fail.")

# ================= 9. CODE =================
s = slide()
title(s, "It even scores how sure it is.")
code = [
    ("# eight models each make a call",                            MUT),
    ("votes = [m.predict_proba(x)[:, 1][0] for m in self.models]", TXT),
    ("proba = self.isotonic.predict([np.mean(votes)])[0]",         TXT),
    ("score = int(round(proba * 100))    # the estimate",          TXT),
    ("",                                                           TXT),
    ("# disagreement becomes the band on screen",                  MUT),
    ("half  = max(2, int(round(1.645 * np.std(votes) * 100)))",    TXT),
    ("ci    = [max(0, score - half), min(100, score + half)]",     TXT),
]
box(s, 0.85, 1.8, 6.7, 4.15, fill=RGBColor(0x0B, 0x10, 0x1E),
    line=LINE, round_=True)
y = 2.0
for t, c in code:
    if t:
        text(s, 1.1, y, 6.2, 0.42, t, size=13, font=MONO, color=c,
             sp_after=0)
    y += 0.45
text(s, 0.9, 6.15, 6.5, 0.5, "backend/predictor.py", size=13, color=MUT,
     font=MONO)
text(s, 8.05, 2.0, 4.5, 4.2, [
    "Eight models vote; their average becomes the score.",
    "Their disagreement sets the band's width.",
    "A wide band means slow down and look closer.",
], size=24, sp_after=22)
notes(s, "This is the honest part, in the actual code. The eight models vote, "
         "their average is calibrated into a probability, and how much they "
         "disagree sets the width of the band on screen. It is a disagreement "
         "measure, not a guarantee, and the app never pretends to be sure "
         "when it is not.")

# ================= 10. THE REPORT CARD =================
s = slide()
title(s, "Tested on patients it never saw, the numbers hold.")
pic(s, str(SHOT / "chart_calibration.png"), 0.8, 1.85, 6.3)
text(s, 7.55, 2.15, 5.0, 4.3, [
    ("When it said 60%, about 60% failed.", {"size": 25}),
    ("Graded on 5,213 patients it never trained on.", {"size": 25}),
    ("Those limits are printed inside the app.", {"size": 25}),
], sp_after=24)
src_line(s, "Source: backend/artifacts/model_metrics.json. "
            "ROC AUC 0.78, calibration error 0.017.")
notes(s, "Here is the report card on 5,213 patients the model never trained "
         "on. Each dot asks the same question: when the model predicted a "
         "number, what share of patients actually failed. The dots sit near "
         "the diagonal, which is what honest probability looks like. It is "
         "not a crystal ball, and the app says that on the screen.")

# ================= 11. CLOSE =================
s = slide()
box(s, 0, 7.35, 13.333, 0.15, fill=ACC)
text(s, 0.75, 2.1, 11.8, 1.3,
     "Doctors should not have to guess alone.", size=44, bold=True)
text(s, 0.78, 3.6, 11.5, 1.6, [
    "Free public data. Open code. Real patients.",
    "Watch it live: load a demo patient and judge for yourself.",
], size=26, color=MUT, sp_after=14)
notes(s, "That is ResistanceAI. It gives a doctor the kind of read an expert "
         "panel would give, in seconds, with the reasoning left on the "
         "screen. Everything you saw is the running app on real public data. "
         "Thanks for watching.")

# ================= 12. SOURCES =================
s = slide()
title(s, "Sources")
text(s, 0.85, 1.95, 11.6, 4.9, [
    "Zehir et al. MSK-IMPACT cohort, Nature Medicine 2017, via cBioPortal.",
    "MSK-CHORD cohort, Nature 2024, PMID 39506116, via cBioPortal.",
    "ClinicalTrials.gov API v2, US National Library of Medicine.",
    "Evaluation: backend/artifacts/model_metrics.json, test n = 5,213.",
    "Screenshots captured from the running app.",
], size=24, color=MUT, sp_after=16)
notes(s, "Every number in this deck traces to one of these sources or to the "
         "app's own evaluation artifacts in the repository.")

prs.save(OUT)
print(f"saved {OUT}  |  {len(prs.slides._sldIdLst)} slides")
