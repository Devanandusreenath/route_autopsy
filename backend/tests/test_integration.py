import json
import os
import subprocess
import sys
import textwrap

import pytest

from app.main import app

ORIGIN = "http://localhost:5173"


# ------------------------------------------------------------------ CORS

def preflight(client, origin, path="/routes/investigate", method="POST"):
    return client.options(path, headers={"Origin": origin, "Access-Control-Request-Method": method, "Access-Control-Request-Headers": "content-type"})


def test_cors_allows_local_frontend_origins(client):
    for o in ("http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8080", "http://localhost:4173"):
        r = preflight(client, o)
        assert r.status_code == 200 and r.headers["access-control-allow-origin"] == o, o
    r = client.get("/vehicles", headers={"Origin": ORIGIN})
    assert r.headers["access-control-allow-origin"] == ORIGIN


def test_cors_blocks_unlisted_origins(client):
    r = preflight(client, "https://evil.example.com")
    assert "access-control-allow-origin" not in r.headers
    assert "access-control-allow-origin" not in client.get("/vehicles", headers={"Origin": "https://evil.example.com"}).headers


def test_cors_origins_come_from_environment(tmp_path):
    code = textwrap.dedent(f"""
        import os
        os.environ["DATABASE_PATH"] = r"{tmp_path / 'c.db'}"
        os.environ["CORS_ORIGINS"] = "https://app.example.com/, https://lovable.example.dev"
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as c:
            def pf(o): return c.options("/autopsy/analyze", headers={{"Origin": o, "Access-Control-Request-Method": "POST"}}).headers.get("access-control-allow-origin")
            print(pf("https://app.example.com"), pf("https://lovable.example.dev"), pf("https://other.example.com"))
    """)
    out = subprocess.run([sys.executable, "-W", "ignore", "-c", code], capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)), env={k: v for k, v in os.environ.items() if k != "CORS_ORIGINS"})
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-1] == "https://app.example.com https://lovable.example.dev None"


def test_cors_allows_multipart_upload_preflight(client):
    r = preflight(client, ORIGIN, "/evidence/analyze")
    assert r.status_code == 200 and "POST" in r.headers["access-control-allow-methods"]


# ------------------------------------------------------------------ frontend request / response compatibility

ROUTE_KEYS = {"routeId", "origin", "destination", "distanceKm", "durationMin", "segments"}
SEGMENT_KEYS = {"id", "name", "distanceKm", "riskLevel"}


def test_frontend_route_request_and_response_shape(client):
    r = client.post("/routes/investigate", json={"origin": "Fort Kochi", "destination": "Aluva", "vehicleId": "veh-ecomet"})
    j = r.json()
    assert r.status_code == 200 and ROUTE_KEYS <= set(j)
    assert isinstance(j["distanceKm"], float) and isinstance(j["durationMin"], (int, float))
    for s in j["segments"]:
        assert SEGMENT_KEYS <= set(s) and s["riskLevel"] in ("low", "medium", "high")
    # segments must chain from origin to destination
    assert [s["id"] for s in j["segments"]] == j["routeId"].split("-", 2)[2].split("_")
    r2 = client.post("/routes/investigate", json={"origin": "FKC", "destination": "ALV"})  # vehicleId optional, as in the frontend form
    assert r2.status_code == 200 and r2.json()["suitabilityStatus"] == "not_validated"


def test_route_alternatives_preserved_in_compat_response(client):
    j = client.post("/routes/investigate", json={"origin": "FKC", "destination": "ALV", "vehicleId": "veh-ecomet", "maxAlternatives": 2}).json()
    usable = [a for a in j["alternatives"] if a["suitabilityStatus"] != "unsuitable"]
    assert len(usable) == 2 and any(a["suitabilityStatus"] == "unsuitable" and a["rejectionReasons"] for a in j["alternatives"])
    assert "Illustrative" in j["disclaimer"]


