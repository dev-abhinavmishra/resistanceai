"""
ResistanceAI v9 — unified multi-cohort ingestion.

Builds one normalized record per patient from:
  * msk_impact_2017/  (local cBioPortal export: clinical + MAF + CNA + SV)
  * msk_chord_2024/   (downloaded: clinical + MAF + CNA + SV + treatment/
                       progression timelines with real therapy outcomes)

Output: backend/data/patient_records.jsonl
  One JSON object per patient:
    patient_id, sample_id, cohort, clinical_input{...}, display{...},
    os_months, os_status, resistant (label), label_source, tx_agents

Also writes backend/data/cohort_index.csv (lightweight analytics index).
"""

import json
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from backend.features import (canonical_cancer_type, DRIVER_GENES, HRD_GENES,
                              CNA_FLAG_GENES)

DATA_DIR = os.environ.get("RESISTANCEAI_DATA_DIR", "backend/data")
RECORDS_OUT = os.path.join(DATA_DIR, "patient_records.jsonl")
INDEX_OUT = os.path.join(DATA_DIR, "cohort_index.csv")

NONSYNONYMOUS = {
    "Missense_Mutation", "Nonsense_Mutation", "Frame_Shift_Del", "Frame_Shift_Ins",
    "In_Frame_Del", "In_Frame_Ins", "Splice_Site", "Splice_Region",
    "Translation_Start_Site", "Nonstop_Mutation", "missense_variant",
    "stop_gained", "frameshift_variant", "splice_donor_variant",
    "splice_acceptor_variant", "inframe_deletion", "inframe_insertion",
    "start_lost", "stop_lost", "protein_altering_variant",
}

# 6-class collapsed substitution spectrum (complements merged)
_SUB_MAP = {}
for _ref, _comp in [("C", "G"), ("T", "A")]:
    for _alt in "ACGT":
        if _alt == _ref:
            continue
        key = f"{_ref}>{_alt}"
        _SUB_MAP[(_ref, _alt)] = key
        _SUB_MAP[(_comp, {"A": "T", "T": "A", "C": "G", "G": "C"}[_alt])] = key
SPEC_KEYS = ["C>T", "C>A", "C>G", "T>A", "T>C", "T>G"]

_DRIVER_SET = set(DRIVER_GENES)


# ---------------------------------------------------------------------------

def _read_table(path, **kw):
    return pd.read_csv(path, sep="\t", comment="#", low_memory=False, **kw)


def _pick_primary_sample(df: pd.DataFrame) -> pd.DataFrame:
    """One sample per patient: prefer the highest-purity draw, with the
    earliest sample ID as the deterministic tie-break (T01 sorts first)."""
    df = df.copy()
    if "TUMOR_PURITY" in df.columns:
        df["_purity"] = pd.to_numeric(df["TUMOR_PURITY"], errors="coerce").fillna(0)
    else:
        df["_purity"] = 0.0
    df = df.sort_values(["PATIENT_ID", "_purity", "SAMPLE_ID"],
                        ascending=[True, False, True])
    return df.drop_duplicates("PATIENT_ID", keep="first")


