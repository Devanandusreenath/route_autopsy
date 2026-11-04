"""Vehicle-aware routing engine for the illustrative RouteWise pilot graph.

Pure functions: every function takes its evidence (defects, restrictions, vehicle)
as arguments and never touches SQLite. That is what allows Route Autopsy to
re-run the *same* engine on in-memory copies for hypothetical scenarios.

The Kochi graph is illustrative demo data. Nothing here is accurate real-world routing.
"""
from __future__ import annotations

from typing import Any

from .pilot import NODES, NODE_BY_ID, SEGMENTS, SEGMENT_BY_ID, segment_length

SURFACE_SPEED = {"good": 34, "fair": 27, "poor": 19, "unknown": 24}
SURFACE_KEYS = ("good", "fair", "poor", "unknown")
STATUS_ORDER = ["suitable", "warning", "not_validated", "unsuitable"]
STATUS_RANK = {"suitable": 0, "warning": 1, "not_validated": 1, "unsuitable": 3}
CATEGORY_LABEL = {"small_car": "small car", "sedan": "sedan", "suv": "SUV", "van": "van", "lcv": "light commercial vehicle", "heavy_truck": "heavy truck", "bus": "bus", "motorcycle": "motorcycle", "other": "vehicle"}
RESTRICTION_LABEL = {"height": "Height limit", "width": "Width limit", "length": "Length limit", "weight": "Weight limit", "access": "Access restriction", "closure": "Road closure"}

# Scoring weights (unchanged from the original engine).
SEVERE_DEFECT_PENALTY_S = 600
POOR_SURFACE_PENALTY_S_PER_KM = 240
UNKNOWN_SURFACE_PENALTY_S_PER_KM = 90

# Search limits. The pilot graph is tiny; the bounds exist so a larger graph cannot hang the API.
DEFAULT_MAX_DEPTH = 6              # max segments per candidate path
DEFAULT_MAX_CANDIDATES = 5000      # max complete candidate paths collected
DEFAULT_MAX_EXPANSIONS = 250_000   # max DFS node visits
DEFAULT_MAX_ALTERNATIVES = 5       # usable alternatives returned
DEFAULT_MAX_REJECTED = 3           # unsuitable alternatives returned for explanation

_ADJ: dict[str, list[tuple[str, str]]] = {}
for _s in SEGMENTS:
    _ADJ.setdefault(_s["from"], []).append((_s["to"], _s["id"]))
    _ADJ.setdefault(_s["to"], []).append((_s["from"], _s["id"]))


def resolve_node(token: str | None) -> str | None:
    """Accept a node id ('FKC') or an exact node name ('Fort Kochi'), case-insensitively."""
    if not token:
        return None
    t = token.strip()
    if t in NODE_BY_ID:
        return t
    low = t.lower()
    for n in NODES:
        if n["id"].lower() == low or n["name"].lower() == low:
            return n["id"]
    return None


def enumerate_paths_bounded(origin, dest, max_depth=DEFAULT_MAX_DEPTH, max_paths=DEFAULT_MAX_CANDIDATES, max_expansions=DEFAULT_MAX_EXPANSIONS):
    """Depth-first enumeration of simple (no repeated node) paths.

    Returns (paths, truncated). Bounded three ways: path length, number of paths,
    and total DFS expansions, so traversal always terminates quickly.
    """
    out: list[list[str]] = []
    state = {"expansions": 0, "truncated": False}

    def walk(node, visited, segs):
        if state["truncated"]:
            return
        state["expansions"] += 1
        if state["expansions"] > max_expansions:
            state["truncated"] = True
            return
        if node == dest:
            if len(out) >= max_paths:
                state["truncated"] = True
                return
            out.append(list(segs))
            return
        if len(segs) >= max_depth:
            return
        for nxt, sid in _ADJ.get(node, ()):
            if nxt in visited:
                continue
            visited.add(nxt)
            segs.append(sid)
            walk(nxt, visited, segs)
            segs.pop()
            visited.remove(nxt)

    walk(origin, {origin}, [])
    return out, state["truncated"]


