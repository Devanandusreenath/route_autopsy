"""Tests for the Phase 2-4 backend additions: scenario comparison data, vehicle restriction check, evidence status."""
import json

import pytest

from app import config, routing
from app.database import get_all

REQ = {"origin": "VYT", "destination": "KKD", "vehicleId": "veh-ecomet"}


def analyze(client, **kw):
    r = client.post("/autopsy/analyze", json={**REQ, **kw})
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ scenario comparison / revisedRoute

def test_changed_scenario_carries_full_revised_route_and_comparison(client):
    j = analyze(client)
    base_route = next(a for a in j["baseline"]["route"]["alternatives"] if a["recommended"])
    changed = [s for s in j["scenarios"] if s["changed"]]
    assert changed, "expected at least one recommendation change on this request"
    for s in changed:
        rr, cmp = s["revisedRoute"], s["comparison"]
        assert rr is not None and rr["routeId"] == s["revisedRecommendation"]["routeId"] and rr["geometry"] and rr["segments"]
        assert cmp["routeIdBefore"] == base_route["routeId"] and cmp["routeIdAfter"] == rr["routeId"]
        assert set(cmp["segmentsRemoved"]) == set(base_route["segmentIds"]) - set(rr["segmentIds"])
        assert set(cmp["segmentsAdded"]) == set(rr["segmentIds"]) - set(base_route["segmentIds"])
        assert set(cmp["segmentsShared"]) == set(base_route["segmentIds"]) & set(rr["segmentIds"])
        assert cmp["durationMinBefore"] == base_route["durationMin"] and cmp["durationMinAfter"] == rr["durationMin"]
        assert s["deltaDurationMin"] == pytest.approx(cmp["durationMinAfter"] - cmp["durationMinBefore"], abs=0.11)


def test_stable_scenario_has_no_revised_route_but_explains_margin(client):
    j = analyze(client)
    stable = [s for s in j["scenarios"] if s["inputChanged"] and not s["changed"]]
    assert stable
    for s in stable:
        assert s["revisedRoute"] is None
        cmp = s["comparison"]
        assert cmp["routeIdBefore"] == cmp["routeIdAfter"] == j["baselineRecommendation"]["routeId"]
    s = next(x for x in stable if x["comparison"]["revisedRunnerUp"])
    assert "score lead over the runner-up" in s["explanation"]


def test_margin_is_runner_up_score_minus_recommendation_score(client):
    j = analyze(client)
    s = next(x for x in j["scenarios"] if not x["changed"] and x["comparison"]["baselineRunnerUp"])
    cmp = s["comparison"]
    assert cmp["baselineMarginSeconds"] == cmp["baselineRunnerUp"]["scoreSeconds"] - cmp["scoreSecondsBefore"]
    assert cmp["baselineMarginSeconds"] >= 0  # the recommendation never trails the runner-up


def test_resolving_a_defect_can_change_score_without_changing_recommendation(client):
    # D3 (severity 4, S12) is not on the recommended route: resolving it leaves recommendation, score and margin unchanged.
    s = client.post("/autopsy/scenario", json={**REQ, "perturbations": [{"type": "resolve_defect", "defectId": "D3"}]}).json()["scenarios"][0]
    assert not s["changed"] and s["comparison"]["scoreSecondsBefore"] == s["comparison"]["scoreSecondsAfter"]
    # D1 resolution on a route it sits on lowers that route's score
    s2 = client.post("/autopsy/scenario", json={"origin": "VYT", "destination": "TPR", "vehicleId": "veh-swift",
                                                "perturbations": [{"type": "resolve_defect", "defectId": "D10"}]}).json()["scenarios"][0]
    cmp = s2["comparison"]
    assert cmp["scoreSecondsAfter"] <= cmp["scoreSecondsBefore"]


def _closure(sid):
    return {"id": f"T-CLOSE-{sid}", "roadSegmentId": sid, "restrictionType": "closure", "limitValue": None, "unit": None, "appliesTo": "all",
            "description": "test closure", "source": "test", "verificationStatus": "verified", "lastVerifiedAt": None}


def test_baseline_with_no_usable_route_then_scenario_restores_one():
    from app import route_autopsy as ra
    vehicle = next(v for v in get_all("vehicles") if v["id"] == "veh-swift")
    restrictions = get_all("restrictions") + [_closure("S1"), _closure("S2")]
    out = ra.analyze("FKC", "ALV", vehicle, get_all("defects"), restrictions, perturbations=[{"type": "remove_restriction", "restrictionId": "T-CLOSE-S1"}],
                     include_default_suite=False)
    assert out["baselineRecommendation"] is None and out["baseline"]["recommendedRouteId"] is None
    s = out["scenarios"][0]
    cmp = s["comparison"]
    assert s["changed"] is True and s["baselineRecommendation"] is None and s["revisedRoute"] is not None
    assert cmp["routeIdBefore"] is None and cmp["routeIdAfter"] == s["revisedRoute"]["routeId"]
    assert cmp["durationMinBefore"] is None and cmp["segmentsRemoved"] == [] and cmp["baselineMarginSeconds"] is None
    assert "Previously no route was usable" in s["explanation"]