def _mutation_stats(mut_path):
    """Per-sample gene sets, mutation counts, indels, spectrum, display variants."""
    usecols = ["Hugo_Symbol", "Variant_Classification", "Variant_Type",
               "Reference_Allele", "Tumor_Seq_Allele2", "Tumor_Sample_Barcode"]
    extra = [c for c in ["HGVSp_Short", "Protein_position", "Consequence"]]
    head = pd.read_csv(mut_path, sep="\t", comment="#", nrows=0)
    usecols += [c for c in extra if c in head.columns]
    mut = _read_table(mut_path, usecols=usecols)
    cons = (mut["Consequence"].fillna("") if "Consequence" in mut.columns
            else pd.Series("", index=mut.index))
    mut = mut[mut["Variant_Classification"].fillna("").isin(NONSYNONYMOUS) |
              cons.str.contains(
                  "missense|nonsense|frameshift|splice|start_lost|stop|inframe",
                  case=False, regex=True)]

    ref = mut["Reference_Allele"].astype(str).str.upper()
    alt = mut["Tumor_Seq_Allele2"].astype(str).str.upper()
    mut["_cls"] = [_SUB_MAP.get((r, a)) for r, a in zip(ref, alt)]
    is_indel = mut["Variant_Type"].isin(["INS", "DEL"]) | \
        (ref.str.len() != alt.str.len())

    spec = (mut.dropna(subset=["_cls"])
              .pivot_table(index="Tumor_Sample_Barcode", columns="_cls",
                           values="Hugo_Symbol", aggfunc="count", fill_value=0))

    grp = mut.groupby("Tumor_Sample_Barcode")
    stats = pd.DataFrame({
        "n_mut": grp.size(),
        "n_indel": grp.apply(lambda g: int(is_indel.loc[g.index].sum()),
                             include_groups=False) if len(mut) else pd.Series(dtype=int),
        "gene_mutations": grp["Hugo_Symbol"].apply(
            lambda s: (sorted(set(s) & _DRIVER_SET)
                       + sorted(set(s) - _DRIVER_SET))[:60]),
    })

    for k in SPEC_KEYS:
        stats[k] = spec[k] if k in spec.columns else 0

    # Top variants per sample for the molecular workbench display
    mut["_rank"] = (~mut["Hugo_Symbol"].isin(_DRIVER_SET)).astype(int)
    mut = mut.sort_values(["Tumor_Sample_Barcode", "_rank"])
    disp = mut.groupby("Tumor_Sample_Barcode").head(12)
    def _vrow(r):
        aa = r.get("HGVSp_Short") or ""
        return {"gene": r["Hugo_Symbol"], "variant_class": r["Variant_Classification"],
                "protein_change": aa.replace("p.", ""),
                "change": f"{r['Reference_Allele']}>{r['Tumor_Seq_Allele2']}"}
    display = disp.apply(_vrow, axis=1).groupby(disp["Tumor_Sample_Barcode"]).apply(list)

    return stats, display.to_dict()


def _cna_stats(cna_path):
    """fga, amp/del counts per sample + per-sample cna dict for flagged genes."""
    cna = _read_table(cna_path)
    genes = cna["Hugo_Symbol"].values
    mat = cna.drop(columns=["Hugo_Symbol"])
    mat = mat.apply(pd.to_numeric, errors="coerce").fillna(0)
    vals = mat.values.astype(np.int8)
    samples = mat.columns.tolist()

    out = pd.DataFrame({
        "fga": (np.abs(vals) >= 1).mean(axis=0),
        "n_amp": (vals >= 2).sum(axis=0),
        "n_deepdel": (vals <= -2).sum(axis=0),
    }, index=samples)

    flagged = set(CNA_FLAG_GENES) | set(HRD_GENES) | {"CD274", "RSPO3", "NRG1"}
    cna_dicts = {s: {} for s in samples}
    for gi, g in enumerate(genes):
        if g not in flagged:
            continue
        for sj in np.nonzero(vals[gi])[0]:
            cna_dicts[samples[sj]][g] = int(vals[gi, sj])
    return out, cna_dicts


def _sv_stats(sv_path):
    """SV counts + fusion pairs per sample."""
    sv = _read_table(sv_path)
    col_map = {c.lower(): c for c in sv.columns}
    sid = col_map.get("sample_id") or col_map.get("sampleid")
    if sid is None:
        # SV export without a sample column can't be joined — treat as no
        # SV data rather than crashing the whole ingest.
        return pd.Series(dtype=float), {}
    g1 = col_map.get("site1_hugo_symbol")
    g2 = col_map.get("site2_hugo_symbol")
    cls = col_map.get("class", "")
    counts = sv.groupby(sid).size().rename("sv_count")
    fusions = {}
    if g1 and g2:
        for sample_id, grp in sv.groupby(sid):
            pairs = []
            for _, r in grp.iterrows():
                a, b = str(r[g1]), str(r[g2])
                if a != "nan" or b != "nan":
                    pairs.append({"gene1": "" if a == "nan" else a,
                                  "gene2": "" if b == "nan" else b,
                                  "sv_class": str(r[cls]) if cls else ""})
            fusions[sample_id] = pairs
    return counts, fusions


