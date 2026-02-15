# How ResistanceAI Works — A Plain-English Guide

> ResistanceAI is a tool that helps cancer doctors figure out whether a patient's treatment is likely to stop working, and if so, what better options might exist.

---

## What Problem Does This Solve?

Cancer treatments don't always keep working. Sometimes a tumor learns to fight back against the medicine — this is called **resistance**. Doctors need help predicting when this will happen so they can choose the right treatment the first time.

ResistanceAI is like a **smart assistant for cancer doctors**. It looks at a patient's medical information and says:

- "There's a **72% chance** this tumor will resist the standard treatment."
- "Based on the patient's specific tumor, here are **better treatment options** backed by medical research."
- "Here are **active research studies** this patient might qualify for."

---

## What Goes In? (Inputs)

The system needs two main things about each patient:

### 1. Basic Medical Info
- **What type of cancer** they have (lung, breast, colon, etc.)
- **How old they were** when diagnosed
- **How far the cancer has spread** (Stage I through IV — Stage I is early, Stage IV has spread the most)

### 2. Tumor Lab Results
These come from a lab test that reads the DNA of the tumor:

- **Mutation count** — How many DNA errors the tumor has. More errors can mean the tumor changes faster and may dodge treatment.
- **Specific gene changes** — Certain genes (like EGFR or BRCA) have known treatments that target them directly.
- **DNA repair ability** — Some tumors can't fix their own DNA. This actually makes them *more* vulnerable to certain drugs.
- **Mutation pattern** — The types of DNA letter-swaps happening in the tumor (for example, a lot of C→T changes can indicate specific damage patterns).

---

## What Comes Out? (Outputs)

| What You Get | What It Means |
|---|---|
| **Risk Score (0–100%)** | How likely the cancer is to resist standard treatment. Higher = more likely to resist. |
| **Risk Level** | A simple label: Low, Moderate, or High. |
| **Treatment Suggestions** | A list of specific medications matched to that patient's tumor profile, with links to the medical research behind each one. |
| **Matching Research Studies** | Real clinical trials the patient might be eligible for, pulled live from a government database. |
| **Board-Ready Report** | A summary document doctors can bring to their team meeting where they discuss the case. |

---

## How Data Flows Through the System

Here's the journey from start to finish, in plain English:

```
 ┌─────────────────────────────────────────────────────────┐
 │                    THE BIG PICTURE                      │
 │                                                         │
 │   Patient Info  ──▶  AI Brain  ──▶  Recommendations     │
 │   (what goes in)    (thinking)     (what comes out)     │
 └─────────────────────────────────────────────────────────┘
```

### Step 1 — Pick a Patient

The doctor opens the app and sees a list of patients waiting to be reviewed. They click on one. The system immediately pulls up that patient's medical record — their cancer type, age, tumor stage, and any known gene changes.

*Think of it like pulling up a student's file in a school office.*

### Step 2 — Prepare the Data

The patient's information gets organized into a standard format that the AI can understand. Raw lab numbers get sorted into buckets:

- A mutation count of **3** becomes "Low"
- A mutation count of **15** becomes "Intermediate-High"
- A mutation count of **25** becomes "High"

This is like converting letter grades to numbers — it makes everything comparable.

### Step 3 — Ask the AI

The organized patient data gets fed into a **prediction model**. This model was trained by studying **thousands of past cancer cases** where we already know the outcome. It learned patterns like:

- *"Patients with high mutation counts AND late-stage cancer AND this gene change tend to resist treatment 80% of the time."*
- *"Patients with low mutation counts AND early-stage cancer tend to respond well."*

The model spits out a **risk score** (like 72%) and also tells us **which factors mattered most** for that particular patient. Maybe it was mainly the gene change, or maybe it was the cancer stage.

*Think of it like a weather forecast — the model looks at many past patterns to predict what's likely to happen next.*

### Step 4 — Look Up the Best Treatments

Now the system takes the patient's specific tumor details and searches through a **medical guidebook** built into the app. This guidebook contains:

- Which drugs are approved for which gene changes
- How strong the evidence is for each drug
- What major medical studies support each recommendation

For example:
- Patient has an **EGFR gene change** in lung cancer → the system recommends **Osimertinib**, a pill that specifically blocks EGFR.
- Patient has **BRCA gene damage** in ovarian cancer → the system recommends **Niraparib**, a drug that attacks cells that can't repair their own DNA.

If no specific match is found, the system defaults to recommending standard chemotherapy.

*This is like a recipe book — "If you have these ingredients (gene changes), here's the best dish (treatment) to make."*

