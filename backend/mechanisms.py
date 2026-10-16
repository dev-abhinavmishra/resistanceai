"""
Resistance Mechanism Analyzer — mechanistic hypothesis engine.

Interprets a patient's genomic profile against a curated knowledge base of
published escape mechanisms (on-target secondary events, bypass-track
activation, lineage transformation, immune exclusion) and returns ranked
hypotheses with evidence and clinical implications.

References: NCCN compendia, OncoKB resistance annotations (Levels R1/R2),
AACR Project GENIE analyses, and primary literature on targeted-therapy
escape (e.g., MET-mediated bypass post-EGFR TKI; RB1 loss in SCLC
transformation; STK11/KEAP1 immune exclusion).
"""

from typing import Dict, Any, List

from .features import fusion_gene_set

# Rule schema — `when` conditions are AND-ed across keys; within a key:
#   genes / genes_all : ALL listed alterations present (mutation, amp, or del)
#   genes_any         : ANY listed alteration (incl. fusions)
#   genes_driver      : ANY listed driver (mutation or fusion partner)
#   cna_amp / cna_del : ANY listed gene amplified / deep-deleted
#   sites             : canonical cancer type must be in the set
#   min_tmb           : TMB >= threshold
#   mechanism, category, implication, strategy, level ("established"|"emerging"|"hypothesis")
RULES = [
    # ---------- BYPASS TRACK ----------
    {
        "id": "met_bypass_egfr", "category": "Bypass track",
        "mechanism": "RTK bypass amplification (MET / HER2 / FGFR1)",
        "when": {"genes": {"EGFR"}, "cna_amp": {"MET", "ERBB2", "FGFR1"}, "sites": {"lung"}},
        "implication": "Parallel RTK amplification (MET, ERBB2 or FGFR1) reactivates ERBB3-dependent PI3K/AKT signaling despite EGFR blockade — the leading bypass class of osimertinib failure (FLAURA/SAVANNAH data).",
        "strategy": "Combine EGFR TKI with the matched RTK inhibitor (osimertinib + savolitinib per SAVANNAH for MET, amivantamab, or HER2-directed therapy for ERBB2); biopsy-guided confirmation recommended.",
        "level": "established",
    },
    {
        "id": "her2_bypass", "category": "Bypass track",
        "mechanism": "HER2 (ERBB2) amplification bypass",
        "when": {"cna_amp": {"ERBB2"}, "genes_any": {"EGFR", "ALK", "ROS1", "KRAS"}},
        "implication": "ERBB2 amplification sustains downstream signaling in the presence of targeted inhibition.",
        "strategy": "HER2-directed therapy combination (trastuzumab deruxtecan for HER2-mutant/amplified tumors).",
        "level": "established",
    },
    {
        "id": "ras_bypass_antiegfr", "category": "Bypass track",
        "mechanism": "RAS-pathway reactivation → anti-EGFR resistance",
        "when": {"genes_any": {"KRAS", "NRAS", "HRAS", "BRAF"}, "sites": {"colorectal"}},
        "implication": "Activating RAS/RAF alterations confer primary resistance to cetuximab/panitumumab — established exclusion criterion.",
        "strategy": "Non-EGFR regimens (bevacizumab backbone); BRAF V600E → encorafenib+cetuximab; KRAS G12C → adagrasib/sotorasib+cetuximab combinations.",
        "level": "established",
    },
    {
        "id": "pi3k_reactivation", "category": "Bypass track",
        "mechanism": "PI3K/AKT/mTOR pathway reactivation",
        "when": {"genes_any": {"PIK3CA", "PIK3R1", "AKT1", "MTOR", "PTEN"}},
        "implication": "Parallel PI3K activation bypasses upstream blockade; PTEN loss is a pan-cancer resistance driver for trastuzumab, endocrine and targeted regimens.",
        "strategy": "PI3Kα inhibition (alpelisib in PIK3CA-mutant disease), AKT inhibition (capivasertib), or mTOR blockade per site guidelines.",
        "level": "established",
    },
    {
        "id": "fgfr_bypass", "category": "Bypass track",
        "mechanism": "FGFR-pathway bypass",
        "when": {"cna_amp": {"FGFR1", "FGFR2"}, "genes_any": {"EGFR", "ESR1"}},
        "implication": "FGFR1 amplification drives endocrine resistance in ER+ breast cancer and bypass signaling in EGFR-driven lung tumors.",
        "strategy": "FGFR inhibition (erdafitinib/pemigatinib backbones) within trials.",
        "level": "emerging",
    },

    # ---------- ON-TARGET / PATHWAY REACTIVATION ----------
    {
        "id": "map2k_reactivation", "category": "On-target / reactivation",
        "mechanism": "MAPK pathway reactivation downstream of the target",
        "when": {"genes_any": {"MAP2K1", "ARAF", "RAF1", "NRAS"},
                 "genes_driver": {"BRAF", "EGFR", "ALK"}},
        "implication": "Secondary MEK/RAF alterations reactivate ERK output despite upstream inhibition (documented in BRAFi- and EGFR-TKI-treated disease).",
        "strategy": "Vertical pathway blockade — RAF+MEK doublet (e.g., dabrafenib+trametinib intensification) or ERK inhibitors in trial.",
        "level": "established",
    },
    {
        "id": "braf_amp_escape", "category": "On-target / reactivation",
        "mechanism": "BRAF amplification / splice-variant escape",
        "when": {"cna_amp": {"BRAF"}, "genes": {"BRAF"}},
        "implication": "BRAF amplification restores ERK signaling under RAF inhibition.",
        "strategy": "MEK co-blockade; dose intensification within trials.",
        "level": "emerging",
    },

    # ---------- LINEAGE / PHENOTYPIC ----------
    {
        "id": "sclc_transformation", "category": "Lineage transformation",
        "mechanism": "Neuroendocrine (SCLC) transformation",
        "when": {"genes_all": {"RB1", "TP53"}, "genes_driver": {"EGFR", "ALK", "ROS1"}},
        "implication": "Complete RB1 loss with TP53 in an EGFR/ALK-driven adenocarcinoma is the genomic signature of small-cell transformation (~5–10% of TKI-resistant NSCLC).",
        "strategy": "Re-biopsy for histologic confirmation; platinum-etoposide + atezolizumab (SCLC regimen) if transformed.",
        "level": "established",
    },
    {
        "id": "ne_transformation_prostate", "category": "Lineage transformation",
        "mechanism": "Neuroendocrine prostate transformation",
        "when": {"genes_all": {"RB1", "TP53"}, "genes_driver": {"AR"}, "sites": {"prostate"}},
        "implication": "RB1 loss + TP53 with AR-pathway pressure → treatment-emergent neuroendocrine prostate cancer.",
        "strategy": "Platinum-based regimens; DLL3-directed agents in trials.",
        "level": "established",
    },

    # ---------- IMMUNE RESISTANCE ----------
    {
        "id": "stk11_keap1_immune", "category": "Immune exclusion",
        "mechanism": "STK11/KEAP1-driven cold tumor microenvironment",
        "when": {"genes_any": {"STK11", "KEAP1"}, "sites": {"lung"}},
        "implication": "STK11 and KEAP1 co-alterations are validated determinants of PD-(L)1 resistance in KRAS-mutant NSCLC despite high TMB.",
        "strategy": "Chemo-IO intensification or dual-IO/clinical trial rather than IO monotherapy.",
        "level": "established",
    },
    {
        "id": "wnt_immune_exclusion", "category": "Immune exclusion",
        "mechanism": "WNT/β-catenin immune-excluded phenotype",
        "when": {"genes_any": {"CTNNB1", "APC", "RNF43"}},
        "implication": "Canonical WNT signaling excludes CD8+ T-cell infiltration — associated with checkpoint resistance across tumor types.",
        "strategy": "Combinations targeting the microenvironment (anti-VEGF+IO backbones); WNT pathway inhibitors remain investigational.",
        "level": "emerging",
    },
    {
        "id": "antigen_presentation_loss", "category": "Immune exclusion",
        "mechanism": "Antigen-presentation machinery loss",
        "when": {"genes_any": {"B2M", "JAK1", "JAK2"}},
        "implication": "B2M or JAK1/2 inactivation abolishes IFN-γ response / HLA display — a validated acquired IO-resistance mechanism.",
        "strategy": "Non-IO regimens; NK-cell or bispecific strategies in trials.",
        "level": "established",
    },
    {
        "id": "emt_inflammation", "category": "Immune exclusion",
        "mechanism": "Inflamed→excluded microenvironment (EMT axis)",
        "when": {"genes_any": {"PTEN"}},
        "implication": "PTEN loss correlates with reduced T-cell infiltration and PI3K-driven immunosuppression.",
        "strategy": "Combinatorial IO+targeted approaches; AKT/PI3K blockade may restore infiltration (preclinical).",
        "level": "emerging",
    },

    # ---------- SITE-SPECIFIC DRUG-CLASS RESISTANCE ----------
    {
        "id": "esr1_endocrine", "category": "On-target / reactivation",
        "mechanism": "ESR1 ligand-binding mutation → endocrine resistance",
        "when": {"genes": {"ESR1"}, "sites": {"breast"}},
        "implication": "ESR1 mutations confer constitutive estrogen-independent ER signaling — acquired aromatase-inhibitor resistance.",
        "strategy": "SERDs (fulvestrant/elacestrant) rather than aromatase inhibitors; ctDNA monitoring for clone tracking.",
        "level": "established",
    },
    {
        "id": "rb_cdki_resistance", "category": "On-target / reactivation",
        "mechanism": "RB1 loss → CDK4/6-inhibitor resistance",
        "when": {"genes": {"RB1"}, "sites": {"breast"}},
        "implication": "RB1 loss removes the pharmacologic target of palbociclib/ribociclib/abemaciclib.",
        "strategy": "Shift to endocrine/chemo or PI3K-AKT directed therapy if PIK3CA-altered.",
        "level": "established",
    },
    {
        "id": "ar_resistance", "category": "On-target / reactivation",
        "mechanism": "AR amplification/mutation → androgen-axis resistance",
        "when": {"genes_any": {"AR"}, "sites": {"prostate"}},
        "implication": "AR alterations indicate castration-resistant disease biology and reduced response to next-generation androgen signaling inhibitors.",
        "strategy": "PARP inhibition if HRD-altered; radioligand (177Lu-PSMA) or taxane sequencing.",
        "level": "established",
    },
    {
        "id": "hrd_parp_context", "category": "Drug-class context",
        "mechanism": "PARP-inhibitor sensitivity (HRD context)",
        "when": {"genes_any": {"BRCA1", "BRCA2", "PALB2", "RAD51C", "RAD51D"}},
        "implication": "Homologous-recombination deficiency predicts PARP-inhibitor and platinum benefit — a protective/sensitivity signal that counterweights resistance risk.",
        "strategy": "PARP inhibitor per site guidelines; monitor for reversion mutations at progression.",
        "level": "established",
        "sensitivity": True,
    },
    {
        "id": "io_sensitivity", "category": "Drug-class context",
        "mechanism": "Checkpoint sensitivity (MSI-H/TMB-H/POLE context)",
        "when": {"genes_any": {"POLE", "MLH1", "MSH2", "MSH6", "PMS2"}, "min_tmb": 10},
        "implication": "Hypermutated phenotype (MSI-H/dMMR/POLE) predicts durable checkpoint-inhibitor benefit — site-agnostic sensitivity signal.",
        "strategy": "Pembrolizumab/dostarlimab site-agnostic indication.",
        "level": "established",
        "sensitivity": True,
    },
    {
        "id": "alk_resistance_context", "category": "Bypass track",
        "mechanism": "ALK-inhibitor escape (compound alterations)",
        "when": {"genes_all": {"TP53"}, "genes_driver": {"ALK"}},
        "implication": "TP53 co-alteration with ALK fusion is associated with shorter TKI duration and earlier progression.",
        "strategy": "Next-generation ALK TKI (lorlatinib) preferred; consider upfront chemo-ALK in high-risk profiles.",
        "level": "emerging",
    },
    {
        "id": "gtpase_plasticity", "category": "Adaptive",
        "mechanism": "RTK-adapted resistance to KRAS-G12C inhibition",
        "when": {"genes": {"KRAS"}, "cna_amp": {"EGFR", "MET", "ERBB2", "FGFR1", "RET"}},
        "implication": "RTK amplification enables adaptive RAS rebound under G12C blockade (CodeBreaK/secondary-analyses).",
        "strategy": "G12C + upstream RTK (EGFR/MET) or SHP2 combinations.",
        "level": "emerging",
    },
]


