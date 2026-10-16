import requests
import json
import os
from typing import List, Dict, Any

class ClinicalTrialEngine:
    """
    Integrates with ClinicalTrials.gov API v2 to fetch real-time oncology trials.
    """
    API_URL = "https://clinicaltrials.gov/api/v2/studies"
    
    def __init__(self, fallback_path: str = "backend/knowledge_base/trials.json"):
        self.fallback_path = fallback_path
        self.cache = {} # Simple in-memory cache for the session

    def fetch_trials(self, site: str, biomarkers: List[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Fetches trials based on cancer site and specific biomarkers.
        """
        cache_key = f"{site}_{'_'.join(biomarkers or [])}_{limit}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Map canonical cancer types to ClinicalTrials.gov condition terms
        site_map = {
            "lung": "Lung Cancer",
            "breast": "Breast Cancer",
            "colorectal": "Colorectal Cancer",
            "prostate": "Prostate Cancer",
            "ovarian": "Ovarian Cancer",
            "melanoma": "Melanoma",
            "pancreatic": "Pancreatic Cancer",
            "bladder": "Urothelial Carcinoma",
            "renal": "Renal Cell Carcinoma",
            "cns": "Brain Tumor",
            "esophagogastric": "Esophagogastric Cancer",
            "endometrial": "Endometrial Cancer",
            "sarcoma": "Sarcoma",
            "head_neck": "Head and Neck Cancer",
            "hepatobiliary": "Hepatobiliary Cancer",
            "thyroid": "Thyroid Cancer",
            "cervical": "Cervical Cancer",
            "mesothelioma": "Mesothelioma",
            "other": "Solid Tumor",
        }
        condition = site_map.get(site.lower(), site)
        
        # Build query parameters
        params = {
            "format": "json",
            "query.cond": condition,
            "pageSize": limit,
            "filter.overallStatus": "RECRUITING|NOT_YET_RECRUITING|ACTIVE_NOT_RECRUITING"
        }
        
        # Add biomarkers to the search query if present
        if biomarkers:
            # We use query.term for biomarkers
            params["query.term"] = " OR ".join(biomarkers)
        
        try:
            response = requests.get(self.API_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            trials = self._parse_api_response(data, site)
            self.cache[cache_key] = trials
            return trials
            
        except Exception as e:
            print(f"API Error: {e}. Falling back to local knowledge base.")
            return self._get_fallback_trials(site, biomarkers)

    def _parse_api_response(self, data: Dict[str, Any], site: str) -> List[Dict[str, Any]]:
        """Transforms API v2 schema to ResistanceAI internal schema."""
        parsed = []
        studies = data.get("studies", [])
        
        for study in studies:
            protocol = study.get("protocolSection", {})
            ident = protocol.get("identificationModule", {})
            status = protocol.get("statusModule", {})
            design = protocol.get("designModule", {})
            
            # Extract Phase
            phases = design.get("phases", ["N/A"])
            phase_str = "/".join(phases) if phases else "N/A"
            
            trial_entry = {
                "id": ident.get("nctId", "N/A"),
                "name": ident.get("briefTitle", "Unnamed Trial"),
                "site": site,
                "biomarker": "Matched", # Simplified for result display
                "phase": phase_str,
                "status": status.get("overallStatus", "Unknown"),
                "location": "Global/Multi-Center" # Could drill down into contactsLocationsModule if needed
            }
            parsed.append(trial_entry)
            
        return parsed

    def _get_fallback_trials(self, site: str, biomarkers: List[str] = None) -> List[Dict[str, Any]]:
        """Loads from local trials.json when API is unreachable."""
        if not os.path.exists(self.fallback_path):
            return []
            
        try:
            with open(self.fallback_path, 'r') as f:
                all_trials = json.load(f).get("trials", [])
            
            # Simple keyword matching
            filtered = [
                t for t in all_trials 
                if t['site'].lower() == site.lower() or t['site'].lower() == 'universal'
            ]
            return filtered
        except:
            return []