def test_scenario_that_does_not_touch_the_baseline_route_reports_stable_comparison(client):
    # swift FKC->ALV baseline starts with S1; closing S2 cannot affect it.
    s = client.post("/autopsy/scenario", json={"origin": "FKC", "destination": "ALV", "vehicleId": "veh-swift",
                                               "perturbations": [{"type": "close_segment", "segmentId": "S2"}]}).json()["scenarios"][0]
    assert s["changed"] is False and s["revisedRoute"] is None and s["comparison"]["routeIdBefore"] == s["comparison"]["routeIdAfter"]


def test_autopsy_payload_stays_reasonably_small(client):
    assert len(json.dumps(analyze(client))) < 200_000


# ------------------------------------------------------------------ vehicle restriction check

def test_restriction_check_404(client):
    assert client.get("/vehicles/nope/restriction-check").status_code == 404


def test_restriction_check_ecomet(client):
    j = client.get("/vehicles/veh-ecomet/restriction-check").json()
    by = {i["restrictionId"]: i for i in j["items"]}
    assert j["vehicleName"].startswith("Ashok Leyland Ecomet") and len(j["items"]) == 7
    assert by["R1"]["outcome"] == "blocks" and by["R1"]["vehicleValue"] == 14.0 and by["R1"]["segmentName"]
    assert by["R2"]["outcome"] == "blocks" and by["R3"]["outcome"] == "blocks"
    assert by["R4"]["outcome"] == "may_block" and by["R5"]["outcome"] == "fits"
    assert sum(j["summary"].values()) == 7 and j["summary"]["blocks"] == 3


def test_restriction_check_surfaces_unknown_specs_not_guesses(client):
    j = client.get("/vehicles/cat-traveller/restriction-check").json()
    assert set(j["unknownSpecs"]) == {"height", "gross vehicle weight"}
    by = {i["restrictionId"]: i for i in j["items"]}
    assert by["R2"]["outcome"] == "unknown_spec" and by["R2"]["vehicleValue"] is None  # height unknown -> never "fits"
    assert by["R1"]["outcome"] == "unknown_spec"
    assert j["summary"]["unknown_spec"] >= 2


@pytest.mark.parametrize("vid", ["veh-swift", "veh-ecomet", "veh-bus", "cat-traveller"])
def test_restriction_check_matches_routing_engine_for_every_restriction(vid):
    """check_restriction() must agree with evaluate_path() on each restriction, or the UI could contradict routing."""
    vehicle = next(v for v in get_all("vehicles") if v["id"] == vid)
    for r in get_all("restrictions"):
        outcome, _val, _msg = routing.check_restriction(r, vehicle)
        warnings, _m, status, _h = routing.evaluate_path([r["roadSegmentId"]], vehicle, [], [r])
        mine = [w for w in warnings if w.get("restrictionId") == r["id"]]
        if outcome == "blocks":
            assert any(w["level"] == "critical" for w in mine) and status == "unsuitable", (vid, r["id"])
        elif outcome == "may_block":
            assert mine and all(w["level"] == "warning" for w in mine), (vid, r["id"])
        elif outcome == "unknown_spec":
            assert mine and "unknown" in mine[0]["message"], (vid, r["id"])
        else:  # fits / not_applicable
            assert not mine, (vid, r["id"], mine)


def test_every_catalogue_vehicle_is_checkable(client):
    for v in client.get("/vehicles").json():
        assert client.get(f"/vehicles/{v['id']}/restriction-check").status_code == 200


# ------------------------------------------------------------------ evidence status

def test_evidence_status_unconfigured(client):
    j = client.get("/evidence/status").json()
    assert j["configured"] is False and j["supportedProvider"] is True and j["model"] is None
    assert "not configured" in j["message"] and j["maxUploadBytes"] == config.EVIDENCE_MAX_UPLOAD_BYTES
    assert j["acceptedTypes"] == ["image/jpeg", "image/png", "image/webp"]


def test_evidence_status_configured_never_exposes_key(client, monkeypatch):
    monkeypatch.setattr(config, "META_API_KEY", "sk-SECRET-XYZ")
    monkeypatch.setattr(config, "META_MODEL", "muse-test")
    r = client.get("/evidence/status")
    j = r.json()
    assert j["configured"] is True and j["model"] == "muse-test" and "SECRET" not in r.text


def test_evidence_status_unsupported_provider(client, monkeypatch):
    monkeypatch.setattr(config, "META_PROVIDER", "other")
    monkeypatch.setattr(config, "META_API_KEY", "k")
    monkeypatch.setattr(config, "META_MODEL", "m")
    j = client.get("/evidence/status").json()
    assert j["configured"] is False and j["supportedProvider"] is False
