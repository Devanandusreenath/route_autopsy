"""Route Autopsy: how sensitive is a routing recommendation to its underlying evidence?

This module contains NO routing logic of its own. Every baseline and every
counterfactual is computed by `routing.compute_routes` on in-memory deep copies
of the evidence. Nothing here writes to SQLite.

Sensitivity is a transparent robustness measure of the *recommendation* against
the *tested perturbations*. It is NOT an accident probability, a failure
probability, or a verified road-safety risk.
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Any

from .compat import DISCLAIMER, alternative_out, build_investigation, to_display_vehicle, unknown_specs
from .pilot import SEGMENT_BY_ID
from .routing import STATUS_RANK, applies, compute_routes

MAX_SCENARIOS = 60
VEHICLE_DELTA = 0.10  # +/-10% vehicle dimension/weight perturbations in the default suite

# Sensitivity weights (documented in README). Evidence perturbations are discrete facts that
# could be true or false, so they weigh 1.0. Vehicle-spec perturbations use an arbitrary +/-10%
# magnitude, so they weigh 0.5.
WEIGHTS = {
    "resolve_defect": 1.0, "verify_restriction": 1.0, "remove_restriction": 1.0, "close_segment": 1.0,
    "set_evidence_verification": 1.0, "set_vehicle_height": 0.5, "set_vehicle_width": 0.5, "set_vehicle_weight": 0.5,
}
FORMULA = "F = sum(weight_i for perturbations that change the selected recommendation) / sum(weight_i for all tested perturbations)"
INTERPRETATION = ("F measures how fragile the route recommendation is to the tested changes in evidence. "
                  "It is not an accident probability, a failure probability, or a verified road-safety risk.")


class ScenarioError(Exception):
    """A requested perturbation references something that does not exist."""


def new_state(vehicle, defects, restrictions) -> dict:
    return {"vehicle": copy.deepcopy(vehicle), "defects": copy.deepcopy(defects), "restrictions": copy.deepcopy(restrictions)}


def _find(items, key):
    return next((x for x in items if x.get("id") == key), None)


def apply_perturbation(state: dict, p: dict) -> tuple[dict, list[dict], str]:
    """Return (modified COPY of state, changedVariables, human description). Never mutates `state`."""
    s = copy.deepcopy(state)
    t = p["type"]
    changes: list[dict] = []
    if t == "resolve_defect":
        d = _find(s["defects"], p["defectId"])
        if d is None:
            raise ScenarioError(f"Unknown defect '{p['defectId']}'")
        desc = f"defect {d['id']} ({d['defectType'].replace('_', ' ')}, severity {d['severity']}) is resolved"
        if d.get("maintenanceStatus") != "resolved":
            changes.append({"variable": f"defect[{d['id']}].maintenanceStatus", "from": d.get("maintenanceStatus"), "to": "resolved"})
            d["maintenanceStatus"] = "resolved"
    elif t in ("verify_restriction", "remove_restriction") or (t == "set_evidence_verification" and p["targetKind"] == "restriction"):
        rid = p["restrictionId"] if t != "set_evidence_verification" else p["targetId"]
        r = _find(s["restrictions"], rid)
        if r is None:
            raise ScenarioError(f"Unknown restriction '{rid}'")
        label = f"{r['restrictionType']} restriction {r['id']} on {r['roadSegmentId']}"
        if t == "remove_restriction":
            desc = f"{label} is removed"
            s["restrictions"] = [x for x in s["restrictions"] if x.get("id") != rid]
            changes.append({"variable": f"restriction[{rid}]", "from": "present", "to": "removed"})
        else:
            target = "verified" if t == "verify_restriction" else p["status"]
            desc = f"{label} is {'verified' if target == 'verified' else 'treated as unverified'}"
            if r.get("verificationStatus") != target:
                changes.append({"variable": f"restriction[{rid}].verificationStatus", "from": r.get("verificationStatus"), "to": target})
                r["verificationStatus"] = target
    elif t == "set_evidence_verification":  # defect
        d = _find(s["defects"], p["targetId"])
        if d is None:
            raise ScenarioError(f"Unknown defect '{p['targetId']}'")
        desc = f"defect {d['id']} is {'verified' if p['status'] == 'verified' else 'treated as unverified'}"
        if d.get("verificationStatus") != p["status"]:
            changes.append({"variable": f"defect[{d['id']}].verificationStatus", "from": d.get("verificationStatus"), "to": p["status"]})
            d["verificationStatus"] = p["status"]
    elif t == "close_segment":
        sid = p["segmentId"]
        if sid not in SEGMENT_BY_ID:
            raise ScenarioError(f"Unknown road segment '{sid}'")
        desc = f"segment {sid} ({SEGMENT_BY_ID[sid]['name']}) is closed"
        already = any(x["roadSegmentId"] == sid and x["restrictionType"] == "closure" and x.get("verificationStatus") == "verified" for x in s["restrictions"])
        if not already:
            s["restrictions"].append({"id": f"HYP-CLOSE-{sid}", "roadSegmentId": sid, "restrictionType": "closure", "limitValue": None, "unit": None,
                                      "appliesTo": "all", "description": "Hypothetical closure (Route Autopsy scenario, not real)", "source": "Route Autopsy hypothetical",
                                      "verificationStatus": "verified", "lastVerifiedAt": None})
            changes.append({"variable": f"segment[{sid}].closure", "from": "none", "to": "hypothetical verified closure"})
    elif t in ("set_vehicle_height", "set_vehicle_width", "set_vehicle_weight"):
        if s["vehicle"] is None:
            raise ScenarioError("Vehicle perturbations require a vehicleId")
        key, val, label = {"set_vehicle_height": ("heightM", p.get("heightM"), "height"), "set_vehicle_width": ("widthM", p.get("widthM"), "width"),
                           "set_vehicle_weight": ("currentLoadedWeightKg", p.get("weightKg"), "loaded weight")}[t]
        unit = "kg" if key.endswith("Kg") else "m"
        desc = f"vehicle {label} is {val:g} {unit}"
        old = s["vehicle"].get(key)
        if old != val:
            changes.append({"variable": f"vehicle.{key}", "from": old, "to": val})
            s["vehicle"][key] = val
            if s["vehicle"].get("specStatus") is not None:
                s["vehicle"]["specStatus"] = {**s["vehicle"]["specStatus"], key: "estimated"}
    else:  # pragma: no cover - guarded by pydantic discriminator
        raise ScenarioError(f"Unsupported perturbation '{t}'")
    return s, changes, desc


def _summary(result: dict, route_id: str | None) -> dict | None:
    if route_id is None:
        return None
    route = next((r for r in result["routes"] if r["id"] == route_id), None)
    if route is not None:
        return {"routeId": route["id"], "via": [SEGMENT_BY_ID[s]["name"] for s in route["segmentIds"]], "segmentIds": route["segmentIds"],
                "durationMin": round(route["durationSeconds"] / 60, 1), "suitabilityStatus": route["suitabilityStatus"]}
    ix = result["index"][route_id]  # pragma: no cover - recommended route is always among returned routes
    return {"routeId": route_id, "via": [SEGMENT_BY_ID[s]["name"] for s in ix["segmentIds"]], "segmentIds": ix["segmentIds"],
            "durationMin": round(ix["durationSeconds"] / 60, 1), "suitabilityStatus": ix["status"]}


def _ranked_usable(index: dict) -> list[tuple[str, dict]]:
    usable = [(k, v) for k, v in index.items() if v["status"] != "unsuitable"]
    return sorted(usable, key=lambda kv: (STATUS_RANK[kv[1]["status"]], kv[1]["scoreSeconds"], kv[1]["durationSeconds"], kv[0]))


def _runner_up(index: dict, rec_id: str | None) -> tuple[dict | None, int | None]:
    """Best usable candidate other than the recommended one, and the score lead of the recommendation over it."""
    if rec_id is None:
        return None, None
    others = [(k, v) for k, v in _ranked_usable(index) if k != rec_id]
    if not others:
        return None, None
    k, v = others[0]
    lead = v["scoreSeconds"] - index[rec_id]["scoreSeconds"]
    return {"routeId": k, "segmentIds": v["segmentIds"], "suitabilityStatus": v["status"], "scoreSeconds": v["scoreSeconds"]}, lead


def _route_by_id(result: dict, route_id: str | None):
    return next((r for r in result["routes"] if r["id"] == route_id), None) if route_id else None


def build_comparison(baseline: dict, revised: dict) -> dict | None:
    """Before/after metrics: baseline recommendation vs the scenario's recommendation.
    When the recommendation is stable, the same route is compared under the changed evidence."""
    b_id, r_id = baseline["recommendedId"], revised["recommendedId"]
    b_route, r_route = _route_by_id(baseline, b_id), _route_by_id(revised, r_id)
    if b_route is None and r_route is None:
        return None
    b_ix = baseline["index"].get(b_id) if b_id else None
    r_ix = revised["index"].get(r_id) if r_id else None
    b_ru, b_margin = _runner_up(baseline["index"], b_id)
    r_ru, r_margin = _runner_up(revised["index"], r_id)
    b_segs = set(b_route["segmentIds"]) if b_route else set()
    r_segs = set(r_route["segmentIds"]) if r_route else set()
    return {
        "routeIdBefore": b_id, "routeIdAfter": r_id,
        "durationMinBefore": round(b_route["durationSeconds"] / 60, 1) if b_route else None,
        "durationMinAfter": round(r_route["durationSeconds"] / 60, 1) if r_route else None,
        "distanceKmBefore": round(b_route["distanceMeters"] / 1000, 2) if b_route else None,
        "distanceKmAfter": round(r_route["distanceMeters"] / 1000, 2) if r_route else None,
        "suitabilityBefore": b_route["suitabilityStatus"] if b_route else None,
        "suitabilityAfter": r_route["suitabilityStatus"] if r_route else None,
        "severeHazardsBefore": b_route["severeHazardCount"] if b_route else None,
        "severeHazardsAfter": r_route["severeHazardCount"] if r_route else None,
        "scoreSecondsBefore": b_ix["scoreSeconds"] if b_ix else None,
        "scoreSecondsAfter": r_ix["scoreSeconds"] if r_ix else None,
        "segmentsRemoved": [x for x in (b_route["segmentIds"] if b_route else []) if x not in r_segs],
        "segmentsAdded": [x for x in (r_route["segmentIds"] if r_route else []) if x not in b_segs],
        "segmentsShared": [x for x in (b_route["segmentIds"] if b_route else []) if x in r_segs],
        "baselineRunnerUp": b_ru, "revisedRunnerUp": r_ru, "baselineMarginSeconds": b_margin, "revisedMarginSeconds": r_margin,
    }


def _run(origin, dest, state, opts) -> dict:
    return compute_routes(origin, dest, state["vehicle"], state["defects"], state["restrictions"], avoid_severe=opts["avoid_severe"],
                          prefer_surfaces=opts["prefer_surfaces"], max_alternatives=opts["max_alternatives"])


def _warnings_for_path(path_ids: list[str], state: dict) -> list[str]:
    from .routing import evaluate_path
    w, _m, _s, _h = evaluate_path(path_ids, state["vehicle"], state["defects"], state["restrictions"])
    return [x["message"] for x in w]


def default_suite(baseline: dict, state: dict) -> tuple[list[dict], dict]:
    """Deterministic default perturbations, derived only from evidence that touches the evaluated alternatives."""
    seg_ids = {s for r in baseline["routes"] for s in r["segmentIds"]}
    out: list[dict] = []
    vehicle = state["vehicle"]
    rec = next((r for r in baseline["routes"] if r["recommended"]), None)

    for d in sorted(state["defects"], key=lambda x: x["id"]):
        if d.get("roadSegmentId") in seg_ids and d.get("maintenanceStatus") != "resolved" and d.get("severity", 0) >= 4:
            out.append({"type": "resolve_defect", "defectId": d["id"]})
    for r in sorted(state["restrictions"], key=lambda x: x["id"]):
        if r.get("roadSegmentId") not in seg_ids or not applies(r, vehicle):
            continue
        out.append({"type": "remove_restriction", "restrictionId": r["id"]})
        if r.get("verificationStatus") == "verified":
            out.append({"type": "set_evidence_verification", "targetKind": "restriction", "targetId": r["id"], "status": "unverified"})
        else:
            out.append({"type": "verify_restriction", "restrictionId": r["id"]})
    if rec:
        for sid in rec["segmentIds"]:
            out.append({"type": "close_segment", "segmentId": sid})
    skipped_vehicle: list[str] = []
    if vehicle:
        for key, typ, field in (("heightM", "set_vehicle_height", "heightM"), ("widthM", "set_vehicle_width", "widthM"), ("currentLoadedWeightKg", "set_vehicle_weight", "weightKg")):
            base = vehicle.get(key)
            if key == "currentLoadedWeightKg" and base is None:
                base = vehicle.get("grossVehicleWeightKg")
            if base is None:
                skipped_vehicle.append(key)
                continue
            for sign in (-1, 1):
                out.append({"type": typ, field: round(base * (1 + sign * VEHICLE_DELTA), 3)})
    truncated = len(out) > MAX_SCENARIOS
    suite = {"description": ("Perturbations generated from evidence touching the evaluated alternatives: resolve severity>=4 defects (only these affect scoring); "
                             "remove / verify / un-verify applicable restrictions; close each segment of the recommended route; vehicle height, width and weight "
                             f"at +/-{int(VEHICLE_DELTA * 100)}% where known. Defect verification state is not a routing input and is therefore not in the default suite."),
             "generated": min(len(out), MAX_SCENARIOS), "truncated": truncated, "vehicleSpecsSkippedBecauseUnknown": skipped_vehicle}
    return out[:MAX_SCENARIOS], suite


def _path(rec):
    return " → ".join(rec["segmentIds"])


def _margin_sentence(cmp: dict | None) -> str:
    if not cmp or cmp.get("baselineMarginSeconds") is None or cmp.get("revisedMarginSeconds") is None:
        return ""
    b, r = cmp["baselineMarginSeconds"], cmp["revisedMarginSeconds"]
    if cmp["revisedRunnerUp"] is None:
        return ""
    if b == r:
        return f" Its score lead over the runner-up stays at {r} s."
    return f" Its score lead over the runner-up {'shrinks' if r < b else 'grows'} from {b} s to {r} s."


def _explain(desc, inputs_changed, changed, base_rec, rev_rec, base_under, base_idx, rev_idx, added, removed, note_extra, cmp=None):
    if not inputs_changed:
        return f"Hypothetically, {desc}. This does not change any input, so the recommendation is unchanged."
    head = f"Hypothetically, {desc}. "
    if not changed:
        tail = "The recommended route is unchanged"
        if base_under and base_under["statusAfter"] != base_under["statusBefore"]:
            tail += f", although its suitability would move from {base_under['statusBefore']} to {base_under['statusAfter']}"
        elif added or removed:
            tail += f", although {len(added) + len(removed)} of its warnings would change"
        return head + tail + "." + _margin_sentence(cmp) + note_extra
    if base_rec is None and rev_rec is not None:
        return head + f"Previously no route was usable; the recommendation becomes the route {_path(rev_rec)} ({rev_rec['suitabilityStatus']}).{note_extra}"
    if rev_rec is None:
        return head + f"The baseline recommendation would no longer be usable and no alternative in the evaluated set is usable, so there would be no recommendation.{note_extra}"
    reasons = []
    if base_under and STATUS_RANK[base_under["statusAfter"]] > STATUS_RANK[base_under["statusBefore"]]:
        reasons.append(f"the baseline route would change from {base_under['statusBefore']} to {base_under['statusAfter']}" + (f" (new constraint: {added[0]})" if added else ""))
    else:
        b, r = base_idx.get(rev_rec["routeId"]), rev_idx.get(rev_rec["routeId"])
        if b and r and r["scoreSeconds"] < b["scoreSeconds"]:
            reasons.append(f"the new recommended route's score would fall from {b['scoreSeconds']} s to {r['scoreSeconds']} s (rank {b['rank']} → {r['rank']})")
        elif b and r and STATUS_RANK[r["status"]] < STATUS_RANK[b["status"]]:
            reasons.append(f"the new recommended route would improve from {b['status']} to {r['status']}")
        else:
            reasons.append("the ranking of the evaluated alternatives would shift")
    delta = rev_rec["durationMin"] - base_rec["durationMin"]
    dtxt = f"{abs(delta):.1f} min {'longer' if delta > 0 else 'shorter'}" if abs(delta) >= 0.05 else "about the same duration"
    return head + (f"The recommendation would change from route {_path(base_rec)} to route {_path(rev_rec)} "
                   f"({dtxt}) because {'; '.join(reasons)}.") + note_extra


def run_scenarios(origin, dest, base_state: dict, baseline: dict, perturbations: list[dict], opts: dict) -> list[dict]:
    base_rec_id = baseline["recommendedId"]
    base_rec = _summary(baseline, base_rec_id)
    base_rec_path = next((r["segmentIds"] for r in baseline["routes"] if r["id"] == base_rec_id), None)
    base_rec_warn = _warnings_for_path(base_rec_path, base_state) if base_rec_path else []
    base_rec_status = next((r["suitabilityStatus"] for r in baseline["routes"] if r["id"] == base_rec_id), None)
    base_rec_dur = next((r["durationSeconds"] for r in baseline["routes"] if r["id"] == base_rec_id), None)
    results = []
    for i, raw in enumerate(perturbations, 1):
        p = dict(raw)
        weight = p.pop("weight", None) or WEIGHTS[p["type"]]
        p_clean = {k: v for k, v in raw.items() if k != "weight"}
        state2, changes, desc = apply_perturbation(base_state, p_clean)
        inputs_changed = bool(changes)
        notes: list[str] = []
        if p_clean["type"] == "set_evidence_verification" and p_clean["targetKind"] == "defect":
            notes.append("Defect verification status is displayed but is not an input to route scoring in the current engine, so this perturbation cannot change the recommendation.")
        if not inputs_changed:
            results.append({"scenarioId": f"sc-{i:02d}", "perturbation": p_clean, "description": desc, "weight": weight, "inputChanged": False, "changed": False, "skipped": True,
                            "baselineRecommendation": base_rec, "revisedRecommendation": base_rec, "deltaDurationMin": 0.0 if base_rec else None, "changedVariables": [],
                            "changedWarnings": {"added": [], "removed": []}, "baselineRouteUnderScenario": None,
                            "explanation": _explain(desc, False, False, base_rec, base_rec, None, {}, {}, [], [], ""), "notes": notes + ["Input already had the requested value; excluded from the sensitivity score."]})
            continue
        revised = _run(origin, dest, state2, opts)
        rev_rec = _summary(revised, revised["recommendedId"])
        changed = revised["recommendedId"] != base_rec_id
        base_under = None
        added: list[str] = []
        removed: list[str] = []
        if base_rec_path:
            under_state = _warnings_for_path(base_rec_path, state2)
            added = [m for m in dict.fromkeys(under_state) if m not in base_rec_warn]
            removed = [m for m in dict.fromkeys(base_rec_warn) if m not in under_state]
            ix2 = revised["index"].get(base_rec_id)
            if ix2:
                base_under = {"routeId": base_rec_id, "statusBefore": base_rec_status, "statusAfter": ix2["status"], "durationSecondsBefore": base_rec_dur, "durationSecondsAfter": ix2["durationSeconds"]}
        delta = round(rev_rec["durationMin"] - base_rec["durationMin"], 1) if (rev_rec and base_rec) else None
        cmp = build_comparison(baseline, revised)
        rev_route = _route_by_id(revised, revised["recommendedId"]) if changed else None
        results.append({"scenarioId": f"sc-{i:02d}", "perturbation": p_clean, "description": desc, "weight": weight, "inputChanged": True, "changed": changed, "skipped": False,
                        "baselineRecommendation": base_rec, "revisedRecommendation": rev_rec, "deltaDurationMin": delta, "changedVariables": changes,
                        "changedWarnings": {"added": added, "removed": removed}, "baselineRouteUnderScenario": base_under,
                        "comparison": cmp, "revisedRoute": alternative_out(rev_route) if rev_route else None,
                        "explanation": _explain(desc, True, changed, base_rec, rev_rec, base_under, baseline["index"], revised["index"], added, removed, "", cmp), "notes": notes})
    return results


def sensitivity(results: list[dict]) -> dict:
    tested = [r for r in results if not r["skipped"]]
    total = round(sum(r["weight"] for r in tested), 6)
    changed = [r for r in tested if r["changed"]]
    cw = round(sum(r["weight"] for r in changed), 6)
    return {"scenariosTested": len(tested), "scenariosChanged": len(changed), "scenariosSkipped": len(results) - len(tested),
            "sensitivityScore": round(cw / total, 4) if total > 0 else None, "totalWeight": total, "changedWeight": cw,
            "changedScenarioIds": [r["scenarioId"] for r in changed], "formula": FORMULA, "interpretation": INTERPRETATION}


def baseline_report(origin, dest, state, opts, result) -> dict:
    inv = build_investigation(origin, dest, state["vehicle"], state["defects"], state["restrictions"], result=result)
    rec = next((r for r in result["routes"] if r["recommended"]), None)
    focus = [rec] if rec else result["routes"]
    segs = {s for r in focus for s in r["segmentIds"]}
    unv_def = [d for d in state["defects"] if d.get("roadSegmentId") in segs and d.get("maintenanceStatus") != "resolved" and d.get("verificationStatus") != "verified"]
    unv_res = [r for r in state["restrictions"] if r.get("roadSegmentId") in segs and r.get("verificationStatus") != "verified" and applies(r, state["vehicle"])]
    restriction_warnings = [w for r in focus for w in r["warnings"] if w.get("restrictionId")]
    missing = unknown_specs(state["vehicle"]) if state["vehicle"] is not None else []
    return {"route": inv, "recommendedRouteId": result["recommendedId"], "suitabilityStatus": rec["suitabilityStatus"] if rec else None,
            "durationMin": round(rec["durationSeconds"] / 60, 1) if rec else None,
            "hazardPenaltySeconds": (rec["scoreBreakdown"]["severeDefectPenaltySeconds"] + rec["scoreBreakdown"]["surfacePenaltySeconds"]) if rec else None,
            "restrictionWarnings": restriction_warnings, "missingVehicleSpecs": missing,
            "unverifiedEvidence": {"defects": unv_def, "restrictions": unv_res}}


def _overall_text(baseline, sens, results):
    rec = baseline["route"]
    if sens["scenariosTested"] == 0:
        return "No perturbations were tested, so no sensitivity score is available."
    base = ("The baseline has no usable recommendation. " if baseline["recommendedRouteId"] is None else
            f"Baseline recommendation: route {' → '.join(s['id'] for s in rec['segments'])} ({baseline['suitabilityStatus']}, {baseline['durationMin']} min). ")
    return (base + f"{sens['scenariosChanged']} of {sens['scenariosTested']} tested hypothetical changes would change the recommendation "
            f"(weighted sensitivity {sens['sensitivityScore']:.2f}). " + INTERPRETATION)


def analyze(origin: str, dest: str, vehicle: dict | None, defects: list, restrictions: list, *, avoid_severe=True, prefer_surfaces=True,
            max_alternatives=5, perturbations: list[dict] | None = None, include_default_suite=True) -> dict:
    """Baseline + counterfactuals + sensitivity. `defects`/`restrictions`/`vehicle` are read-only inputs (copied before any change)."""
    opts = {"avoid_severe": avoid_severe, "prefer_surfaces": prefer_surfaces, "max_alternatives": max_alternatives}
    base_state = new_state(vehicle, defects, restrictions)
    result = _run(origin, dest, base_state, opts)
    if not result["routes"]:
        from .compat import RequestError
        raise RequestError(404, f"No candidate path from {origin} to {dest} within {result['search']['maxDepth']} segments.")
    suite_perts, suite_info = (default_suite(result, base_state) if include_default_suite else ([], {"description": "Default suite disabled by request.", "generated": 0, "truncated": False, "vehicleSpecsSkippedBecauseUnknown": []}))
    perts = [{**p} for p in suite_perts] + [{**p.model_dump(exclude_none=True)} if hasattr(p, "model_dump") else {**p} for p in (perturbations or [])]
    # validate user-supplied perturbations before running anything
    for p in perts:
        apply_perturbation(base_state, {k: v for k, v in p.items() if k != "weight"})
    results = run_scenarios(origin, dest, base_state, result, perts, opts)
    sens = sensitivity(results)
    baseline = baseline_report(origin, dest, base_state, opts, result)
    return {"analysisId": "ra-" + uuid.uuid4().hex[:12], "generatedAt": datetime.now(timezone.utc).isoformat(), "persisted": False,
            "baseline": baseline, "baselineRecommendation": _summary(result, result["recommendedId"]), "scenarios": results, "sensitivity": sens,
            "suite": suite_info, "explanation": _overall_text(baseline, sens, results), "disclaimer": DISCLAIMER}
