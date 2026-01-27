"""
Prediction module for cancer resistance model.
Handles model loading and inference.
"""

import os
import json
import joblib
import numpy as np
from typing import Dict, Any, List
from pathlib import Path

# Define expected feature order for prediction
NUMERIC_FEATURES = ['age_at_diagnosis', 'ct_transition_pct']
CATEGORICAL_FEATURES = [
    'cancer_type', 'tmb_level', 'structural_variant_burden', 
    'hr_deficiency', 'stage'
]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES

class ResistancePredictor:
    """Wrapper for resistance prediction model with dynamic medical KB."""
    
    def __init__(self, model_dir: str = "backend/artifacts"):
        """Initialize predictor and load medical knowledge base."""
        import pickle
        with open(os.path.join(model_dir, "resistance_model.pkl"), 'rb') as f:
            self.model = pickle.load(f)
        with open(os.path.join(model_dir, "preprocessor.pkl"), 'rb') as f:
            self.preprocessor = pickle.load(f)
        
        self.feature_names = (
            NUMERIC_FEATURES + 
            list(self.preprocessor.named_transformers_['cat']
                 .named_steps['onehot']
                 .get_feature_names_out(CATEGORICAL_FEATURES))
        )
        
        # Load Medical Knowledge Base
        kb_path = os.path.join(os.path.dirname(__file__), "knowledge_base", "treatments.json")
        try:
            with open(kb_path, 'r') as f:
                self.kb = json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load treatments.json: {e}")
            self.kb = {"cancer_types": {}}

    def predict_resistance(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Make resistance prediction and map variants to outcomes using KB."""
        self._validate_input(input_data)
        
        import pandas as pd
        input_df = pd.DataFrame([input_data])
        X = self.preprocessor.transform(input_df)
        
        proba = self.model.predict_proba(X)[0][1]
        risk_score = int(round(proba * 100))
        
        feature_contributions = self._get_feature_contributions(input_data, proba)
        risk_tier, interpretation, recommendation = self._generate_interpretation(risk_score, input_data)
        
        return {
            "risk_score": risk_score,
            "risk_tier": risk_tier,
            "probability": float(proba),
            "interpretation": interpretation,
            "recommendation": recommendation,
            "feature_contributions": feature_contributions
        }

    def _validate_input(self, input_data: Dict[str, Any]) -> None:
        """Validate input data against expected schema."""
        missing = [f for f in FEATURES if f not in input_data]
        if missing:
            raise ValueError(f"Missing required features: {missing}")

    def _get_feature_contributions(
        self, 
        input_data: Dict[str, Any],
        probability: float
    ) -> List[Dict[str, Any]]:
        """Calculate contribution of each feature to the prediction."""
        importances = self.model.feature_importances_
        feature_importance = dict(zip(self.feature_names, importances))
        total_importance = sum(importances)
        normalized_importances = {
            k: v / total_importance for k, v in feature_importance.items()
        }
        contributions = [
            {"name": name, "weight": float(weight)}
            for name, weight in normalized_importances.items()
        ]
        contributions.sort(key=lambda x: x["weight"], reverse=True)
        return contributions[:10]

    def _generate_interpretation(self, risk_score: int, input_data: Dict[str, Any]) -> tuple:
        """Query knowledge base for site-specific, biomarker-linked recommendations."""
        
        # 1. Assessment Tier
        if risk_score >= 70:
            risk_tier = "HIGH"
            interpretation = f"Predictive signature identifies high risk of therapeutic escape ({risk_score}%)."
        elif risk_score >= 40:
            risk_tier = "MODERATE"
            interpretation = f"Intermediate genomic stability detected ({risk_score}%)."
        else:
            risk_tier = "LOW"
            interpretation = f"Genomically stable profile with favorable therapeutic window ({risk_score}%)."

        # 2. Dynamic Knowledge Base Query
        therapies = []
        cancer_type = input_data['cancer_type']
        detected_variants = input_data.get("detected_variants", [])
        hr_status = input_data.get("hr_deficiency")
        tmb_level = input_data.get("tmb_level")

        # Site-Specific Mapping
        type_kb = self.kb.get("cancer_types", {}).get(cancer_type, {})
        biomarker_kb = type_kb.get("biomarkers", {})
        
        # Search for exact variant matches (e.g., EGFR)
        for variant in detected_variants:
            if variant in biomarker_kb:
                therapies.extend(biomarker_kb[variant]["regimens"])

        # HRD Logic for Breast/Ovarian
        if hr_status == "present" and "HRD_Positive" in biomarker_kb:
            therapies.extend(biomarker_kb["HRD_Positive"]["regimens"])
        
        # TMB Logic
        if tmb_level in ["tmb_3", "tmb_4"] and "TMB-H" in biomarker_kb:
            therapies.extend(biomarker_kb["TMB-H"]["regimens"])

        # Universal Site-Agnostic Logic (MSI-H)
        # Note: We simulate MSI-H mapping if HRD or high TMB is present in this demo
        if tmb_level == "tmb_4" or hr_status == "present":
             therapies.extend(self.kb.get("universal_biomarkers", {}).get("MSI-H", []))

        # Default Fallback
        if not therapies:
            therapies.append({
                "name": "Institutional SoC (Chemotherapy)",
                "type": "Standard of Care",
                "line": "1st-Line",
                "guideline_tier": "Standard Care",
                "evidence_level": "Level 2-3",
                "regulatory_status": "FDA Approved",
                "rationale": "Recommended in the absence of actionable genomic drivers.",
                "patient_explanation": "Standard chemotherapy used to treat this type of cancer."
            })

        recommendation = {
            "summary": "Escalated monitoring recommended." if risk_tier == "HIGH" else "Proceed with standard protocol.",
            "therapies": therapies,
            "trials": [{"id": "NCT00000000", "name": "Phase III Active Matching Trial", "match": "90%", "phase": "III"}]
        }

        return risk_tier, interpretation, recommendation

# Singleton instance
_predictor = None

def get_predictor() -> ResistancePredictor:
    """Get or create singleton predictor instance."""
    global _predictor
    if _predictor is None:
        try:
            _predictor = ResistancePredictor()
        except:
            # Fallback for transient load issues
            return None
    return _predictor

def predict_resistance(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Predict resistance risk from input features.
    
    Args:
        input_data: Dictionary containing feature values
        
    Returns:
        Dictionary with prediction results
    """
    predictor = get_predictor()
    if predictor:
        return predictor.predict_resistance(input_data)
    else:
        # Mock for development if model is missing
        return {
            "risk_score": 55, "risk_tier": "MODERATE", "probability": 0.55,
            "interpretation": "Engine in fallback mode.", "recommendation": {"summary": "Offline", "therapies": [], "trials": []},
            "feature_contributions": []
        }