def _os_label(os_status, os_months):
    """OS-proxy resistance label: died <24mo -> 1, alive >24mo -> 0."""
    if pd.isna(os_months) or pd.isna(os_status):
        return np.nan
    if int(os_status) == 1:
        return 1.0 if os_months < 24 else 0.0
    return 0.0 if os_months >= 24 else np.nan


def _tx_labels(patients, tx_path, prog_path, os_map):
    """Treatment-outcome label from real therapy + NLP progression timelines."""
    tx = _read_table(tx_path)
    prog = _read_table(prog_path)
    tx = tx[tx["EVENT_TYPE"].str.lower() == "treatment"]
    tx["START_DATE"] = pd.to_numeric(tx["START_DATE"], errors="coerce")
    post = tx[tx["START_DATE"] >= -60]
    first_tx = post.groupby("PATIENT_ID")["START_DATE"].min()
    agents = post.groupby("PATIENT_ID")["AGENT"].apply(
        lambda s: sorted(set(str(a).title() for a in s.dropna()))[:6])

    prog = prog[prog["EVENT_TYPE"].str.lower() == "diagnosis"]
    prog["START_DATE"] = pd.to_numeric(prog["START_DATE"], errors="coerce")
    prog_y = prog[prog["PROGRESSION"].astype(str).str.upper() == "Y"]
    # First progression AT/AFTER treatment start (-30d tolerance), per patient.
    # Taking the first-ever progression would censor patients who progress once
    # before therapy and again on it.
    prog_y = prog_y.merge(first_tx.rename("t0"), left_on="PATIENT_ID",
                          right_index=True, how="inner")
    first_prog = (prog_y[prog_y["START_DATE"] >= prog_y["t0"] - 30]
                  .groupby("PATIENT_ID")["START_DATE"].min())

    def _dead(os_status):
        s = str(os_status).lower()
        return "1:" in s or "deceased" in s

    labels, sources = {}, {}
    for pid in patients:
        os_status, os_months = os_map.get(pid, (np.nan, np.nan))
        dead = _dead(os_status)
        alive = ("0:" in str(os_status)) or ("living" in str(os_status).lower())
        if pid in first_tx.index:
            t0 = first_tx.loc[pid]
            p = first_prog.get(pid)
            if p is not None and p <= t0 + 365 and p > t0 - 30:
                labels[pid], sources[pid] = 1.0, "tx"
            elif dead and not pd.isna(os_months) and os_months <= 18:
                labels[pid], sources[pid] = 1.0, "tx"
            elif (p is None or p > t0 + 365) and \
                    (alive or (dead and os_months >= 18) or
                     (pd.isna(os_status) or pd.isna(os_months))):
                labels[pid], sources[pid] = 0.0, "tx"
            else:
                labels[pid], sources[pid] = np.nan, "tx"
        else:
            labels[pid], sources[pid] = np.nan, "none"
    return labels, sources, agents.to_dict()


# ---------------------------------------------------------------------------

