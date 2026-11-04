"""Capture REAL backend responses as JSON fixtures for the frontend's contract test (vitest + zod).

Usage (from backend/):  python scripts/generate_contract_fixtures.py ../frontend/src/test/fixtures
Uses a throw-away temp database and a fake vision client (no network, no credentials).
"""
import json
import os
import sys
import tempfile

os.environ["DATABASE_PATH"] = os.path.join(tempfile.mkdtemp(), "fixtures.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.routers_evidence import get_vision_client  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
MODEL_REPLY = json.dumps({"imageQuality": "good", "observations": [
    {"observationType": "pothole", "description": "Deep pothole in the left lane.", "severityEstimate": 4, "visualConfidence": 0.9, "observedAttributes": {"approxSize": "large"}},
    {"observationType": "restriction_sign", "description": "Sign that appears to show a height limit.", "visualConfidence": 0.8, "observedAttributes": {"signText": "3.5m"}, "extraThing": 1}]})


class Fake:
    provider, model = "meta_model_api", "fixture-model"

    def complete_with_image(self, **_):
        return MODEL_REPLY


def main(out):
    os.makedirs(out, exist_ok=True)
    w = lambda name, r: (json.dump(r.json(), open(os.path.join(out, name + ".json"), "w"), indent=1), print("wrote", name, r.status_code))  # noqa: E731
    with TestClient(app) as c:
        app.dependency_overrides[get_vision_client] = lambda: Fake()
        w("network", c.get("/api/meta"))
        w("vehicles", c.get("/vehicles"))
        w("restrictions", c.get("/restrictions"))
        w("defects", c.get("/defects"))
        w("restriction_check_ecomet", c.get("/vehicles/veh-ecomet/restriction-check"))
        w("restriction_check_traveller", c.get("/vehicles/cat-traveller/restriction-check"))
        w("evidence_status", c.get("/evidence/status"))
        w("route_ecomet", c.post("/routes/investigate", json={"origin": "FKC", "destination": "ALV", "vehicleId": "veh-ecomet"}))
        w("route_no_vehicle", c.post("/routes/investigate", json={"origin": "VYT", "destination": "KKD"}))
        req = {"origin": "VYT", "destination": "KKD", "vehicleId": "veh-ecomet"}
        w("autopsy_analyze", c.post("/autopsy/analyze", json=req))
        w("autopsy_scenario", c.post("/autopsy/scenario", json={**req, "perturbations": [{"type": "close_segment", "segmentId": "S6"}, {"type": "set_vehicle_height", "heightM": 3.0}]}))
        w("autopsy_traveller", c.post("/autopsy/analyze", json={"origin": "FKC", "destination": "ALV", "vehicleId": "cat-traveller"}))
        ev = c.post("/evidence/analyze", files={"file": ("a.jpg", JPEG, "image/jpeg")}, data={"latitude": "10.0", "longitude": "76.3"})
        w("evidence_analyze", ev)
        conf = c.post("/evidence/confirm", json={"evidenceId": ev.json()["evidenceId"], "confirmedObservationIds": ["obs-1", "obs-2"]})
        w("evidence_confirm", conf)
        w("defect_created", c.get("/defects/" + conf.json()["results"][0]["defectId"]))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "fixtures")
