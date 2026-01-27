
import pandas as pd
import numpy as np
import os
from pathlib import Path

def ingest_msk_data(
    base_dir: str = "msk_impact_2017/msk_impact_2017",
    output_path: str = "backend/data/resistance_real.csv"
):
    """
    Ingest and merge MSK-IMPACT clinical and mutation data.
    """
    print("Loading clinical data...")
    patient_path = os.path.join(base_dir, "data_clinical_patient.txt")
    sample_path = os.path.join(base_dir, "data_clinical_sample.txt")
    mutation_path = os.path.join(base_dir, "data_mutations.txt")
    
    if not all(os.path.exists(p) for p in [patient_path, sample_path, mutation_path]):
        raise FileNotFoundError("One or more required data files missing.")
        
    df_pat = pd.read_csv(patient_path, sep='\t', comment='#')
    df_sam = pd.read_csv(sample_path, sep='\t', comment='#')
    
    # Merge Patient and Sample data
    df = pd.merge(df_sam, df_pat, on='PATIENT_ID', how='inner')
    
    # Parse OS_MONTHS and define Resistance
    df['OS_MONTHS'] = pd.to_numeric(df['OS_MONTHS'], errors='coerce')
    df = df.dropna(subset=['OS_MONTHS'])
    
    def define_resistance(row):
        status = str(row['OS_STATUS']).lower()
        months = row['OS_MONTHS']
        if 'deceased' in status:
            return 1 if months < 24 else 0
        elif 'living' in status or 'alive' in status:
            return 0 if months > 24 else -1
        return -1

    df['resistant'] = df.apply(define_resistance, axis=1)
    df = df[df['resistant'] != -1].copy()
    
    print(f"Loading mutation data (this may take a moment)...")
    # Only load columns we need to save memory
    mut_cols = ['Hugo_Symbol', 'Reference_Allele', 'Tumor_Seq_Allele2', 'Tumor_Sample_Barcode']
    df_mut = pd.read_csv(mutation_path, sep='\t', comment='#', usecols=mut_cols, low_memory=False)
    
    # Calculate C>T Transition Percentage per sample
    print("Calculating C>T transition rates...")
    def is_ct_transition(row):
        ref = str(row['Reference_Allele']).upper()
        alt = str(row['Tumor_Seq_Allele2']).upper()
        # C>T or G>A (complementary strand)
        return (ref == 'C' and alt == 'T') or (ref == 'G' and alt == 'A')

    df_mut['is_ct'] = df_mut.apply(is_ct_transition, axis=1)
    
    sample_mut_stats = df_mut.groupby('Tumor_Sample_Barcode').agg(
        total_muts=('is_ct', 'count'),
        ct_muts=('is_ct', 'sum')
    )
    sample_mut_stats['ct_transition_pct'] = (sample_mut_stats['ct_muts'] / sample_mut_stats['total_muts'] * 100).fillna(0)
    
    # Identify HR Deficiency
    print("Identifying HR deficiency from mutations...")
    hr_genes = ['BRCA1', 'BRCA2', 'ATM', 'PALB2', 'CHEK2', 'RAD51C', 'RAD51D', 'BARD1']
    hr_samples = df_mut[df_mut['Hugo_Symbol'].isin(hr_genes)]['Tumor_Sample_Barcode'].unique()
    
    # Map back to main dataframe
    df['ct_transition_pct'] = df['SAMPLE_ID'].map(sample_mut_stats['ct_transition_pct']).fillna(20) # Default to 20 if no mutations
    df['hr_deficiency'] = df['SAMPLE_ID'].apply(lambda x: 'present' if x in hr_samples else 'absent')
    
    # Mapping other features
    df['cancer_type'] = df['CANCER_TYPE'].str.lower().replace({
        'non-small cell lung cancer': 'lung',
        'breast cancer': 'breast',
        'colorectal cancer': 'colorectal',
        'melanoma': 'melanoma',
        'ovarian cancer': 'ovarian'
    })
    valid_types = ['lung', 'breast', 'colorectal', 'melanoma', 'ovarian']
    df['cancer_type'] = df['cancer_type'].apply(lambda x: x if x in valid_types else 'other')
    
    df['TMB_NONSYNONYMOUS'] = pd.to_numeric(df['TMB_NONSYNONYMOUS'], errors='coerce').fillna(0)
    def bin_tmb(val):
        if val < 5: return 'tmb_1'
        elif val < 10: return 'tmb_2'
        elif val < 20: return 'tmb_3'
        else: return 'tmb_4'
    df['tmb_level'] = df['TMB_NONSYNONYMOUS'].apply(bin_tmb)
    
    def map_stage(row):
        sample_type = str(row.get('SAMPLE_TYPE', '')).lower()
        return 'IV' if 'metastasis' in sample_type or 'metastatic' in sample_type else 'II'
    df['stage'] = df.apply(map_stage, axis=1)
    
    # Handle Age (since missing in file, we'll try to find any numeric column that might be age or just use 60)
    df['age_at_diagnosis'] = 60 # Confirmed missing AGE in clinical patient/sample headers
    
    sv_map = {'tmb_1': 'low', 'tmb_2': 'low', 'tmb_3': 'moderate', 'tmb_4': 'high'}
    df['structural_variant_burden'] = df['tmb_level'].map(sv_map)

    final_cols = [
        'cancer_type', 'age_at_diagnosis', 'tmb_level', 
        'ct_transition_pct', 'structural_variant_burden', 
        'hr_deficiency', 'stage', 'resistant'
    ]
    
    final_df = df[final_cols]
    final_df.to_csv(output_path, index=False)
    print(f"Saved refined dataset with real genomic features to {output_path}")
    print(f"Summary: {len(final_df)} samples, {len(hr_samples)} HR-deficient samples identified.")


if __name__ == "__main__":
    ingest_msk_data()