def analyze(clinical_input: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return ranked resistance-mechanism hypotheses for a clinical input."""
    muts = set(clinical_input.get("gene_mutations") or [])
    cna = clinical_input.get("cna") or {}
    tmb = clinical_input.get("tmb") or 0
    site = clinical_input.get("cancer_type_canonical") or \
        str(clinical_input.get("cancer_type", "")).lower()
    amps = {g for g, v in cna.items() if v >= 2}
    dels = {g for g, v in cna.items() if v <= -2}
    fus = fusion_gene_set(clinical_input.get("fusions"))

    hits = []
    for rule in RULES:
        w = rule["when"]
        if w.get("sites") and site not in w["sites"]:
            continue
        if w.get("genes") and not w["genes"] <= (muts | amps | dels):
            continue
        if w.get("genes_all") and not w["genes_all"] <= (muts | dels | amps):
            continue
        if w.get("genes_any") and not w["genes_any"] & (muts | amps | dels | fus):
            continue
        if w.get("cna_amp") and not w["cna_amp"] & amps:
            continue
        if w.get("cna_del") and not w["cna_del"] & dels:
            continue
        if w.get("min_tmb") and tmb < w["min_tmb"]:
            continue
        if w.get("genes_driver") and not w["genes_driver"] & (muts | fus):
            continue

        evidence = []
        for g in sorted(w.get("genes", set()) & (muts | amps | dels)):
            evidence.append(f"{g} alteration detected")
        for g in sorted(w.get("genes_any", set()) & (muts | amps | dels | fus)):
            evidence.append(f"{g} alteration detected")
        for g in sorted(w.get("cna_amp", set()) & amps):
            evidence.append(f"{g} amplification (CN≥2)")
        for g in sorted(w.get("cna_del", set()) & dels):
            evidence.append(f"{g} deep deletion")
        if w.get("min_tmb") and tmb >= w["min_tmb"]:
            evidence.append(f"TMB {tmb:.1f} mut/Mb")
        hits.append({
            "mechanism": rule["mechanism"], "category": rule["category"],
            "implication": rule["implication"], "strategy": rule["strategy"],
            "evidence": evidence, "level": rule["level"],
            "sensitivity": rule.get("sensitivity", False),
            "confidence": "high" if rule["level"] == "established" else "moderate",
        })
    order = {"established": 0, "emerging": 1, "hypothesis": 2}
    hits.sort(key=lambda h: (h["sensitivity"], order[h["level"]]))
    return hits
