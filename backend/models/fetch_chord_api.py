"""
Fetch MSK-CHORD 2024 mutation + structural variant data via the public cBioPortal API.

The datahub GitHub mirror serves large files through Git LFS which can be
rate-limited; the cBioPortal REST API is the reliable channel.

Outputs (written to msk_chord_2024/):
  data_mutations.txt   - MAF-like TSV, same schema as cBioPortal downloads
  data_sv.txt          - structural variant TSV
"""

import json
import os
import time
import requests

API = "https://www.cbioportal.org/api"
OUT_DIR = "msk_chord_2024"
RAW_DIR = os.path.join(OUT_DIR, "raw_mutation_batches")
PROFILE_MUT = "msk_chord_2024_mutations"
PROFILE_SV = "msk_chord_2024_structural_variants"
SAMPLE_BATCH = 2000  # samples per request (tuned against edge timeouts)


def get_sample_ids():
    import pandas as pd
    s = pd.read_csv(os.path.join(OUT_DIR, "data_clinical_sample.txt"),
                    sep="\t", comment="#", usecols=["SAMPLE_ID"])
    return s["SAMPLE_ID"].unique().tolist()


def fetch_mutations(sample_ids):
    """Download all mutations, batched by sample."""
    os.makedirs(RAW_DIR, exist_ok=True)
    done = set()
    for fn in os.listdir(RAW_DIR):
        if fn.startswith("mut_batch_") and fn.endswith(".json"):
            done.add(int(fn.split("_")[2].split(".")[0]))
    for b, i in enumerate(range(0, len(sample_ids), SAMPLE_BATCH)):
        if b in done:
            continue
        ids = sample_ids[i:i + SAMPLE_BATCH]
        for attempt in range(4):
            try:
                r = requests.post(f"{API}/molecular-profiles/{PROFILE_MUT}/mutations/fetch",
                                  json={"sampleIds": ids}, timeout=280)
                r.raise_for_status()
                with open(os.path.join(RAW_DIR, f"mut_batch_{b}.json"), "w") as f:
                    json.dump(r.json(), f)
                print(f"batch {b}: {len(r.json())} records ({len(ids)} samples)",
                      flush=True)
                break
            except Exception as e:
                print(f"batch {b} attempt {attempt} failed: {e}", flush=True)
                time.sleep(5 * (attempt + 1))
        else:
            print(f"batch {b}: FAILED permanently", flush=True)
        time.sleep(0.4)


FUSION_ENTREZ = [238, 6098, 5979, 4914, 4915, 4916, 2263, 2261, 4233, 673,
                 5894, 3084, 7113, 613, 25, 2130, 340419, 54532, 7157, 1956,
                 3845, 3248, 2064, 5728]


def fetch_sv():
    """Download structural variants for fusion-relevant genes."""
    r = requests.post(f"{API}/structural-variant/fetch",
                      json={"molecularProfileIds": [PROFILE_SV],
                            "entrezGeneIds": FUSION_ENTREZ}, timeout=280)
    if r.status_code != 200:
        print(f"SV fetch failed ({r.status_code}): {r.text[:200]}")
        return []
    return r.json()


def mutations_to_maf():
    e2h = {}
    map_path = os.path.join(OUT_DIR, "entrez_to_hugo.json")
    if os.path.exists(map_path):
        with open(map_path) as f:
            e2h = {int(k): v for k, v in json.load(f).items()}
    rows = []
    for fn in sorted(os.listdir(RAW_DIR)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(RAW_DIR, fn)) as f:
            rows.extend(json.load(f))
    cols = ["Hugo_Symbol", "Entrez_Gene_Id", "Chromosome", "Start_Position", "End_Position",
            "Consequence", "Variant_Classification", "Variant_Type",
            "Reference_Allele", "Tumor_Seq_Allele1", "Tumor_Seq_Allele2",
            "Tumor_Sample_Barcode", "HGVSp_Short", "Protein_position"]
    with open(os.path.join(OUT_DIR, "data_mutations.txt"), "w") as f:
        f.write("\t".join(cols) + "\n")
        for m in rows:
            mut = m.get("mutationType") or m.get("variantClassification") or ""
            hugo = (m.get("gene") or {}).get("hugoGeneSymbol") or \
                e2h.get(m.get("entrezGeneId"), "")
            f.write("\t".join(str(x) for x in [
                hugo,
                m.get("entrezGeneId", ""),
                m.get("chr", m.get("chromosome", "")),
                m.get("startPosition", ""),
                m.get("endPosition", ""),
                m.get("consequenceTerms", "") if isinstance(m.get("consequenceTerms"), str)
                    else ";".join(m.get("consequenceTerms", []) or []),
                mut, m.get("variantType", ""),
                m.get("referenceAllele", ""), m.get("tumorSeqAllele1", ""),
                m.get("variantAllele", m.get("tumorSeqAllele2", "")),
                m.get("sampleId", ""), m.get("proteinChange", ""),
                m.get("proteinPosStart", ""),
            ]) + "\n")
    return len(rows)


def sv_to_tsv(sv_rows):
    cols = ["Sample_Id", "Site1_Hugo_Symbol", "Site2_Hugo_Symbol", "Class",
            "Event_Info", "Site1_Position", "Site2_Position", "Site1_Chromosome",
            "Site2_Chromosome", "SV_Status"]
    with open(os.path.join(OUT_DIR, "data_sv.txt"), "w") as f:
        f.write("\t".join(cols) + "\n")
        for s in sv_rows:
            g1 = s.get("site1HugoSymbol") or ""
            g2 = s.get("site2HugoSymbol") or ""
            f.write("\t".join(str(x) for x in [
                s.get("sampleId", ""), g1, g2,
                s.get("variantClass", s.get("structuralVariantClass", "")),
                s.get("eventInfo") or (f"{g1}-{g2} Fusion" if g2 else f"{g1} rearrangement"),
                s.get("site1Position", ""), s.get("site2Position", ""),
                s.get("site1Chromosome", ""), s.get("site2Chromosome", ""),
                s.get("svStatus", "SOMATIC"),
            ]) + "\n")


if __name__ == "__main__":
    print("Loading sample ids...", flush=True)
    sample_ids = get_sample_ids()
    print(f"{len(sample_ids)} samples", flush=True)
    fetch_mutations(sample_ids)
    n = mutations_to_maf()
    print(f"Wrote {n} mutations to data_mutations.txt", flush=True)
    print("Fetching structural variants...", flush=True)
    svs = fetch_sv()
    sv_to_tsv(svs)
    print(f"Wrote {len(svs)} SVs to data_sv.txt", flush=True)
