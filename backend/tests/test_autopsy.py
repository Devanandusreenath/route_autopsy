import copy

import pytest

from app import route_autopsy as ra
from app.database import get_all
from tests.conftest import snapshot

REQ = {"origin": "VYT", "destination": "KKD", "vehicleId": "veh-ecomet"}


def analyze(client, **extra):
    r = client.post("/autopsy/analyze", json={**REQ, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def scenario(client, perts, **extra):
    r = client.post("/autopsy/scenario", json={**REQ, "perturbations": perts, **extra})
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ baseline

def test_baseline_calculation(client):
    j = analyze(client, includeDefaultSuite=False)
    b = j["baseline"]
    assert b["recommendedRouteId"] == "VYT-KKD-S6_S13" == j["baselineRecommendation"]["routeId"]
    assert b["suitabilityStatus"] == "suitable" and b["durationMin"] == pytest.approx(20.1, abs=0.1)
    assert b["hazardPenaltySeconds"] > 0
    assert b["route"]["alternatives"] and b["route"]["vehicle"]["id"] == "veh-ecomet"
    assert j["persisted"] is False and j["scenarios"] == [] and j["sensitivity"]["sensitivityScore"] is None


def test_baseline_reports_restrictions_missing_specs_and_unverified_evidence(client):
    j = analyze(client, origin="FKC", destination="ALV", vehicleId="cat-traveller", includeDefaultSuite=False)
    b = j["baseline"]
    assert set(b["missingVehicleSpecs"]) == {"height", "gross vehicle weight"}
    assert any(d["verificationStatus"] != "verified" for d in b["unverifiedEvidence"]["defects"])
    assert any(r["verificationStatus"] != "verified" for r in b["unverifiedEvidence"]["restrictions"])
    assert all(w.get("restrictionId") for w in b["restrictionWarnings"])


def test_baseline_without_vehicle_is_not_validated(client):
    j = client.post("/autopsy/analyze", json={"origin": "VYT", "destination": "KKD", "includeDefaultSuite": False}).json()
    assert j["baseline"]["suitabilityStatus"] == "not_validated" and j["baseline"]["missingVehicleSpecs"] == []


# ------------------------------------------------------------------ single-variable perturbation

def test_single_perturbation_changes_only_the_specified_input(client):
    j = scenario(client, [{"type": "close_segment", "segmentId": "S6"}])
    s = j["scenarios"][0]
    assert s["inputChanged"] and len(s["changedVariables"]) == 1
    assert s["changedVariables"][0] == {"variable": "segment[S6].closure", "from": "none", "to": "hypothetical verified closure"}
    assert s["changed"] is True
    assert s["baselineRecommendation"]["routeId"] == "VYT-KKD-S6_S13"
    assert s["revisedRecommendation"]["routeId"] != "VYT-KKD-S6_S13" and "S6" not in s["revisedRecommendation"]["segmentIds"]
    assert s["baselineRouteUnderScenario"]["statusBefore"] == "suitable" and s["baselineRouteUnderScenario"]["statusAfter"] == "unsuitable"
    assert any("Road closure" in m for m in s["changedWarnings"]["added"])
    assert "would change from route S6 → S13" in s["explanation"] and "unsuitable" in s["explanation"]


def test_every_perturbation_type_supported_and_isolated(client):
    perts = [
        {"type": "resolve_defect", "defectId": "D10"},
        {"type": "verify_restriction", "restrictionId": "R7"},
        {"type": "remove_restriction", "restrictionId": "R1"},
        {"type": "set_vehicle_height", "heightM": 3.0},
        {"type": "set_vehicle_width", "widthM": 2.0},
        {"type": "set_vehicle_weight", "weightKg": 9000},
        {"type": "close_segment", "segmentId": "S13"},
        {"type": "set_evidence_verification", "targetKind": "restriction", "targetId": "R2", "status": "unverified"},
        {"type": "set_evidence_verification", "targetKind": "defect", "targetId": "D3", "status": "verified"},
    ]
    j = scenario(client, perts)
    assert [len(s["changedVariables"]) for s in j["scenarios"]] == [1] * len(perts)  # exactly one input changed per scenario
    assert j["sensitivity"]["scenariosTested"] == len(perts)
    defect_ver = j["scenarios"][-1]
    assert defect_ver["changed"] is False and defect_ver["notes"], "defect verification is not a routing input; the API says so"


def _s12(vehicle):
    from app import routing
    r = routing.compute_routes("VYT", "KKD", vehicle, get_all("defects"), get_all("restrictions"), max_alternatives=100, max_rejected=100)
    return next(x for x in r["routes"] if x["id"] == "VYT-KKD-S12")


def test_vehicle_height_change_removes_only_the_height_reason():
    # Real Ecomet: 3.3 m high and 2.5 m wide. Verified S12 limits: height 3.2 m, width 2.3 m.
    ecomet = next(v for v in get_all("vehicles") if v["id"] == "veh-ecomet")
    before = _s12(ecomet)
    assert before["suitabilityStatus"] == "unsuitable" and any("Height limit" in m for m in before["rejectionReasons"])
    state, changes, _ = ra.apply_perturbation(ra.new_state(ecomet, [], []), {"type": "set_vehicle_height", "heightM": 3.1})
    assert changes == [{"variable": "vehicle.heightM", "from": 3.3, "to": 3.1}]
    after = _s12(state["vehicle"])
    assert after["suitabilityStatus"] == "unsuitable"                      # width still blocks it
    assert not any("Height limit" in m for m in after["rejectionReasons"])  # ...but the height reason is gone
    assert any("Width limit" in m for m in after["rejectionReasons"])


def test_vehicle_height_change_unblocks_route_when_height_is_the_only_problem():
    tall_narrow = {**next(v for v in get_all("vehicles") if v["id"] == "veh-swift"), "id": "tall-narrow", "heightM": 3.3, "widthM": 2.0}
    assert _s12(tall_narrow)["suitabilityStatus"] == "unsuitable"
    state, _c, _d = ra.apply_perturbation(ra.new_state(tall_narrow, [], []), {"type": "set_vehicle_height", "heightM": 3.1})
    assert _s12(state["vehicle"])["suitabilityStatus"] != "unsuitable"


def test_vehicle_height_scenario_via_api(client):
    j = scenario(client, [{"type": "set_vehicle_height", "heightM": 3.1}])
    assert j["scenarios"][0]["changedVariables"] == [{"variable": "vehicle.heightM", "from": 3.3, "to": 3.1}]


def test_unverified_to_verified_restriction_makes_route_unsuitable(client):
    # R5 (length 10 m, unverified) on S2; the Ecomet is 8.6 m so not affected -> use bus (11 m).
    j = client.post("/autopsy/scenario", json={"origin": "FKC", "destination": "KKD", "vehicleId": "veh-bus",
                                               "perturbations": [{"type": "verify_restriction", "restrictionId": "R5"}]}).json()
    s = j["scenarios"][0]
    assert s["changedVariables"] == [{"variable": "restriction[R5].verificationStatus", "from": "unverified", "to": "verified"}]
    assert s["baselineRouteUnderScenario"]["statusBefore"] == "warning" and s["baselineRouteUnderScenario"]["statusAfter"] == "unsuitable"
    assert s["changed"] is True


def test_noop_perturbation_is_skipped_and_excluded_from_score(client):
    j = scenario(client, [{"type": "verify_restriction", "restrictionId": "R1"},   # already verified
                          {"type": "close_segment", "segmentId": "S6"}])
    assert j["scenarios"][0]["skipped"] and not j["scenarios"][0]["inputChanged"]
    assert j["sensitivity"]["scenariosTested"] == 1 and j["sensitivity"]["scenariosSkipped"] == 1


# ------------------------------------------------------------------ multiple scenarios + change detection + sensitivity

def test_default_suite_runs_many_scenarios_and_detects_changes(client):
    j = analyze(client)
    s = j["sensitivity"]
    assert s["scenariosTested"] >= 15 and s["scenariosChanged"] >= 1
    changed_ids = {x["scenarioId"] for x in j["scenarios"] if x["changed"]}
    assert set(s["changedScenarioIds"]) == changed_ids
    # known drivers for this request
    desc = {x["description"] for x in j["scenarios"] if x["changed"]}
    assert any("segment S6" in d for d in desc) and any("D10" in d for d in desc)
    for x in j["scenarios"]:
        assert x["changed"] == (x["baselineRecommendation"]["routeId"] != (x["revisedRecommendation"] or {}).get("routeId"))
    assert j["suite"]["generated"] == len(j["scenarios"])


def test_sensitivity_formula_is_weighted_changed_over_total(client):
    j = scenario(client, [
        {"type": "close_segment", "segmentId": "S6", "weight": 2},              # changes, weight 2
        {"type": "remove_restriction", "restrictionId": "R1"},                  # no change, default weight 1
        {"type": "set_vehicle_height", "heightM": 3.0},                         # no change, default weight 0.5
    ])
    s = j["sensitivity"]
    assert (s["scenariosTested"], s["scenariosChanged"]) == (3, 1)
    assert s["totalWeight"] == 3.5 and s["changedWeight"] == 2.0
    assert s["sensitivityScore"] == pytest.approx(2 / 3.5, abs=1e-4)
    assert "not an accident probability" in s["interpretation"]


def test_sensitivity_zero_when_nothing_changes_and_one_when_all_change(client):
    zero = scenario(client, [{"type": "remove_restriction", "restrictionId": "R1"}])["sensitivity"]
    assert zero["sensitivityScore"] == 0 and zero["scenariosChanged"] == 0
    one = scenario(client, [{"type": "close_segment", "segmentId": "S6"}, {"type": "close_segment", "segmentId": "S13"}])["sensitivity"]
    assert one["sensitivityScore"] == 1.0


def test_autopsy_uses_the_routing_engine_not_its_own(monkeypatch, client):
    calls = []
    real = ra.compute_routes
    monkeypatch.setattr(ra, "compute_routes", lambda *a, **k: calls.append(1) or real(*a, **k))
    scenario(client, [{"type": "close_segment", "segmentId": "S6"}])
    assert len(calls) == 2  # baseline + one scenario, both through routing.compute_routes


# ------------------------------------------------------------------ original database preservation

def test_hypotheticals_never_persist(client):
    before = snapshot()
    destructive = [
        {"type": "resolve_defect", "defectId": "D1"}, {"type": "resolve_defect", "defectId": "D10"},
        {"type": "remove_restriction", "restrictionId": "R2"}, {"type": "verify_restriction", "restrictionId": "R4"},
        {"type": "close_segment", "segmentId": "S6"}, {"type": "set_vehicle_height", "heightM": 1.0},
        {"type": "set_vehicle_weight", "weightKg": 1000}, {"type": "set_evidence_verification", "targetKind": "defect", "targetId": "D3", "status": "verified"},
    ]
    analyze(client, perturbations=destructive)
    scenario(client, destructive)
    assert snapshot() == before
    veh = client.get("/vehicles/veh-ecomet").json()
    assert veh["heightM"] == 3.3 and veh["currentLoadedWeightKg"] == 14000


def test_apply_perturbation_does_not_mutate_its_input():
    state = ra.new_state(get_all("vehicles")[0], get_all("defects"), get_all("restrictions"))
    frozen = copy.deepcopy(state)
    for p in ({"type": "resolve_defect", "defectId": "D1"}, {"type": "remove_restriction", "restrictionId": "R1"}, {"type": "close_segment", "segmentId": "S1"},
              {"type": "set_vehicle_height", "heightM": 1.2}):
        new, changes, _ = ra.apply_perturbation(state, p)
        assert changes and new != state
    assert state == frozen


# ------------------------------------------------------------------ errors & endpoints

@pytest.mark.parametrize("pert,code", [
    ({"type": "resolve_defect", "defectId": "NOPE"}, 422),
    ({"type": "remove_restriction", "restrictionId": "NOPE"}, 422),
    ({"type": "close_segment", "segmentId": "S99"}, 422),
    ({"type": "set_vehicle_height", "heightM": -1}, 422),
    ({"type": "teleport"}, 422),
])
def test_invalid_perturbations_rejected(client, pert, code):
    assert client.post("/autopsy/scenario", json={**REQ, "perturbations": [pert]}).status_code == code


def test_vehicle_perturbation_requires_a_vehicle(client):
    r = client.post("/autopsy/scenario", json={"origin": "VYT", "destination": "KKD", "perturbations": [{"type": "set_vehicle_height", "heightM": 3}]})
    assert r.status_code == 422 and "vehicleId" in r.json()["detail"]


def test_scenario_requires_at_least_one_perturbation(client):
    assert client.post("/autopsy/scenario", json={**REQ, "perturbations": []}).status_code == 422


def test_autopsy_request_errors(client):
    assert client.post("/autopsy/analyze", json={"origin": "XXX", "destination": "KKD"}).status_code == 422
    assert client.post("/autopsy/analyze", json={**REQ, "vehicleId": "nope"}).status_code == 404
    assert client.post("/autopsy/analyze", json={"origin": "VYT", "destination": "VYT"}).status_code == 422


def test_autopsy_health(client):
    j = client.get("/autopsy/health").json()
    assert j["status"] == "ok" and j["persistsHypotheticals"] is False and "close_segment" in j["perturbationTypes"] and j["graph"]["illustrative"]


def test_autopsy_accepts_legacy_field_names(client):
    j = client.post("/autopsy/analyze", json={"originId": "VYT", "destinationId": "KKD", "vehicleId": "veh-swift", "includeDefaultSuite": False}).json()
    assert j["baseline"]["route"]["originId"] == "VYT"


def test_no_invented_incident_history(client):
    text = str(analyze(client)).lower()
    for banned in ("incident", "accident occurred", "crash"):
        assert banned not in text.replace("not an accident probability", "")