def _ingest_cohort(base, cohort):
    print(f"[{cohort}] clinical...")
    pat = _read_table(os.path.join(base, "data_clinical_patient.txt"))
    sam = _read_table(os.path.join(base, "data_clinical_sample.txt"))
    df = sam.merge(pat, on="PATIENT_ID", how="inner", suffixes=("", "_p"))
    df = _pick_primary_sample(df)
    df["OS_MONTHS"] = pd.to_numeric(df.get("OS_MONTHS"), errors="coerce")
    os_map = {r["PATIENT_ID"]: (r.get("OS_STATUS"), r.get("OS_MONTHS"))
              for _, r in df.iterrows()}

    print(f"[{cohort}] mutations...")
    mstats, mdisp = _mutation_stats(os.path.join(base, "data_mutations.txt"))
    print(f"[{cohort}] cna...")
    cna_stats, cna_dicts = _cna_stats(os.path.join(base, "data_cna.txt"))
    print(f"[{cohort}] sv...")
    sv_path = os.path.join(base, "data_sv.txt")
    sv_counts, fusion_map = (pd.Series(dtype=float), {})
    if os.path.exists(sv_path) and os.path.getsize(sv_path) > 100:
        sv_counts, fusion_map = _sv_stats(sv_path)

    labels, sources, agents = {}, {}, {}
    if cohort == "chord":
        print(f"[{cohort}] treatment labels...")
        labels, sources, agents = _tx_labels(
            set(df["PATIENT_ID"]),
            os.path.join(base, "data_timeline_treatment.txt"),
            os.path.join(base, "data_timeline_progression.txt"), os_map)

    n_met_sites = {}
    met_cols = [c for c in ["BONE", "LIVER", "LUNG", "CNS_BRAIN", "LYMPH_NODES",
                            "INTRA_ABDOMINAL", "PLEURA", "ADRENAL_GLANDS"]
                if c in df.columns]
    for _, r in df.iterrows():
        n_met_sites[r["PATIENT_ID"]] = sum(
            1 for c in met_cols if str(r.get(c, "")).lower() == "yes")

    records = []
    for _, r in df.iterrows():
        sid, pid = r["SAMPLE_ID"], r["PATIENT_ID"]
        m = mstats.loc[sid] if sid in mstats.index else None
        gene_muts = m["gene_mutations"] if m is not None else []
        spec = {k: int(m[k]) for k in SPEC_KEYS
                if m is not None and not pd.isna(m[k])} if m is not None else {}
        os_status_raw = str(r.get("OS_STATUS", ""))
        os_status = 1 if "1:" in os_status_raw or "deceased" in os_status_raw.lower() \
            else (0 if "0:" in os_status_raw or "living" in os_status_raw.lower() else np.nan)
        os_months = r.get("OS_MONTHS")

        if cohort == "chord":
            age = pd.to_numeric(r.get("CURRENT_AGE_DEID"), errors="coerce")
            # CHORD only records a 3-way stage bucket; keep the bucket labels
            # aligned with features.stage_map ("STAGE 1-3" -> 2, "STAGE 4" -> 4)
            # so corpus and API inputs encode identically.
            stage = {"Stage 4": "IV", "Stage 1-3": "STAGE 1-3"}.get(
                str(r.get("STAGE_HIGHEST_RECORDED", "")).strip())
            sex = r.get("GENDER")
            smoking = r.get("SMOKING_PREDICTIONS_3_CLASSES")
            msi_score = pd.to_numeric(r.get("MSI_SCORE"), errors="coerce")
            msi_type = r.get("MSI_TYPE")
            pdl1 = str(r.get("PDL1_POSITIVE", "") or r.get("HISTORY_OF_PDL1", ""))
        else:
            age = np.nan
            stage = "IV" if str(r.get("SAMPLE_TYPE", "")).lower().startswith("met") else "II"
            sex, smoking = r.get("SEX"), r.get("SMOKING_HISTORY")
            msi_score, msi_type, pdl1 = np.nan, None, ""

        ci = {
            "age_at_diagnosis": None if pd.isna(age) else float(age),
            "sex": sex, "smoking_history": smoking,
            "cancer_type": r.get("CANCER_TYPE"),
            "cancer_type_canonical": canonical_cancer_type(r.get("CANCER_TYPE")),
            "cancer_type_detailed": r.get("CANCER_TYPE_DETAILED"),
            "oncotree_code": r.get("ONCOTREE_CODE"),
            "stage": stage,
            "sample_type": r.get("SAMPLE_TYPE"),
            "metastatic_site": r.get("METASTATIC_SITE"),
            "n_met_sites": n_met_sites.get(pid, 0),
            "tumor_purity": pd.to_numeric(r.get("TUMOR_PURITY"), errors="coerce"),
            "tmb": pd.to_numeric(r.get("TMB_NONSYNONYMOUS"), errors="coerce"),
            "msi_score": None if pd.isna(msi_score) else float(msi_score),
            "msi_type": msi_type, "pdl1_status": pdl1,
            "gene_mutations": gene_muts,
            "mutation_details": mdisp.get(sid, []),
            "n_mut": int(m["n_mut"]) if m is not None else 0,
            "n_indel_frac": float(m["n_indel"] / m["n_mut"]) if m is not None and m["n_mut"] else 0.0,
            "substitution_spectrum": spec,
            "cna": cna_dicts.get(sid, {}),
            "fga": float(cna_stats.loc[sid, "fga"]) if sid in cna_stats.index else None,
            "n_amp": float(cna_stats.loc[sid, "n_amp"]) if sid in cna_stats.index else None,
            "n_deepdel": float(cna_stats.loc[sid, "n_deepdel"]) if sid in cna_stats.index else None,
            "sv_count": float(sv_counts.get(sid, np.nan)) if len(sv_counts) else np.nan,
            "fusions": fusion_map.get(sid, []),
        }
        if pd.isna(ci["sv_count"]):
            ci["sv_count"] = None
        if ci["tumor_purity"] is not None and pd.isna(ci["tumor_purity"]):
            ci["tumor_purity"] = None
        if ci["tmb"] is not None and pd.isna(ci["tmb"]):
            ci["tmb"] = None

        os_lab = _os_label(os_status, os_months)
        tx_lab = labels.get(pid, np.nan)
        label = tx_lab if not pd.isna(tx_lab) else os_lab
        src = "tx" if not pd.isna(tx_lab) else ("os" if not pd.isna(os_lab) else None)

        display = {
            "variants": mdisp.get(sid, [])[:12],
            "cna_events": [{"gene": g, "call": v,
                            "event": "Amplification" if v >= 2 else ("Gain" if v == 1 else
                            ("Deep deletion" if v <= -2 else "Loss"))}
                           for g, v in sorted(cna_dicts.get(sid, {}).items(),
                                              key=lambda kv: -abs(kv[1]))[:15]],
            "fusions": fusion_map.get(sid, [])[:10],
        }
        records.append({
            "patient_id": pid, "sample_id": sid, "cohort": cohort,
            "clinical_input": ci, "display": display,
            "os_months": None if pd.isna(os_months) else float(os_months),
            "os_status": None if pd.isna(os_status) else int(os_status),
            "resistant": None if pd.isna(label) else int(label),
            "label_source": src,
            "tx_agents": agents.get(pid, []),
        })
    print(f"[{cohort}] {len(records)} records")
    return records


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    records = []
    if os.path.exists("msk_impact_2017/msk_impact_2017"):
        records += _ingest_cohort("msk_impact_2017/msk_impact_2017", "impact2017")
    if os.path.exists("msk_chord_2024/data_clinical_patient.txt") and \
            os.path.exists("msk_chord_2024/data_mutations.txt") and \
            os.path.getsize("msk_chord_2024/data_mutations.txt") > 1000:
        records += _ingest_cohort("msk_chord_2024", "chord")

    with open(RECORDS_OUT, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    idx = pd.DataFrame([{
        "patient_id": r["patient_id"], "cohort": r["cohort"],
        "cancer_type": r["clinical_input"]["cancer_type_canonical"],
        "stage": r["clinical_input"]["stage"],
        "tmb": r["clinical_input"]["tmb"],
        "os_months": r["os_months"], "os_status": r["os_status"],
        "resistant": r["resistant"], "label_source": r["label_source"],
        "n_drivers": len(r["clinical_input"]["gene_mutations"]),
    } for r in records])
    idx.to_csv(INDEX_OUT, index=False)

    labeled = idx["resistant"].notna().sum()
    print(f"Wrote {len(records)} records -> {RECORDS_OUT}")
    print(f"Labeled: {labeled} ({labeled/len(records)*100:.1f}%), "
          f"tx-labeled: {(idx['label_source']=='tx').sum()}, "
          f"positive rate: {idx['resistant'].mean()*100:.1f}%")


if __name__ == "__main__":
    main()
