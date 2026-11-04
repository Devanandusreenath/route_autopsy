import pytest

from app import routing
from app.database import get_all
from app.pilot import NODES, SEGMENT_BY_ID

ALL_VEH = None


def closure(sid, verified=True, rid=None):
    return {"id": rid or f"T-CLOSE-{sid}", "roadSegmentId": sid, "restrictionType": "closure", "limitValue": None, "unit": None, "appliesTo": "all",
            "description": "test closure", "source": "test", "verificationStatus": "verified" if verified else "unverified", "lastVerifiedAt": None}


def compute(o, d, vehicle, defects=None, restrictions=None, **kw):
    return routing.compute_routes(o, d, vehicle, get_all("defects") if defects is None else defects,
                                  get_all("restrictions") if restrictions is None else restrictions, **kw)


def veh(vehicles, vid):
    return vehicles[vid]


# ------------------------------------------------------------------ basic validity

def test_valid_origin_destination_legacy_and_new(client, vehicles):
    body = {"originId": "FKC", "destinationId": "ALV", "vehicle": vehicles["veh-swift"]}
    legacy = client.post("/routes", json=body)
    assert legacy.status_code == 200 and isinstance(legacy.json(), list) and legacy.json()
    new = client.post("/routes/investigate", json={"origin": "FKC", "destination": "ALV", "vehicleId": "veh-swift"})
    assert new.status_code == 200
    j = new.json()
    assert j["routeId"] and j["distanceKm"] > 0 and j["durationMin"] > 0 and j["segments"]
    assert j["origin"] == "Fort Kochi" and j["destination"] == "Aluva"


@pytest.mark.parametrize("path,body", [
    ("/routes", {"originId": "NOPE", "destinationId": "ALV"}),
    ("/routes", {"originId": "FKC", "destinationId": "NOPE"}),
    ("/routes/investigate", {"origin": "Atlantis", "destination": "ALV"}),
    ("/routes/investigate", {"origin": "FKC", "destination": "Atlantis"}),
])
def test_invalid_nodes_rejected_with_422(client, path, body):
    r = client.post(path, json=body)
    assert r.status_code == 422
    assert "detail" in r.json()


def test_same_origin_destination(client):
    assert client.post("/routes", json={"originId": "FKC", "destinationId": "FKC"}).json() == []  # legacy behaviour preserved
    r = client.post("/routes/investigate", json={"origin": "FKC", "destination": "Fort Kochi"})
    assert r.status_code == 422 and "different" in r.json()["detail"]


def test_node_names_resolve_case_insensitively(client):
    r = client.post("/routes/investigate", json={"origin": "fort kochi", "destination": "aluva"})
    assert r.status_code == 200 and r.json()["originId"] == "FKC"


def test_unknown_vehicle_is_404(client):
    assert client.post("/routes/investigate", json={"origin": "FKC", "destination": "ALV", "vehicleId": "nope"}).status_code == 404


def test_multiple_alternatives_returned(client):
    j = client.post("/routes/investigate", json={"origin": "FKC", "destination": "ALV", "vehicleId": "veh-swift"}).json()
    assert len(j["alternatives"]) >= 3
    assert sum(a["recommended"] for a in j["alternatives"]) == 1
    assert j["search"]["candidatesEvaluated"] == j["search"]["candidatesEnumerated"] == 28


# ------------------------------------------------------------------ the top-3 limitation

def _top3_by_duration_ids(o, d, vehicle):
    res = compute(o, d, vehicle, max_alternatives=100, max_rejected=100)
    return [r["id"] for r in sorted(res["routes"], key=lambda r: r["durationSeconds"])[:3]]


def test_full_evaluation_beats_top3_shortcut(vehicles):
    """Original engine only scored the 3 fastest paths. On veh-swift FKC->TPR the best route is the 4th+ fastest."""
    v = vehicles["veh-swift"]
    res = compute("FKC", "TPR", v)
    idx = res["index"]
    by_duration = sorted(idx.items(), key=lambda kv: kv[1]["durationSeconds"])
    order = [k for k, _ in by_duration]
    assert res["recommendedId"] == "FKC-TPR-S1_S3_S5_S13_S11"
    assert order.index(res["recommendedId"]) >= 3, "recommended route is NOT among the 3 fastest candidates"
    top3_best = min(order[:3], key=lambda k: (routing.STATUS_RANK[idx[k]["status"]], idx[k]["scoreSeconds"]))
    assert idx[res["recommendedId"]]["scoreSeconds"] < idx[top3_best]["scoreSeconds"]