def enumerate_paths(origin, dest, max_depth=DEFAULT_MAX_DEPTH):
    """Original signature preserved: all simple paths up to max_depth segments."""
    return enumerate_paths_bounded(origin, dest, max_depth)[0]


def oriented_geometry(seg_ids, origin):
    pts = []
    at = origin
    for sid in seg_ids:
        s = SEGMENT_BY_ID[sid]
        g = s["geometry"] if s["from"] == at else list(reversed(s["geometry"]))
        at = s["to"] if s["from"] == at else s["from"]
        pts.extend(g if not pts else g[1:])
    return pts


def applies(restriction, vehicle):
    ap = restriction.get("appliesTo", "all")
    return ap == "all" or (vehicle is not None and vehicle.get("category") in ap)


def vehicle_value(r, v):
    typ = r["restrictionType"]
    if typ == "height":
        return v.get("heightM")
    if typ == "width":
        return v.get("widthM")
    if typ == "length":
        return v.get("lengthM")
    if typ == "weight":
        kg = v.get("currentLoadedWeightKg")
        if kg is None:
            kg = v.get("grossVehicleWeightKg")
        return kg / 1000 if kg is not None else None
    return None


def check_restriction(r, vehicle):
    """Classify ONE restriction against a vehicle, mirroring the per-restriction logic in evaluate_path.

    Returns (outcome, vehicleValue, message). outcome is one of:
      not_applicable | blocks (verified, vehicle cannot pass) | may_block (unverified, would block if confirmed)
      | unknown_spec (vehicle value missing, clearance cannot be confirmed) | fits
    A consistency test pins this to evaluate_path so the two cannot drift apart.
    """
    label = RESTRICTION_LABEL.get(r["restrictionType"], r["restrictionType"])
    if not applies(r, vehicle):
        return "not_applicable", None, f"{label} does not apply to this vehicle category."
    verified = r.get("verificationStatus") == "verified"
    typ = r["restrictionType"]
    if typ in ("closure", "access"):
        return ("blocks" if verified else "may_block"), None, f"{label}: {r.get('description', '')}" + ("" if verified else " (unverified)")
    val = vehicle_value(r, vehicle)
    unit = r.get("unit")
    if val is None:
        return "unknown_spec", None, f"Vehicle {typ} is unknown, so clearance for the {r.get('limitValue')} {unit} limit cannot be confirmed."
    limit = r.get("limitValue")
    if limit is not None and val > limit:
        if verified:
            return "blocks", val, f"Vehicle {val:.2f} {unit} exceeds the verified {limit} {unit} limit."
        return "may_block", val, f"Vehicle {val:.2f} {unit} exceeds the {limit} {unit} limit, but the limit is unverified."
    return "fits", val, f"Vehicle {val:.2f} {unit} is within the {limit} {unit} limit."


