"""Shared defect-creation workflow (used by POST /defects and by evidence confirmation)."""
import uuid
from datetime import datetime, timezone

from .database import put_json
from .pilot import nearest_segment
from .schemas import NewDefectInput


def create_defect_record(data: NewDefectInput, provenance: dict | None = None) -> dict:
    """Identical to the original POST /defects behaviour: always created unverified/open with one report.
    `provenance` adds extra keys (e.g. evidence id) but can never override the verification fields."""
    now = datetime.now(timezone.utc).isoformat()
    defect = {
        **data.model_dump(), "id": "U-" + uuid.uuid4().hex[:8].upper(),
        "roadSegmentId": nearest_segment(data.latitude, data.longitude), "reportedAt": now,
        "verificationStatus": "unverified", "maintenanceStatus": "open", "independentReportCount": 1, "isUserSubmitted": True,
    }
    for k, v in (provenance or {}).items():
        defect.setdefault(k, v)
    put_json("defects", defect["id"], defect)
    return defect
