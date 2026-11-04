"""Adapters between the RouteWise engine/data model and the Route Autopsy frontend contracts.

Nothing here changes stored data or engine behaviour; it only re-shapes it.
"""
from __future__ import annotations

from typing import Any

from .pilot import SEGMENT_BY_ID, NODE_BY_ID
from .routing import CATEGORY_LABEL, compute_routes, resolve_node

DISCLAIMER = ("Illustrative Kochi pilot graph, restrictions and defects (demo data). Not surveyed, not live, and not suitable for "
              "real-world navigation. 'riskLevel' is an evidence-attention heuristic, not a probability of accident or failure.")

SPEC_KEYS = (("lengthM", "length"), ("widthM", "width"), ("heightM", "height"), ("grossVehicleWeightKg", "gross vehicle weight"))


def unknown_specs(v: dict) -> list[str]:
    out = []
    status = v.get("specStatus") or {}
    for key, label in SPEC_KEYS:
        if v.get(key) is None or status.get(key) == "unknown":
            out.append(label)
    return out


def vehicle_display_name(v: dict) -> str:
    parts = [v.get("make"), v.get("model"), str(v["year"]) if v.get("year") else None, v.get("variant") or None]
    return " ".join(p for p in parts if p)


def to_display_vehicle(v: dict) -> dict:
    """Explicit adapter: stored VehicleProfile -> frontend view. Keeps every original field."""
    unknown = unknown_specs(v)
    notes = []
    if v.get("isIllustrative"):
        notes.append("Illustrative catalogue entry — not an official specification.")
    if unknown:
        notes.append("Unknown: " + ", ".join(unknown) + ".")
    return {**v, "name": vehicle_display_name(v), "type": CATEGORY_LABEL.get(v.get("category", "other"), "vehicle").capitalize(),
            "unknownSpecs": unknown, "notes": " ".join(notes) or None}


def segment_risk(route: dict, sid: str) -> tuple[str, str | None]:
    """Transparent per-segment attention level derived from engine output:
    high   = a verified blocking restriction on the segment, or an unresolved severity>=4 defect
    medium = any non-critical warning, unresolved severity 2-3 defect, poor/unknown surface or incomplete restriction/width data
    low    = none of the above
    """
    seg = SEGMENT_BY_ID[sid]
    notes: list[str] = []
    level = "low"

    def raise_to(l):
        nonlocal level
        if ["low", "medium", "high"].index(l) > ["low", "medium", "high"].index(level):
            level = l

    for w in route["warnings"]:
        if w.get("segmentId") != sid:
            continue
        if w["level"] == "critical":
            raise_to("high")
        elif w["level"] == "warning":
            raise_to("medium")
        notes.append(w["message"])
    for d in route["knownHazards"]:
        if d.get("roadSegmentId") != sid:
            continue
        sev = d.get("severity", 0)
        if sev >= 4:
            raise_to("high")
        elif sev >= 2:
            raise_to("medium")
            notes.append(f"Severity {sev} {d['defectType'].replace('_', ' ')} reported ({d.get('verificationStatus')}).")
    if seg["surface"] in ("poor", "unknown"):
        raise_to("medium")
        notes.append(f"{seg['surface'].capitalize()} surface condition (demo value).")
    if not seg["restrictionDataComplete"]:
        raise_to("medium")
        notes.append("Restriction data incomplete for this segment.")
    if seg["widthM"] is None:
        raise_to("medium")
        notes.append("Road width unknown.")
    # de-duplicate, keep order, cap length
    notes = list(dict.fromkeys(notes))
    return level, (" ".join(notes)[:600] if notes else None)


def _segments_out(route: dict) -> list[dict]:
    from .routing import _seg_len
    out = []
    for sid in route["segmentIds"]:
        level, note = segment_risk(route, sid)
        out.append({"id": sid, "name": SEGMENT_BY_ID[sid]["name"], "distanceKm": round(_seg_len(sid) / 1000, 2), "riskLevel": level, "note": note})
    return out


def alternative_out(route: dict) -> dict:
    return {
        "routeId": route["id"], "label": route["label"], "segmentIds": route["segmentIds"], "segments": _segments_out(route),
        "distanceKm": round(route["distanceMeters"] / 1000, 2), "durationMin": round(route["durationSeconds"] / 60, 1),
        "suitabilityStatus": route["suitabilityStatus"], "recommended": route["recommended"], "isFastestCandidate": route["isFastestCandidate"],
        "rank": route["rank"], "scoreSeconds": route["scoreSeconds"], "scoreBreakdown": route["scoreBreakdown"],
        "severeHazardCount": route["severeHazardCount"], "warnings": route["warnings"], "missingData": route["missingData"],
        "rejectionReasons": route["rejectionReasons"], "explanation": route["explanation"], "geometry": route["geometry"],
    }


class RequestError(Exception):
    def __init__(self, status: int, detail: str):
        self.status, self.detail = status, detail
        super().__init__(detail)


def resolve_request(origin: str, destination: str, vehicle_id: str | None, get_vehicle) -> tuple[str, str, dict | None]:
    o, d = resolve_node(origin), resolve_node(destination)
    valid = ", ".join(f"{n} ({NODE_BY_ID[n]['name']})" for n in NODE_BY_ID)
    if o is None:
        raise RequestError(422, f"Unknown origin '{origin}'. Use one of: {valid}")
    if d is None:
        raise RequestError(422, f"Unknown destination '{destination}'. Use one of: {valid}")
    if o == d:
        raise RequestError(422, "Origin and destination must be different.")
    vehicle = None
    if vehicle_id:
        vehicle = get_vehicle(vehicle_id)
        if vehicle is None:
            raise RequestError(404, f"Vehicle profile '{vehicle_id}' not found")
    return o, d, vehicle


def build_investigation(origin_id: str, dest_id: str, vehicle: dict | None, defects: list, restrictions: list, *,
                        avoid_severe=True, prefer_surfaces=True, max_alternatives=5, result: dict | None = None) -> dict:
    """Map the engine's list of alternatives onto the single-route frontend response (alternatives preserved)."""
    result = result or compute_routes(origin_id, dest_id, vehicle, defects, restrictions, avoid_severe=avoid_severe,
                                      prefer_surfaces=prefer_surfaces, max_alternatives=max_alternatives)
    routes = result["routes"]
    if not routes:
        raise RequestError(404, f"No candidate path from {origin_id} to {dest_id} within {result['search']['maxDepth']} segments.")
    rec = next((r for r in routes if r["recommended"]), None)
    primary = rec or min(routes, key=lambda r: r["rank"])
    alts = [alternative_out(r) for r in routes]
    segs = next(a for a in alts if a["routeId"] == primary["id"])["segments"]
    return {
        "routeId": primary["id"], "origin": NODE_BY_ID[origin_id]["name"], "destination": NODE_BY_ID[dest_id]["name"],
        "originId": origin_id, "destinationId": dest_id,
        "distanceKm": round(primary["distanceMeters"] / 1000, 2), "durationMin": round(primary["durationSeconds"] / 60, 1),
        "segments": segs, "vehicle": to_display_vehicle(vehicle) if vehicle else None,
        "suitabilityStatus": primary["suitabilityStatus"], "recommended": rec is not None,
        "recommendationStatus": "recommended" if rec else "no_usable_route",
        "explanation": primary["explanation"], "warnings": primary["warnings"], "missingData": primary["missingData"],
        "alternatives": alts, "search": result["search"], "disclaimer": DISCLAIMER,
    }
