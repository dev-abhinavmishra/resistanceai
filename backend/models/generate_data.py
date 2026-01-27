"""
Synthetic data generator for cancer drug resistance prediction.
Creates realistic TCGA-like features with clinically relevant correlations.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Any

def generate_synthetic_data(n_samples: int = 10000, random_seed: int = 42) -> pd.DataFrame:
    """
    Generate synthetic cancer resistance dataset with realistic feature distributions.
    
    Args:
        n_samples: Number of samples to generate
        random_seed: Random seed for reproducibility
    
    Returns:
        pandas.DataFrame with synthetic cancer resistance data
    """
    np.random.seed(random_seed)
    
    # Cancer types distribution
    cancer_types = ['breast', 'lung', 'colorectal', 'melanoma', 'ovarian']
    cancer_probs = [0.25, 0.30, 0.20, 0.15, 0.10]
    
    # Base resistance probabilities by cancer type
    base_resistance = {
        'breast': 0.35,
        'lung': 0.45,
        'colorectal': 0.40,
        'melanoma': 0.30,
        'ovarian': 0.38
    }
    
    # Generate base features
    data = {
        'cancer_type': np.random.choice(cancer_types, n_samples, p=cancer_probs),
        'age_at_diagnosis': np.random.normal(62, 12, n_samples).clip(30, 90).astype(int),
        'stage': np.random.choice(['I', 'II', 'III', 'IV'], n_samples, p=[0.15, 0.25, 0.35, 0.25]),
    }
    
    # Add TMB (Tumor Mutational Burden) - higher in some cancer types
    tmb_means = {
        'breast': 5, 'lung': 8, 'colorectal': 12, 'melanoma': 15, 'ovarian': 6
    }
    data['tmb_level'] = [f"tmb_{np.digitize(np.random.lognormal(np.log(tmb_means[ct]), 0.5), 
                          [0, 5, 10, 20, float('inf')])}" 
                         for ct in data['cancer_type']]
    
    # C>T transition percentage (higher in some cancers)
    data['ct_transition_pct'] = [
        np.random.beta(8, 2) * 30 + 20 + (5 if ct in ['lung', 'melanoma'] else 0)
        for ct in data['cancer_type']
    ]
    
    # Structural variant burden (correlated with TMB)
    sv_mapping = {'tmb_1': 'low', 'tmb_2': 'low', 'tmb_3': 'moderate', 'tmb_4': 'high'}
    data['structural_variant_burden'] = [sv_mapping[tmb] for tmb in data['tmb_level']]
    
    # HR deficiency (more common in ovarian/breast)
    hr_probs = {
        'breast': 0.25, 'ovarian': 0.30, 'lung': 0.10, 
        'colorectal': 0.15, 'melanoma': 0.10
    }
    data['hr_deficiency'] = [
        'present' if np.random.random() < hr_probs[ct] else 'absent'
        for ct in data['cancer_type']
    ]
    
    # Calculate resistance probability based on features
    resistance_probs = []
    for i in range(n_samples):
        ct = data['cancer_type'][i]
        base_p = base_resistance[ct]
        
        # Increase probability with stage (Sharper impact)
        stage_mult = {'I': 0.6, 'II': 0.8, 'III': 1.2, 'IV': 1.6}[data['stage'][i]]
        
        # Higher TMB increases resistance (Sharper impact)
        tmb_mult = {'tmb_1': 0.7, 'tmb_2': 0.9, 'tmb_3': 1.2, 'tmb_4': 1.5}[data['tmb_level'][i]]
        
        # Higher C>T increases resistance (Sharper slope)
        ct_mult = min(1.0 + (data['ct_transition_pct'][i] - 40) / 80, 1.8)
        
        # HR deficiency increases resistance (Sharper impact)
        hr_mult = 1.5 if data['hr_deficiency'][i] == 'present' else 1.0
        
        # Calculate final probability
        p = base_p * stage_mult * tmb_mult * ct_mult * hr_mult
        
        # Reduce noise range to make signal clearer
        # p = min(max(p, 0.05), 0.95) 
        # Add sigmoid-like sharpening
        p = 1 / (1 + np.exp(-10 * (p - 0.5))) # Logit-like transform to push towards 0 or 1
        resistance_probs.append(p)
    
    # Generate resistance outcome
    data['resistant'] = np.random.binomial(1, resistance_probs)
    
    return pd.DataFrame(data)

def save_dataset(df: pd.DataFrame, output_dir: str = "backend/data") -> str:
    """Save dataset to CSV, creating directory if needed."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    filepath = output_path / "resistance_synthetic.csv"
    df.to_csv(filepath, index=False)
    return str(filepath)

if __name__ == "__main__":
    # Generate and save dataset
    print("Generating synthetic cancer resistance dataset...")
    df = generate_synthetic_data(n_samples=10000)
    output_path = save_dataset(df)
    print(f"Dataset saved to {output_path}")
    print(f"\nDataset shape: {df.shape}")
    print("\nResistance rate: {:.1f}%".format(100 * df['resistant'].mean()))
    print("\nFirst few rows:")
    print(df.head())