def test_slower_suitable_route_found_when_fastest_candidates_unsuitable(vehicles):
    v = vehicles["veh-swift"]
    base = compute("FKC", "ALV", v)
    closures = []
    # Close segments on the fastest candidates (never a cut-edge that would leave NO usable route) until the 3 fastest are unsuitable.
    for _ in range(8):
        cur = compute("FKC", "ALV", v, restrictions=get_all("restrictions") + closures, max_alternatives=100, max_rejected=100)["index"]
        top3 = sorted(cur.items(), key=lambda kv: kv[1]["durationSeconds"])[:3]
        live = [(k, ix) for k, ix in top3 if ix["status"] != "unsuitable"]
        if not live:
            break
        for sid in live[0][1]["segmentIds"]:
            trial = closures + [closure(sid)]
            if compute("FKC", "ALV", v, restrictions=get_all("restrictions") + trial)["recommendedId"] is not None:
                closures = trial
                break
        else:
            pytest.fail("could not construct scenario")
    res = compute("FKC", "ALV", v, restrictions=get_all("restrictions") + closures)
    ranked_by_duration = sorted(res["index"].items(), key=lambda kv: kv[1]["durationSeconds"])
    assert all(ix["status"] == "unsuitable" for _, ix in ranked_by_duration[:3])
    assert res["recommendedId"] is not None, "a usable slower route must still be discovered"
    assert [k for k, _ in ranked_by_duration].index(res["recommendedId"]) >= 3
    assert res["index"][res["recommendedId"]]["status"] != "unsuitable"
    rec = next(r for r in res["routes"] if r["recommended"])
    assert "recommended" in rec["explanation"]
    # the fastest (rejected) candidate is still shown and explained
    fastest = next(r for r in res["routes"] if r["isFastestCandidate"])
    assert fastest["suitabilityStatus"] == "unsuitable" and "rejected" in fastest["explanation"] and fastest["rejectionReasons"]
    assert base["recommendedId"] != res["recommendedId"] or closures


def test_no_usable_route_means_no_recommendation(vehicles):
    v = vehicles["veh-swift"]
    res = compute("FKC", "ALV", v, restrictions=get_all("restrictions") + [closure("S1"), closure("S2")])
    assert res["recommendedId"] is None
    assert all(not r["recommended"] for r in res["routes"])
    assert all(r["suitabilityStatus"] == "unsuitable" for r in res["routes"])
    inv = routing and None  # noqa
    from app.compat import build_investigation
    out = build_investigation("FKC", "ALV", v, get_all("defects"), get_all("restrictions") + [closure("S1"), closure("S2")])
    assert out["recommended"] is False and out["recommendationStatus"] == "no_usable_route"


# ------------------------------------------------------------------ status states + hard constraints

def statuses(res):
    return {r["id"]: r["suitabilityStatus"] for r in res["routes"]}


def test_height_restriction_verified_blocks_tall_vehicle(vehicles):
    res = compute("VYT", "KKD", vehicles["veh-ecomet"])  # 3.3 m vs verified 3.2 m on S12
    s12 = statuses(res)["VYT-KKD-S12"]
    assert s12 == "unsuitable"
    r = next(r for r in res["routes"] if r["id"] == "VYT-KKD-S12")
    assert any("Height limit" in m for m in r["rejectionReasons"])
    assert statuses(compute("VYT", "KKD", vehicles["veh-swift"]))["VYT-KKD-S12"] != "unsuitable"


def test_width_restriction_verified_blocks_wide_vehicle(vehicles):
    wide = {**vehicles["veh-swift"], "id": "wide", "widthM": 2.5, "heightM": 2.0}
    res = compute("VYT", "KKD", wide)
    r = next(r for r in res["routes"] if r["id"] == "VYT-KKD-S12")
    assert r["suitabilityStatus"] == "unsuitable" and any("Width limit" in m for m in r["rejectionReasons"])


def test_weight_restriction_verified_blocks_heavy_vehicle(vehicles):
    res = compute("FKC", "ERS", vehicles["veh-ecomet"])
    direct = next(r for r in res["routes"] if r["id"] == "FKC-ERS-S1")
    assert direct["suitabilityStatus"] == "unsuitable" and any("Weight limit" in m for m in direct["rejectionReasons"])
    light = compute("FKC", "ERS", vehicles["veh-swift"])
    assert statuses(light)["FKC-ERS-S1"] != "unsuitable"


def test_road_closure_verified_unsuitable_unverified_warning(vehicles):
    v = vehicles["veh-swift"]
    verified = compute("VYT", "KKD", v, restrictions=get_all("restrictions") + [closure("S6")])
    assert statuses(verified)["VYT-KKD-S6_S13"] == "unsuitable"
    unverified = compute("VYT", "KKD", v, restrictions=get_all("restrictions") + [closure("S6", verified=False)])
    assert statuses(unverified)["VYT-KKD-S6_S13"] == "warning"


def full_status(o, d, vehicle):
    res = compute(o, d, vehicle, max_alternatives=100, max_rejected=100)
    return {k: v["status"] for k, v in res["index"].items()}, res


