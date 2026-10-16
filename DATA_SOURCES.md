# ResistanceAI — Training Data & External Sources

## Datasets currently integrated

| Dataset | N | Modalities used | Source | Role |
|---|---|---|---|---|
| **MSK-IMPACT 2017** (in repo) | 10,336 samples | Clinical (sex, smoking, OS), MAF mutations, CNA matrix, SV table | cBioPortal public study `msk_impact_2017` (**ODbL** — share/modify with attribution, LICENSE file in-tree) | Development + label (OS proxy) |
| **MSK-CHORD 2024** (downloaded) | 24,954 patients / 25,040 tumors (24,950 ingested) | Clinical (real age, stage, NLP metastatic sites, PD-L1, HR/HER2), MAF via API (208k mutations), CNA matrix, SV fusions, **treatment timeline (135k rows)**, **NLP progression timeline (399k rows)** | cBioPortal study `msk_chord_2024` (Nature 2024, PMID 39506116, CC BY-NC-ND) | Primary training + **real therapy-outcome labels** |

> **Licensing note.** CHORD is **CC BY-NC-ND**: the raw study, the derived
> `backend/data/*` corpus, **and the trained weights
> `backend/artifacts/resistance_model_v2.pkl`** (a derivative work trained on
> the corpus) are **not committed to git** (`.gitignore`) and must not be
> redistributed — including inside Docker images (`.dockerignore`). Regenerate
> locally via `backend/models/ingest_v2.py` + `backend/models/train_v2.py`;
> commercial use requires an MSK license. Aggregate evaluation metrics
> (`model_metrics.json`, `cohort_stats.json`) contain no row-level data and
> are committed for the validation dashboard.
> MSK-IMPACT 2017 remains in-tree under ODbL (attribution + share-alike;
> LICENSE file included).

### Patient identity across cohorts

MSK-IMPACT and MSK-CHORD assign patients and samples the *same* `P-XXXXXXX`
namespace — 4,272 patient ids and 4,201 sample ids exist in both cohorts and
refer to different people (41 of them with different cancer types). A bare
`patient_id` therefore does **not** identify a unique patient. Every record
carries a cohort field (`impact2017` | `chord`), and all joins, lookups,
queues, and twin tables key on the cohort-qualified uid
`"<cohort>:<patient_id>"` (see `backend/corpus.py:record_uid`). Passing a
bare colliding id to `ingest_ehr_patient` is treated as ambiguous and will
not return a record — always use the qualified uid.

### Known data asymmetries (documented, not hidden)

- **SV burden**: CHORD `data_sv.txt` is fetched only for ~24 fusion-relevant
  genes (`fetch_chord_api.py:FUSION_ENTREZ`), so `sv_count`/`fusions`
  undercount total structural burden vs. IMPACT's full SV table. Treat
  `sv_count` as a fusion-centric feature for CHORD records.
- **Stage granularity**: CHORD ships only `Stage 1-3 | Stage 4 | Unknown`
  (`STAGE_HIGHEST_RECORDED`); ingested as `STAGE 1-3` (ord 2) / `IV` /
  missing. IMPACT uses sample type (metastasis → `IV`, else `II`). API inputs
  share the same encoding via `features.stage_map`.
- **Partial label leakage (stage)**: `STAGE_HIGHEST_RECORDED` is the maximum
  stage observed across the patient's course, not stage at sequencing. For
  patients who progressed to stage 4 *after* their baseline workup, the
  `stage_ord`/`is_metastatic` features partially encode the outcome they are
  meant to predict. They are the strongest feature group (`is_metastatic`
  ΔAUC ≈ 0.13 on permutation), so the reported 0.781 held-out AUC should be
  read as mildly optimistic for the pre-treatment prediction task. Mitigation path: drop or
  counterfactually floor the stage features for CHORD when a
  stage-at-sequencing field becomes available.

### CHORD label construction
For patients with systemic therapy initiated after sequencing:
`resistant = 1` if an NLP-detected progression event occurs ≤12 months after
the first post-sequencing treatment (progression is counted from the first
event at/after treatment start, −30d tolerance), or death ≤18 months;
`0` if progression-free ≥12 months and alive ≥18 months; censored otherwise.
Patients without treatment data fall back to the OS-proxy label
(deceased <24 mo → resistant; living >24 mo → non-resistant; else censored).

### How CHORD was fetched
Clinical/sample/timeline tables come from the cBioPortal datahub GitHub mirror (manual download into `msk_chord_2024/`). `backend/models/fetch_chord_api.py` downloads mutations/SVs via the public cBioPortal REST API (`/mutations/fetch` batched by sample; `/structural-variant/fetch` by fusion-relevant genes).

---

## Additional frontier datasets (integration roadmap)

| Dataset | Why it matters | Access |
|---|---|---|
| **AACR GENIE** (~150k samples, multi-institution) | External validation at scale; the single biggest credibility signal for hospitals | genie.cbioportal.org (free registration) |
| **TCGA PanCanAtlas** (11k, WXS) | RNA-seq + methylation + immune contexture — extends model to transcriptomic features | GDC portal |
| **GDSC / DepMap PRISM** | Drug-response screens on ~1000 cell lines — could power per-compound sensitivity heads | cancerrxgene.org / depmap.org |
| **CIViC / OncoKB** | Curated variant-theraputic-disease annotations — upgrade `treatments.json` to live KB | civicdb.org / oncokb.org (API key) |
| **Project Orbis / real-world EHR (Flatiron, COTA)** | The pharma-grade moat: EMR outcomes at scale | Partnership only — flagged in pitch deck |

---

## Feature surface extracted per patient

`backend/features.py` builds 201 features: driver-gene binaries, CNA event flags, fusion/RTK flags, 10 pathway-activation scores (RTK/RAS, PI3K, cell cycle, DDR, TP53, WNT, NOTCH, chromatin, immune evasion, hormone), 6-class substitution spectrum, FGA/amp/del/SV burden, TMB(log), purity, MSI, stage/age/sex/smoking, cancer-type one-hot (19).

## Model

Bagged HistGradientBoosting ensemble (8 models) + isotonic calibration:
- calibrated probability → risk %, bootstrap CI, cohort percentile
- label: real treatment-outcome (CHORD) + OS-proxy (IMPACT-2017)
- honest metrics: held-out AUC, PR-AUC, Brier, ECE, per-cohort + per-cancer-type AUC
