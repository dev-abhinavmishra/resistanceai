
import json
import os
import time
import datetime
import threading
from typing import Dict, List, Any, Callable

# Reentrant so the atomic read-modify-write in _mutate() can call the
# lock-taking _load_json/_save_json helpers without deadlocking.
_FILE_LOCK = threading.RLock()


class InstitutionalDB:
    """
    Persistence layer for ResistanceAI Enterprise.
    Stores MTB case resolutions, patient outcomes, and system audit logs
    in local JSON files. Suitable for single-instance deployment; a
    production rollout needs a real database + IAM-backed audit store.
    """
    def __init__(self, data_dir: str = None):
        self.data_dir = data_dir or os.environ.get(
            "RESISTANCEAI_MODEL_DIR", "backend/artifacts")
        self.cases_file = os.path.join(self.data_dir, "case_archive.json")
        self.outcomes_file = os.path.join(self.data_dir, "patient_outcomes.json")
        self.audit_file = os.path.join(self.data_dir, "audit_log.json")
        os.makedirs(self.data_dir, exist_ok=True)

    def _load_json(self, file_path: str) -> List[Any]:
        # Lock held for the read as well: on Windows os.replace() below fails
        # if any thread still has the destination open for reading.
        with _FILE_LOCK:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    try:
                        return json.load(f)
                    except (json.JSONDecodeError, OSError):
                        return []
            return []

    def _save_json(self, file_path: str, data: List[Any]):
        # Write tmp + atomic rename so readers never see a torn file.
        # The retry covers transient lock-holders outside the process
        # (antivirus/indexers) that Windows allows to block a rename.
        with _FILE_LOCK:
            tmp_path = file_path + ".tmp"
            with open(tmp_path, 'w') as f:
                json.dump(data, f, indent=4)
            for attempt in range(5):
                try:
                    os.replace(tmp_path, file_path)
                    return
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.02 * (attempt + 1))

    def _mutate(self, file_path: str, mutate: Callable[[List[Any]], None]):
        """Atomic read-modify-write for append-style ledger updates.

        Holding the lock across load+save prevents lost updates when two
        Streamlit reruns append to the same ledger concurrently.
        """
        with _FILE_LOCK:
            data = self._load_json(file_path)
            mutate(data)
            self._save_json(file_path, data)

    def list_cases(self, limit: int = None) -> List[Any]:
        """Public accessor for archived MTB case records (newest last)."""
        records = self._load_json(self.cases_file)
        return records[-limit:] if limit else records

    def archive_mtb_decision(self, case_id: str, decision: Dict[str, Any]):
        """Saves a formal MTB board resolution and calculates concordance."""
        # Concordance: the board explicitly accepted the AI proposal.
        # (Comparing the suggested therapy *name* to the decision *label*
        # could never match — free-text regimen concordance needs structured
        # regimen codes, which this archive does not capture.)
        board_choice = decision.get("decision")
        concordance = 1.0 if board_choice == "Accept AI Proposal" else 0.0
        decision['concordance'] = concordance

        decision['case_id'] = case_id
        decision['resolved_at'] = datetime.datetime.now().isoformat()
        self._mutate(self.cases_file, lambda records: records.append(decision))
        self.log_audit("MTB_RESOLUTION", f"Case {case_id} resolved. Concordance: {concordance}")

    def log_shadow_entry(self, patient_id: str, ai_output: Dict[str, Any], final_board_action: str = None):
        """Logs entries for Shadow Mode validation (silent tracking)."""
        shadow_file = os.path.join(self.data_dir, "shadow_log.json")
        self._mutate(shadow_file, lambda entries: entries.append({
            "timestamp": datetime.datetime.now().isoformat(),
            "patient_id": patient_id,
            "ai_risk": ai_output.get('risk_score'),
            "ai_therapy": ai_output.get('recommendation', {}).get('therapies', [{}])[0].get('name'),
            "board_action": final_board_action
        }))

    def log_audit(self, event_type: str, details: str, user_id: str = "SYSTEM_ADMIN"):
        """Append an event to the local audit ledger (JSON file).

        Not a HIPAA-compliant audit store on its own — production use needs
        an IAM-backed, tamper-evident audit service."""
        self._mutate(self.audit_file, lambda logs: logs.append({
            "timestamp": datetime.datetime.now().isoformat(),
            "user": user_id,
            "event": event_type,
            "details": details
        }))

    def record_clinical_outcome(self, patient_id: str, outcome: Dict[str, Any]):
        """Formal entry point for post-MTB outcome tracking."""
        outcome['patient_id'] = patient_id
        outcome['timestamp'] = datetime.datetime.now().isoformat()
        self._mutate(self.outcomes_file, lambda outcomes: outcomes.append(outcome))
        self.log_audit("OUTCOME_FOLLOWUP", f"Clinical follow-up recorded for PX {patient_id}.")
