"""
Flask API for cancer resistance prediction.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import sys
from pathlib import Path
from typing import Dict, Any

# Add backend directory to path
sys.path.append(str(Path(__file__).parent))

from predictor import predict_resistance

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

@app.route('/health', methods=['GET'])
def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}

@app.route('/predict', methods=['POST'])
def predict() -> Dict[str, Any]:
    """
    Predict resistance risk from input features.
    
    Expected JSON body:
    {
        "cancer_type": "breast|lung|colorectal|melanoma|ovarian",
        "age_at_diagnosis": int,
        "tmb_level": "tmb_1|tmb_2|tmb_3|tmb_4",
        "ct_transition_pct": float (0-100),
        "structural_variant_burden": "low|moderate|high",
        "hr_deficiency": "present|absent",
        "stage": "I|II|III|IV"
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = {
            'cancer_type': str,
            'age_at_diagnosis': int,
            'tmb_level': str,
            'ct_transition_pct': (int, float),
            'structural_variant_burden': str,
            'hr_deficiency': str,
            'stage': str
        }
        
        # Check for missing fields
        missing = [f for f in required_fields if f not in data]
        if missing:
            return jsonify({
                "error": f"Missing required fields: {', '.join(missing)}"
            }), 400
        
        # Validate field types
        for field, field_type in required_fields.items():
            if not isinstance(data[field], field_type) and not (
                field_type == (int, float) and 
                isinstance(data[field], (int, float))
            ):
                return jsonify({
                    "error": f"Invalid type for {field}. Expected {field_type}."
                }), 400
        
        # Validate categorical values
        valid_values = {
            'cancer_type': ['breast', 'lung', 'colorectal', 'melanoma', 'ovarian'],
            'tmb_level': ['tmb_1', 'tmb_2', 'tmb_3', 'tmb_4'],
            'structural_variant_burden': ['low', 'moderate', 'high'],
            'hr_deficiency': ['present', 'absent'],
            'stage': ['I', 'II', 'III', 'IV']
        }
        
        for field, valid_options in valid_values.items():
            if data[field] not in valid_options:
                return jsonify({
                    "error": f"Invalid value for {field}. Must be one of: {', '.join(valid_options)}"
                }), 400
        
        # Validate numerical ranges
        if not (0 <= data['ct_transition_pct'] <= 100):
            return jsonify({
                "error": "ct_transition_pct must be between 0 and 100"
            }), 400
        
        if not (18 <= data['age_at_diagnosis'] <= 120):
            return jsonify({
                "error": "age_at_diagnosis must be between 18 and 120"
            }), 400
        
        # Make prediction
        result = predict_resistance(data)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "error": f"Prediction failed: {str(e)}"
        }), 500

if __name__ == "__main__":
    # Create artifacts directory if it doesn't exist
    os.makedirs("backend/artifacts", exist_ok=True)
    os.makedirs("backend/data", exist_ok=True)
    
    # Start the Flask app
    app.run(host="0.0.0.0", port=5000, debug=False)