def evaluate_path(seg_ids, vehicle, defects, restrictions):
    """Unchanged evaluation semantics: returns (warnings, missing, status, hazards)."""
    warnings = []
    missing = []
    status = "suitable"

    def bump(value):
        nonlocal status
        if STATUS_ORDER.index(value) > STATUS_ORDER.index(status):
            status = value

    if vehicle is None:
        bump("not_validated")
        warnings.append({"level": "warning", "message": "No vehicle selected — restrictions cannot be checked against this route."})
    else:
        critical = [("widthM", "width"), ("heightM", "height"), ("grossVehicleWeightKg", "gross vehicle weight")]
        absent = [label for key, label in critical if vehicle.get(key) is None]
        if absent:
            missing.append("Vehicle " + ", ".join(absent) + " not provided")
    for sid in seg_ids:
        seg = SEGMENT_BY_ID[sid]
        if not seg["restrictionDataComplete"]:
            missing.append(f"Restriction data incomplete on {seg['name']}")
            bump("warning")
        if seg["widthM"] is None:
            missing.append(f"Road width unknown on {seg['name']}")
            bump("warning")
        elif vehicle and vehicle.get("widthM") is not None and seg["widthM"] < 6 and vehicle["widthM"] > 2.0:
            warnings.append({"level": "warning", "segmentId": sid, "message": f"{seg['name']} is narrow ({seg['widthM']} m demo value) for a {vehicle['widthM']} m wide vehicle — passing may be difficult."})
            bump("warning")
        for r in [x for x in restrictions if x.get("roadSegmentId") == sid and applies(x, vehicle)]:
            label = RESTRICTION_LABEL.get(r["restrictionType"], r["restrictionType"])
            verified = r.get("verificationStatus") == "verified"
            if r["restrictionType"] == "closure":
                warnings.append({"level": "critical" if verified else "warning", "segmentId": sid, "restrictionId": r.get("id"), "message": f"{label} on {seg['name']}: {r.get('description', '')}"})
                bump("unsuitable" if verified else "warning")
                continue
            if r["restrictionType"] == "access":
                who = CATEGORY_LABEL.get(vehicle.get("category", "other"), "vehicle") if vehicle else "some vehicles"
                warnings.append({"level": "critical" if verified else "warning", "segmentId": sid, "restrictionId": r.get("id"), "message": f"{label} on {seg['name']} for {who}: {r.get('description', '')}"})
                bump("unsuitable" if verified else "warning")
                continue
            if not vehicle:
                continue
            val = vehicle_value(r, vehicle)
            if val is None:
                warnings.append({"level": "warning", "segmentId": sid, "restrictionId": r.get("id"), "message": f"{label} of {r.get('limitValue')} {r.get('unit')} on {seg['name']}, but your vehicle's {r['restrictionType']} is unknown — cannot confirm clearance."})
                bump("warning")
                continue
            limit = r.get("limitValue")
            if limit is not None and val > limit:
                if verified:
                    warnings.append({"level": "critical", "segmentId": sid, "restrictionId": r.get("id"), "message": f"{label} {limit} {r.get('unit')} on {seg['name']}; your vehicle is {val:.2f} {r.get('unit')}. Vehicle is not permitted / cannot pass."})
                    bump("unsuitable")
                else:
                    warnings.append({"level": "warning", "segmentId": sid, "restrictionId": r.get("id"), "message": f"Unverified {label.lower()} of {limit} {r.get('unit')} on {seg['name']}; your vehicle is {val:.2f} {r.get('unit')}. Confirm before travelling."})
                    bump("warning")
    hazards = [d for d in defects if d.get("roadSegmentId") in seg_ids and d.get("maintenanceStatus") != "resolved"]
    for h in hazards:
        if h.get("severity", 0) >= 4:
            warnings.append({"level": "info", "segmentId": h.get("roadSegmentId"), "defectId": h.get("id"), "message": f"Severity {h['severity']} {h['defectType'].replace('_', ' ')} reported on {SEGMENT_BY_ID.get(h.get('roadSegmentId'), {}).get('name', 'road')} ({h.get('verificationStatus')})."})
    return warnings, list(dict.fromkeys(missing)), status, hazards


def format_duration(seconds):
    minutes = max(1, round(seconds / 60))
    return f"{minutes // 60} hr {minutes % 60} min" if minutes >= 60 else f"{minutes} min"