def test_riskLevel_is_derived_from_evidence(client):
    j = client.post("/routes/investigate", json={"origin": "VYT", "destination": "TPR", "vehicleId": "veh-swift"}).json()
    assert "S10" not in [s["id"] for s in j["segments"]]  # the recommended route avoids the pothole-ridden direct road
    via_s10 = next(a for a in j["alternatives"] if "S10" in a["segmentIds"])  # the fastest candidate still shows it
    s10 = next(s for s in via_s10["segments"] if s["id"] == "S10")
    assert s10["riskLevel"] == "high" and "pothole" in s10["note"]  # severity>=4 potholes + poor surface
    assert via_s10["severeHazardCount"] >= 2 and not via_s10["recommended"]
    quiet = next(s for a in j["alternatives"] for s in a["segments"] if s["id"] == "S9") if any("S9" in a["segmentIds"] for a in j["alternatives"]) else None
    assert quiet is None or quiet["riskLevel"] in ("low", "medium")


def test_vehicle_adapter_adds_display_fields_and_loses_nothing(client):
    items = client.get("/vehicles").json()
    assert len(items) == 7
    ecomet = next(v for v in items if v["id"] == "veh-ecomet")
    assert ecomet["name"] == "Ashok Leyland Ecomet 2022 1615 HE" and ecomet["type"] == "Heavy truck"
    for k in ("heightM", "widthM", "lengthM", "grossVehicleWeightKg", "currentLoadedWeightKg", "specStatus", "verificationStatus", "sources", "isIllustrative"):
        assert k in ecomet
    assert (ecomet["heightM"], ecomet["widthM"], ecomet["currentLoadedWeightKg"]) == (3.3, 2.5, 14000)
    assert ecomet["specStatus"]["currentLoadedWeightKg"] == "user_confirmed"
    bus = next(v for v in items if v["id"] == "veh-bus")
    assert bus["heightM"] is None and "height" in bus["unknownSpecs"] and "Unknown" in bus["notes"]  # unknown stays unknown, never faked
    assert "maxLoadKg" not in ecomet  # no invented payload figure
    trav = next(v for v in items if v["id"] == "cat-traveller")
    assert trav["verificationStatus"] == "unknown" and set(trav["unknownSpecs"]) == {"height", "gross vehicle weight"}


def test_vehicle_crud_roundtrip_still_works(client):
    one = client.get("/vehicles/veh-swift").json()
    assert one["name"].startswith("Maruti Suzuki Swift")
    saved = client.put("/vehicles", json={**one, "id": "veh-new", "heightM": 1.6}).json()
    assert saved["id"] == "veh-new" and saved["heightM"] == 1.6 and "name" not in saved  # stored model unchanged
    assert client.get("/vehicles/veh-new").json()["name"].startswith("Maruti Suzuki Swift")
    assert client.delete("/vehicles/veh-new").json() == {"id": "veh-new", "deleted": True}
    assert client.get("/vehicles/veh-new").status_code == 404
    assert client.delete("/vehicles/veh-new").status_code == 404


def test_vehicle_roundtrip_through_display_view_is_lossless(client):
    shown = client.get("/vehicles/veh-ecomet").json()
    client.put("/vehicles", json=shown)
    stored = client.get("/vehicles/veh-ecomet").json()
    for k in ("heightM", "widthM", "lengthM", "grossVehicleWeightKg", "currentLoadedWeightKg", "specStatus", "verificationStatus", "category"):
        assert stored[k] == shown[k]


# ------------------------------------------------------------------ existing endpoints preserved

def test_existing_endpoints_still_work(client):
    assert client.get("/health").json()["status"] == "ok" and client.get("/api/health").status_code == 200
    meta = client.get("/api/meta").json()
    assert len(meta["nodes"]) == 10 and len(meta["segments"]) == 16 and meta["demoMode"] is True
    assert len(client.get("/defects").json()) == 15 and len(client.get("/defects?severity_min=5").json()) == 2
    assert len(client.get("/restrictions").json()) == 7
    assert client.get("/roads/S12").json()["restrictions"]
    assert client.get("/roads/nearby", params={"lat": 9.9667, "lon": 76.3186, "radius_m": 500}).json()
    assert client.get("/roads/S99").status_code == 404
    assert client.get("/maintenance/summary").json()["total"] == 15
    assert client.get("/admin/priority-segments").json()[0]["priority"] >= client.get("/admin/priority-segments").json()[-1]["priority"]
    assert client.get("/admin/defects").status_code == 200