def test_state_distinction_all_four(vehicles):
    # unknown height (traveller van, width 2.0 m OK) vs a height limit on S12 -> cannot confirm clearance -> warning
    st, _ = full_status("VYT", "KKD", vehicles["cat-traveller"])
    assert st["VYT-KKD-S12"] == "warning"
    # no vehicle at all -> everything is not_validated
    st_none, _ = full_status("VYT", "KKD", None)
    assert set(st_none.values()) == {"not_validated"}
    # the 2.6 m wide bus is blocked on S12 by the verified 2.3 m width limit even though its height is unknown
    st_bus, _ = full_status("VYT", "KKD", vehicles["veh-bus"])
    assert st_bus["VYT-KKD-S12"] == "unsuitable"
    allst = {s for vid in ("veh-swift", "veh-ecomet") for o, d in (("FKC", "ALV"), ("VYT", "KKD")) for s in full_status(o, d, vehicles[vid])[0].values()}
    assert {"suitable", "warning", "unsuitable"} <= allst


def test_missing_vehicle_information_reported(vehicles):
    res = compute("ERS", "TPR", vehicles["veh-bus"])
    assert any("height" in m for r in res["routes"] for m in r["missingData"])
    st, full = full_status("VYT", "KKD", vehicles["cat-traveller"])
    assert any("height" in m and "gross vehicle weight" in m for r in full["routes"] for m in r["missingData"])
    assert st["VYT-KKD-S12"] != "suitable"
    # unknown specs never silently count as "fits": the S12 evaluation carries an explicit 'unknown' warning
    from app import routing as rt
    w, _m, status, _h = rt.evaluate_path(["S12"], vehicles["cat-traveller"], get_all("defects"), get_all("restrictions"))
    assert status == "warning" and any("unknown" in x["message"] for x in w)


def test_preserved_penalties(vehicles):
    v = vehicles["veh-swift"]
    with_pen = compute("VYT", "KKD", v)
    without = compute("VYT", "KKD", v, avoid_severe=False, prefer_surfaces=False)
    a = next(r for r in with_pen["routes"] if r["id"] == "VYT-KKD-S12")
    b = next(r for r in without["routes"] if r["id"] == "VYT-KKD-S12")
    assert a["scoreSeconds"] > b["scoreSeconds"] == a["durationSeconds"]
    assert a["scoreBreakdown"]["surfacePenaltySeconds"] > 0  # S12 has a poor surface


# ------------------------------------------------------------------ search bounds

def test_enumeration_is_bounded_and_acyclic():
    paths, truncated = routing.enumerate_paths_bounded("FKC", "ALV", max_depth=6)
    assert not truncated and len(paths) == 28
    for p in paths:
        nodes = ["FKC"]
        for sid in p:
            s = SEGMENT_BY_ID[sid]
            nodes.append(s["to"] if s["from"] == nodes[-1] else s["from"])
        assert len(nodes) == len(set(nodes)), "path revisits a node"
    capped, trunc = routing.enumerate_paths_bounded("FKC", "ALV", max_paths=5)
    assert len(capped) == 5 and trunc
    _, trunc2 = routing.enumerate_paths_bounded("FKC", "ALV", max_expansions=10)
    assert trunc2
    assert len(routing.enumerate_paths("FKC", "ALV", max_depth=3)) < 28
    assert routing.enumerate_paths("FKC", "FKC") == [[]]


def test_every_node_pair_terminates_quickly(vehicles):
    import time
    t = time.time()
    n = 0
    for a in NODES:
        for b in NODES:
            if a["id"] != b["id"]:
                compute(a["id"], b["id"], vehicles["veh-swift"])
                n += 1
    assert n == 90 and time.time() - t < 20


def test_search_truncation_is_reported(client):
    from app.compat import build_investigation
    out = build_investigation("FKC", "ALV", None, get_all("defects"), get_all("restrictions"), result=compute("FKC", "ALV", None, max_candidates=4))
    assert out["search"]["truncated"] is True


# ------------------------------------------------------------------ legacy API compatibility

LEGACY_KEYS = {"id", "label", "segmentIds", "distanceMeters", "durationSeconds", "geometry", "knownHazards", "severeHazardCount", "warnings",
               "missingData", "surfaceMeters", "suitabilityStatus", "recommended", "explanation"}


def test_legacy_route_shape_preserved(client, vehicles):
    items = client.post("/routes", json={"originId": "VYT", "destinationId": "KKD", "vehicle": vehicles["veh-ecomet"]}).json()
    for it in items:
        assert LEGACY_KEYS <= set(it)
    assert [i["durationSeconds"] for i in items] == sorted(i["durationSeconds"] for i in items)  # still fastest-first
    assert [i["label"] for i in items][:3] == ["Route A", "Route B", "Route C"]
    assert sum(i["recommended"] for i in items) == 1


def test_legacy_function_names_still_importable():
    from app import main
    for name in ("enumerate_paths", "oriented_geometry", "applies", "vehicle_value", "evaluate_path", "route_explanation", "calculate_routes", "nearest_segment"):
        assert callable(getattr(main, name))