def route_explanation(route, all_routes):
    """Explain why a route is recommended, an alternative, or rejected.

    `all_routes` must be ordered fastest-first (as returned by compute_routes).
    """
    fastest = all_routes[0] if all_routes else route
    recommended = next((r for r in all_routes if r["recommended"]), None)
    criticals = [w["message"] for w in route["warnings"] if w["level"] == "critical"]
    via = ", ".join(SEGMENT_BY_ID[sid]["name"] for sid in route["segmentIds"][:2])
    if route["suitabilityStatus"] == "unsuitable":
        text = f"{route['label']} is not usable for this vehicle: {criticals[0] if criticals else 'a known restriction applies'}"
        if len(criticals) > 1:
            text += f" (+{len(criticals) - 1} more blocking constraint{'s' if len(criticals) > 2 else ''})"
        if route["id"] == fastest["id"] and recommended:
            text += f". It is the fastest candidate but was rejected; {recommended['label']} is recommended instead."
        return text
    if recommended is None:
        return f"{route['label']} (via {via}) is not recommended: no route in the evaluated set is usable for this vehicle."
    if route["recommended"]:
        if fastest["id"] == route["id"]:
            return f"{route['label']} (via {via}) is recommended and is the fastest option, with {len(route['knownHazards'])} known hazards ({route['severeHazardCount']} severe). Estimated {format_duration(route['durationSeconds'])}."
        dt = route["durationSeconds"] - fastest["durationSeconds"]
        why = []
        if fastest["suitabilityStatus"] == "unsuitable":
            why.append(f"the faster {fastest['label']} is blocked by a known restriction")
        else:
            if STATUS_RANK[fastest["suitabilityStatus"]] > STATUS_RANK[route["suitabilityStatus"]]:
                why.append(f"{fastest['label']} has unresolved warnings ({fastest['suitabilityStatus']}) that this route avoids")
            d_sev = fastest["severeHazardCount"] - route["severeHazardCount"]
            if d_sev > 0:
                why.append(f"it passes {d_sev} fewer reported severe defect{'s' if d_sev != 1 else ''}")
        why_txt = "; ".join(why) if why else "its combined time, surface and defect score is lower"
        extra = f"about {max(1, round(dt / 60))} min slower than {fastest['label']}" if dt > 30 else "about as fast as the fastest option"
        return f"{route['label']} (via {via}) is recommended because {why_txt}. It is {extra}. Estimated {format_duration(route['durationSeconds'])}."
    compare = recommended
    dt = route["durationSeconds"] - compare["durationSeconds"]
    d_severe = compare["severeHazardCount"] - route["severeHazardCount"]
    if d_severe > 0:
        parts = f"{route['label']} avoids {d_severe} reported severe road defect{'s' if d_severe != 1 else ''} compared with {compare['label']}"
    elif d_severe < 0:
        parts = f"{route['label']} passes {-d_severe} more reported severe defects than {compare['label']}"
    else:
        parts = f"{route['label']} has the same number of severe defects as {compare['label']}"
    if dt > 30:
        parts += f" but adds approximately {max(1, round(dt / 60))} minutes"
    elif dt < -30:
        parts += f" but saves approximately {max(1, round(-dt / 60))} minutes"
    else:
        parts += " and takes about the same time"
    if STATUS_RANK[route["suitabilityStatus"]] > STATUS_RANK[compare["suitabilityStatus"]]:
        parts += f"; it carries more unresolved warnings ({route['suitabilityStatus']})"
    return parts + f". Estimated {format_duration(route['durationSeconds'])}."


_LEN_CACHE: dict[str, float] = {}


def _seg_len(sid):
    if sid not in _LEN_CACHE:
        _LEN_CACHE[sid] = segment_length(sid)
    return _LEN_CACHE[sid]


def measure_path(path):
    dist = duration = 0.0
    surface = {k: 0.0 for k in SURFACE_KEYS}
    for sid in path:
        length = _seg_len(sid)
        surf = SEGMENT_BY_ID[sid]["surface"]
        dist += length
        duration += length / (SURFACE_SPEED[surf] * 1000 / 3600)
        surface[surf] += length
    return {"segIds": path, "distance": dist, "duration": duration, "surfaceMeters": surface}


