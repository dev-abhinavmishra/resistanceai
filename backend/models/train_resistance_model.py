"""
Model training script for cancer resistance prediction.
Handles data loading, preprocessing, model training, and evaluation.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import pickle
import json
from typing import Dict, Any, Tuple

from sklearn.model_selection import train_test_split, RandomizedSearchCV
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    accuracy_score, roc_auc_score, precision_score, 
    recall_score, f1_score, confusion_matrix, classification_report
)
import joblib

# Define feature types
NUMERIC_FEATURES = ['age_at_diagnosis', 'ct_transition_pct']
CATEGORICAL_FEATURES = [
    'cancer_type', 'tmb_level', 'structural_variant_burden', 
    'hr_deficiency', 'stage'
]
TARGET = 'resistant'

def load_data(data_path: str = "backend/data/resistance_real.csv") -> pd.DataFrame:
    """Load and prepare the dataset."""
    df = pd.read_csv(data_path)
    return df

def build_preprocessor() -> ColumnTransformer:
    """Build preprocessing pipeline for features."""
    numeric_transformer = Pipeline(steps=[
        ('scaler', StandardScaler())
    ])
    
    categorical_transformer = Pipeline(steps=[
        ('onehot', OneHotEncoder(handle_unknown='ignore', sparse_output=False))
    ])
    
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', numeric_transformer, NUMERIC_FEATURES),
            ('cat', categorical_transformer, CATEGORICAL_FEATURES)
        ])
    
    return preprocessor

from sklearn.ensemble import RandomForestClassifier

def train_model(X_train: np.ndarray, y_train: np.ndarray) -> RandomForestClassifier:
    """Train the random forest classifier with balanced class weights."""
    param_dist = {
        'n_estimators': [100, 200, 300],
        'max_depth': [None, 10, 20, 30],
        'min_samples_split': [2, 5, 10],
        'min_samples_leaf': [1, 2, 4],
        'class_weight': ['balanced', 'balanced_subsample']
    }
    
    rf = RandomForestClassifier(random_state=42)
    
    random_search = RandomizedSearchCV(
        estimator=rf,
        param_distributions=param_dist,
        n_iter=10,
        cv=5,
        scoring='f1_macro', # Optimization for imbalanced data
        n_jobs=1,
        random_state=42,
        verbose=1
    )
    
    print("Performing hyperparameter tuning (Balanced Random Forest)...")
    random_search.fit(X_train, y_train)
    
    print(f"Best parameters: {random_search.best_params_}")
    print(f"Best CV score (Macro F1): {random_search.best_score_:.4f}")
    
    return random_search.best_estimator_

def evaluate_model(model, X_test: np.ndarray, y_test: np.ndarray) -> Dict[str, float]:
    """Evaluate model performance and return metrics."""
    y_pred = model.predict(X_test)
    y_pred_proba = model.predict_proba(X_test)[:, 1]
    
    metrics = {
        'accuracy': accuracy_score(y_test, y_pred),
        'roc_auc': roc_auc_score(y_test, y_pred_proba),
        'precision': precision_score(y_test, y_pred),
        'recall': recall_score(y_test, y_pred),
        'f1': f1_score(y_test, y_pred)
    }
    
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred))
    
    print("\nConfusion Matrix:")
    print(confusion_matrix(y_test, y_pred))
    
    return metrics

def save_artifacts(
    model: GradientBoostingClassifier,
    preprocessor: ColumnTransformer,
    output_dir: str = "backend/artifacts"
) -> Dict[str, str]:
    """Save model and preprocessing artifacts."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    model_path = output_path / "resistance_model.pkl"
    preprocessor_path = output_path / "preprocessor.pkl"
    
    # joblib.dump(model, model_path)
    # joblib.dump(preprocessor, preprocessor_path)
    with open(model_path, 'wb') as f:
        pickle.dump(model, f)
    with open(preprocessor_path, 'wb') as f:
        pickle.dump(preprocessor, f)
    
    return {
        'model_path': str(model_path),
        'preprocessor_path': str(preprocessor_path)
    }

def train_pipeline(data_path: str = None) -> Dict[str, Any]:
    """Complete training pipeline."""
    # Load data
    df = load_data(data_path) if data_path else load_data()
    
    # Split data
    X = df[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    y = df[TARGET]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    # Preprocessing
    preprocessor = build_preprocessor()
    X_train_processed = preprocessor.fit_transform(X_train)
    X_test_processed = preprocessor.transform(X_test)
    
    # Train model
    print("Training model...")
    model = train_model(X_train_processed, y_train)
    
    # Evaluate
    print("\nModel Evaluation:")
    metrics = evaluate_model(model, X_test_processed, y_test)
    
    # Save artifacts
    artifact_paths = save_artifacts(model, preprocessor)
    
    # Get feature importances
    feature_importances = model.feature_importances_
    feature_names = (
        NUMERIC_FEATURES + 
        list(preprocessor.named_transformers_['cat']
             .named_steps['onehot']
             .get_feature_names_out(CATEGORICAL_FEATURES))
    )
    
    return {
        'metrics': metrics,
        'artifact_paths': artifact_paths,
        'feature_importances': dict(zip(feature_names, feature_importances))
    }

if __name__ == "__main__":
    results = train_pipeline()
    print("\nTraining complete!")
    print(f"Model saved to: {results['artifact_paths']['model_path']}")
    print("\nFeature Importances:")
    for feat, imp in sorted(
        results['feature_importances'].items(), 
        key=lambda x: x[1], 
        reverse=True
    )[:10]:  # Top 10 features
        print(f"{feat}: {imp:.4f}")