def test_existing_defect_workflow_unchanged(client):
    d = client.post("/defects", json={"defectType": "pothole", "latitude": 9.97, "longitude": 76.31, "severity": 3, "description": "t", "observedAt": "2026-10-09T00:00:00Z"})
    assert d.status_code == 201
    j = d.json()
    assert j["verificationStatus"] == "unverified" and j["maintenanceStatus"] == "open" and j["independentReportCount"] == 1 and j["id"].startswith("U-")
    assert client.get(f"/defects/{j['id']}").json()["id"] == j["id"]
    assert client.post(f"/defects/{j['id']}/confirm").json()["verificationStatus"] == "verified"
    assert client.post(f"/defects/{j['id']}/resolve").json()["maintenanceStatus"] == "resolved"
    assert client.patch(f"/defects/{j['id']}/status", json={"status": "under_review"}).json()["status"] == "under_review"
    ins = client.post("/admin/inspections", json={"defectId": "D1", "observedCondition": "bad"})
    assert ins.status_code == 201 and client.get("/defects/D1").json()["maintenanceStatus"] == "inspected"
    rep = client.post("/admin/repairs", json={"defectId": "D2", "completedAt": "2026-10-10T00:00:00Z"})
    assert rep.status_code == 201 and client.get("/defects/D2").json()["maintenanceStatus"] == "resolved"
    assert client.get("/defects/NOPE").status_code == 404


# ------------------------------------------------------------------ error handling

def test_validation_errors_use_fastapi_detail_shape_the_frontend_parses(client):
    r = client.post("/routes/investigate", json={"origin": "", "destination": "ALV"})
    assert r.status_code == 422 and isinstance(r.json()["detail"], list) and {"loc", "msg"} <= set(r.json()["detail"][0])
    r = client.post("/routes/investigate", json={"origin": "XXX", "destination": "ALV"})
    assert isinstance(r.json()["detail"], str) and "FKC" in r.json()["detail"]  # lists valid choices
    assert client.post("/routes/investigate", content="not json", headers={"content-type": "application/json"}).status_code == 422
    assert client.post("/routes/investigate", json={"origin": "x" * 201, "destination": "ALV"}).status_code == 422
    assert client.post("/routes/investigate", json={"origin": "FKC", "destination": "ALV", "maxAlternatives": 99}).status_code == 422


def test_unknown_routes_404_and_wrong_method_405(client):
    assert client.get("/nope").status_code == 404
    assert client.get("/routes/investigate").status_code == 405
    assert client.get("/autopsy/analyze").status_code == 405


def test_errors_do_not_leak_internals(client):
    for r in (client.post("/autopsy/analyze", json={"origin": "ZZZ", "destination": "ALV"}), client.post("/evidence/confirm", json={"evidenceId": "x", "confirmedObservationIds": []})):
        assert "Traceback" not in r.text and "routewise" not in r.text.lower().replace("routewise ai", "")


# ------------------------------------------------------------------ OpenAPI

def test_openapi_schema_generates_and_documents_new_endpoints(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    for p in ("/routes/investigate", "/autopsy/analyze", "/autopsy/scenario", "/autopsy/health", "/evidence/analyze", "/evidence/confirm", "/routes", "/vehicles", "/defects"):
        assert p in spec["paths"], p
    assert "multipart/form-data" in spec["paths"]["/evidence/analyze"]["post"]["requestBody"]["content"]
    comps = spec["components"]["schemas"]
    for name in ("RouteInvestigationResponse", "AutopsyResponse", "EvidenceAnalyzeResponse", "EvidenceObservation", "ScenarioResult"):
        assert name in comps, name
    pert = json.dumps(comps["AutopsyScenarioRequest"])
    assert "set_vehicle_height" in json.dumps(spec) and "perturbations" in pert
    json.dumps(spec)  # fully serialisable


def test_openapi_exposes_no_secret_fields(client):
    text = client.get("/openapi.json").text.lower()
    assert "api_key" not in text and "bearer" not in text


def test_all_response_models_validate_real_output(client):
    """response_model validation runs on every call; a 500 here would mean a schema/engine drift."""
    for body in ({"origin": "FKC", "destination": "ALV", "vehicleId": "veh-ecomet"}, {"origin": "VYT", "destination": "KKD"}, {"origin": "ERS", "destination": "TPR", "vehicleId": "veh-bus"}):
        assert client.post("/routes/investigate", json=body).status_code == 200
        assert client.post("/autopsy/analyze", json=body).status_code == 200