def compute_routes(origin_id, dest_id, vehicle, defects, restrictions, *, avoid_severe=True, prefer_surfaces=True,
                   max_alternatives=DEFAULT_MAX_ALTERNATIVES, max_rejected=DEFAULT_MAX_REJECTED,
                   max_depth=DEFAULT_MAX_DEPTH, max_candidates=DEFAULT_MAX_CANDIDATES):
    """Enumerate, evaluate and rank candidate routes. Pure: reads only its arguments.

    Every enumerated candidate is evaluated against hard vehicle restrictions
    BEFORE ranking, so a slower suitable route is never discarded because faster
    candidates turned out to be unsuitable. Returns a dict:
      routes        - selected alternatives, fastest first, in the legacy item shape (+ additive fields)
      recommendedId - id of the recommended route, or None if nothing is usable
      search        - candidate counts, status counts and truncation flag
    """
    paths, truncated = enumerate_paths_bounded(origin_id, dest_id, max_depth, max_candidates)
    evaluated = []
    for path in paths:
        cand = measure_path(path)
        warnings, missing, status, hazards = evaluate_path(path, vehicle, defects, restrictions)
        severe = sum(1 for h in hazards if h.get("severity", 0) >= 4)
        sev_pen = severe * SEVERE_DEFECT_PENALTY_S if avoid_severe else 0
        surf_pen = ((cand["surfaceMeters"]["poor"] / 1000) * POOR_SURFACE_PENALTY_S_PER_KM + (cand["surfaceMeters"]["unknown"] / 1000) * UNKNOWN_SURFACE_PENALTY_S_PER_KM) if prefer_surfaces else 0
        score = cand["duration"] + sev_pen + surf_pen
        evaluated.append({**cand, "warnings": warnings, "missing": missing, "status": status, "hazards": hazards, "severe": severe,
                          "score": score, "statusRank": STATUS_RANK[status], "sevPenalty": sev_pen, "surfPenalty": surf_pen,
                          "id": f"{origin_id}-{dest_id}-{'_'.join(path)}"})
    ranked = sorted(evaluated, key=lambda e: (e["statusRank"], e["score"], e["duration"], e["id"]))
    for i, e in enumerate(ranked):
        e["rank"] = i + 1
    usable = [e for e in ranked if e["status"] != "unsuitable"]
    rejected = [e for e in ranked if e["status"] == "unsuitable"]
    recommended = usable[0] if usable else None
    fastest = min(evaluated, key=lambda e: (e["duration"], e["id"])) if evaluated else None

    selected = usable[:max_alternatives]
    chosen_rejected = sorted(rejected, key=lambda e: (e["duration"], e["id"]))[:max_rejected]
    selected += chosen_rejected
    if fastest is not None and all(fastest["id"] != s["id"] for s in selected):
        selected.append(fastest)  # always show the fastest candidate so it can be explained
    selected.sort(key=lambda e: (e["duration"], e["id"]))

    routes = []
    for i, e in enumerate(selected):
        label = f"Route {chr(65 + i)}"
        routes.append({
            "id": e["id"], "label": label, "segmentIds": e["segIds"], "distanceMeters": round(e["distance"]), "durationSeconds": round(e["duration"]),
            "geometry": oriented_geometry(e["segIds"], origin_id), "knownHazards": e["hazards"], "severeHazardCount": e["severe"], "warnings": e["warnings"],
            "missingData": e["missing"], "surfaceMeters": {k: round(v) for k, v in e["surfaceMeters"].items()}, "suitabilityStatus": e["status"],
            "recommended": recommended is not None and e["id"] == recommended["id"], "explanation": "",
            # additive fields (absent in the original API)
            "rank": e["rank"], "isFastestCandidate": fastest is not None and e["id"] == fastest["id"], "scoreSeconds": round(e["score"]),
            "scoreBreakdown": {"travelSeconds": round(e["duration"]), "severeDefectPenaltySeconds": round(e["sevPenalty"]), "surfacePenaltySeconds": round(e["surfPenalty"])},
            "rejectionReasons": [w["message"] for w in e["warnings"] if w["level"] == "critical"] if e["status"] == "unsuitable" else [],
        })
    for r in routes:
        r["explanation"] = route_explanation(r, routes)
    counts = {s: sum(1 for e in evaluated if e["status"] == s) for s in STATUS_ORDER}
    return {
        "routes": routes,
        "recommendedId": recommended["id"] if recommended else None,
        "index": {e["id"]: {"rank": e["rank"], "status": e["status"], "scoreSeconds": round(e["score"]), "durationSeconds": round(e["duration"]),
                            "segmentIds": e["segIds"]} for e in evaluated},
        "search": {"candidatesEnumerated": len(paths), "candidatesEvaluated": len(evaluated), "truncated": truncated, "maxDepth": max_depth,
                   "maxCandidates": max_candidates, "statusCounts": counts, "alternativesReturned": len(routes)},
    }