### Step 5 — Search for Research Studies

The system also reaches out to a **government database of clinical trials** (ClinicalTrials.gov) to find active research studies that match the patient's cancer type and gene changes. It searches in real time and brings back up to 50 matching studies.

If the internet connection fails, it falls back to a smaller list of studies stored locally on the computer.

*Think of it like searching for scholarships — you enter your profile and it finds programs you're eligible for.*

### Step 6 — Show Everything on the Dashboard

All of the results are displayed on a visual dashboard with multiple tabs:

| Tab | What It Shows |
|---|---|
| **Snapshot** | The risk score with charts showing which factors contributed most |
| **Pathways** | Treatment suggestions and matching clinical trials |
| **Molecular Workbench** | A detailed view of the tumor's DNA changes |
| **Board Packet** | Tools to prepare a summary for the doctor's team meeting |
| **Real-World Evidence** | How well the AI's past suggestions have performed across hundreds of patients |
| **Validation** | Testing tools to measure the AI's accuracy |

### Step 7 — Save Everything

Every action is recorded in log files:

- What the AI recommended
- What the doctors actually decided
- Whether the AI and doctors agreed
- A security log of who accessed what and when (for patient privacy compliance)

This record-keeping serves two purposes:
1. **Accountability** — there's always a paper trail.
2. **Learning** — over time, the team can see whether patients do better when doctors follow the AI's suggestions vs. when they don't.

---

## How the AI Learned in the First Place

Before the app can help anyone, the AI model had to be **trained**. Here's how that happened:

```
  Thousands of past          Clean & organize         Train the AI
  patient records    ──▶     the data          ──▶    to find patterns
  (real hospital data)       (standardize it)         (machine learning)
        │                          │                         │
        ▼                          ▼                         ▼
  "Patient A had               "Cancer: lung,           "I learned that
   lung cancer,                 Mutations: high,         high mutations +
   high mutations,              Stage: IV,               late stage =
   died in 8 months"            Resisted: yes"           likely resistance"
```

1. **Collect real data** — Records from over 1,000 real cancer patients (names removed for privacy) were gathered from a major cancer hospital (Memorial Sloan Kettering).

2. **Label the outcomes** — Each patient was marked as either "resisted treatment" or "responded to treatment," based on how long they survived.

3. **Teach the model** — A machine learning algorithm studied all these labeled examples. It tried many different combinations of settings to find the most accurate version of itself. It was tested on patients it had never seen before to make sure it wasn't just memorizing.

4. **Save the trained model** — The final trained model is saved as a file that the app loads when it starts up. It's about 5 megabytes — smaller than a single photo.

---

## The Whole Journey in One Picture

```
  ┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
  │  DOCTOR      │     │  THE APP     │     │  WHAT HAPPENS    │
  │  DOES THIS   │     │  DOES THIS   │     │  BEHIND SCENES   │
  ├──────────────┤     ├──────────────┤     ├──────────────────┤
  │              │     │              │     │                  │
  │ Selects a    │────▶│ Pulls up     │────▶│ Formats patient  │
  │ patient      │     │ their record │     │ data for the AI  │
  │              │     │              │     │                  │
  │              │     │ Runs the     │────▶│ AI model scores  │
  │              │     │ prediction   │     │ resistance risk  │
  │              │     │              │     │                  │
  │              │     │ Looks up     │────▶│ Matches genes to │
  │              │     │ treatments   │     │ approved drugs   │
  │              │     │              │     │                  │
  │              │     │ Searches for │────▶│ Queries a live   │
  │              │     │ trials       │     │ government DB    │
  │              │     │              │     │                  │
  │ Reviews      │◀────│ Shows        │     │ Saves a log of   │
  │ results      │     │ dashboard    │────▶│ everything that  │
  │              │     │              │     │ happened         │
  │ Makes a      │────▶│ Records the  │     │                  │
  │ decision     │     │ decision     │────▶│ Stores it for    │
  │              │     │              │     │ future learning  │
  └──────────────┘     └──────────────┘     └──────────────────┘
```

---

## Key Takeaways

- **No diagnosis is made by the AI alone.** It gives suggestions — doctors make the final call.
- **The AI explains its reasoning.** It doesn't just give a number; it shows which factors pushed the score up or down.
- **Everything is recorded.** There's a complete history of every recommendation and every decision for safety and accountability.
- **It gets better over time.** By tracking whether patients do better when doctors follow the AI's advice, the system can prove (or disprove) its own value.

---

> *This tool is for research purposes only. It is not a replacement for a doctor's judgment. All recommendations must be reviewed by a qualified medical professional.*
