"""Shared access to the ingested patient corpus (lazy, process-cached).

Both MSK-IMPACT and MSK-CHORD use the same P-XXXXXXX patient/sample id
namespace, so ids collide across cohorts (~4.2k patients). Every consumer
must key records by `record_uid` (``"<cohort>:<id>"``) — never by the bare
patient_id/sample_id, which does not identify a unique patient.
"""

import json
import os
from functools import lru_cache

DATA_DIR = os.environ.get("RESISTANCEAI_DATA_DIR", "backend/data")
RECORDS_PATH = os.path.join(DATA_DIR, "patient_records.jsonl")


def data_path(name: str) -> str:
    """Path inside the corpus directory (override via RESISTANCEAI_DATA_DIR)."""
    return os.path.join(DATA_DIR, name)


def record_uid(record: dict) -> str:
    """Globally-unique patient key: cohort-qualified patient_id."""
    return f"{record['cohort']}:{record['patient_id']}"


def record_sample_uid(record: dict) -> str:
    """Globally-unique sample key: cohort-qualified sample_id."""
    return f"{record['cohort']}:{record['sample_id']}"


@lru_cache(maxsize=1)
def load_records(path: str = RECORDS_PATH):
    recs = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                recs.append(json.loads(line))
    return tuple(recs)
