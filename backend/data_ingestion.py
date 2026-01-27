
import json
import pandas as pd
from typing import Dict, Any, List, Optional
import os

class ClinicalDataIngestor:
    """
    Simulates enterprise-grade ingestion for ResistanceAI.
    Handles FHIR-like patient data and structured genomic (NGS) reports.
    """
    
    @staticmethod
    def ingest_genomic_report(file_content: str, format: str = "json") -> Dict[str, Any]:
        """
        Parses a structured genomic report (Illumina/Foundation-like).
        Example Ingestion: 'EGFR L858R', 'TMB: 12.5 mut/Mb', 'MSS'.
        """
        try:
            if format == "json":
                data = json.loads(file_content)
                # Map structured report to ResistanceAI internal features
                biomarkers = data.get("biomarkers", {})
                variants = data.get("variants", [])
                
                # Extract TMB
                tmb_val = biomarkers.get("tmb", 0)
                tmb_tier = "tmb_1"
                if tmb_val > 20: tmb_tier = "tmb_4"
                elif tmb_val > 10: tmb_tier = "tmb_3"
                elif tmb_val > 5: tmb_tier = "tmb_2"
                
                # Extract MSI/HRD
                hr_status = "present" if biomarkers.get("hrd_status") == "positive" else "absent"
                
                # Search for specific clinical drivers in variant list
                driver_variants = [v.get("gene") for v in variants]
                
                return {
                    "tmb_level": tmb_tier,
                    "hr_deficiency": hr_status,
                    "ct_transition_pct": biomarkers.get("signature_1_weight", 40.0), # Example mapping
                    "structural_variant_burden": "high" if biomarkers.get("sv_count", 0) > 10 else "moderate",
                    "detected_variants": driver_variants
                }
        except Exception as e:
            raise ValueError(f"Failed to parse genomic report: {str(e)}")
        return {}

    @staticmethod
    def ingest_ehr_patient(patient_id: str) -> Dict[str, Any]:
        """
        Simulates a bi-directional EHR (Electronic Health Record) integration.
        Fetches demographics and prior problem lists via mock FHIR bridge.
        """
        # Mock database of enterprise patients with Diversified Genomics
        MOCK_EHR_DB = {
            "PX-9921": {"name": "Sarah Connor", "age_at_diagnosis": 42, "cancer_type": "breast", "stage": "IV", "hr_deficiency": "present", "detected_variants": ["HER2+"]},
            "PX-8812": {"name": "James Howlett", "age_at_diagnosis": 61, "cancer_type": "lung", "stage": "III", "detected_variants": ["EGFR"]},
            "PX-7743": {"name": "Bruce Wayne", "age_at_diagnosis": 48, "cancer_type": "prostate", "stage": "IV", "detected_variants": ["BRCA1/2"]},
            "PX-6654": {"name": "Diana Prince", "age_at_diagnosis": 52, "cancer_type": "ovarian", "stage": "III", "hr_deficiency": "present", "detected_variants": ["BRCA_Mutant"]},
            "PX-5565": {"name": "Clark Kent", "age_at_diagnosis": 35, "cancer_type": "colorectal", "stage": "IV", "detected_variants": ["BRAF_V600E"]},
            "PX-4476": {"name": "Arthur Curry", "age_at_diagnosis": 45, "cancer_type": "melanoma", "stage": "II", "detected_variants": ["BRAF_V600"]},
            "PX-3387": {"name": "Barry Allen", "age_at_diagnosis": 29, "cancer_type": "lung", "stage": "IV", "detected_variants": ["ALK"]},
            "PX-2298": {"name": "Victor Stone", "age_at_diagnosis": 24, "cancer_type": "prostate", "stage": "IV", "detected_variants": ["PTEN_Loss"]},
            "PX-1109": {"name": "Hal Jordan", "age_at_diagnosis": 38, "cancer_type": "colorectal", "stage": "III", "tmb_level": "tmb_4"},
            "PX-0010": {"name": "Selina Kyle", "age_at_diagnosis": 34, "cancer_type": "breast", "stage": "II", "hr_deficiency": "present"}
        }
        return MOCK_EHR_DB.get(patient_id, {"name": "Unknown", "age_at_diagnosis": 50, "cancer_type": "lung", "stage": "II"})

class CaseQueueManager:
    """Manages the clinical worklist/queue for Tumor Boards."""
    
    def __init__(self, queue_file: str = "backend/artifacts/case_queue.json"):
        self.queue_file = queue_file
        self.queue = self._load_queue()
        
    def _load_queue(self) -> List[Dict[str, Any]]:
        # Hard-coded diverse default for demo excellence
        return [
            {"id": "PX-9921", "status": "Genomics Ready", "priority": "High", "site": "Breast"},
            {"id": "PX-8812", "status": "Board Pending", "priority": "High", "site": "Lung (EGFR+)"},
            {"id": "PX-7743", "status": "New Case", "priority": "Critical", "site": "Prostate"},
            {"id": "PX-6654", "status": "Genomics Ready", "priority": "Medium", "site": "Ovarian"},
            {"id": "PX-5565", "status": "Follow-up", "priority": "Low", "site": "CRC (BRAF+)"},
            {"id": "PX-4476", "status": "Review Requested", "priority": "High", "site": "Melanoma"},
            {"id": "PX-3387", "status": "In Analysis", "priority": "High", "site": "Lung (ALK+)"},
            {"id": "PX-2298", "status": "Ready", "priority": "Medium", "site": "Prostate (PTEN-)"},
            {"id": "PX-1109", "status": "Board Pending", "priority": "Critical", "site": "CRC (TMB-H)"},
            {"id": "PX-0010", "status": "New Case", "priority": "Medium", "site": "Breast (HRD+)"}
        ]
        
    def add_case(self, case_data: Dict[str, Any]):
        self.queue.append(case_data)
        self._save_queue()
        
    def _save_queue(self):
        os.makedirs(os.path.dirname(self.queue_file), exist_ok=True)
        with open(self.queue_file, 'w') as f:
            json.dump(self.queue, f, indent=4)
