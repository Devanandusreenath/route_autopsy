"""Generate docs/API_CONTRACT.md from the backend's real OpenAPI schema.

    python scripts/generate_api_contract.py            # rewrite docs/API_CONTRACT.md
    python scripts/generate_api_contract.py --check    # exit 1 if the committed file is stale (also run by the test-suite)

The endpoint table, request/response models and status codes come from FastAPI/Pydantic, so they cannot drift from the code.
Only the "consumed by" column and the behaviour rules below are hand-maintained.
"""
import os
import sys
import tempfile

os.environ.setdefault("DATABASE_PATH", os.path.join(tempfile.mkdtemp(), "contract.db"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "API_CONTRACT.md")

# Frontend consumers (hand-maintained; verified by tests/test_api_contract_doc.py against frontend endpoints.ts when present).
CONSUMED = {
    ("GET", "/api/meta"): ("network.api.ts › getNetwork", "types/network.ts"),
    ("GET", "/vehicles"): ("vehicles.api.ts › listVehicles", "types/vehicles.ts"),
    ("GET", "/vehicles/{vehicle_id}/restriction-check"): ("vehicles.api.ts › getVehicleRestrictionCheck", "types/vehicles.ts"),
    ("GET", "/restrictions"): ("restrictions.api.ts › listRestrictions", "types/restrictions.ts"),
    ("GET", "/defects"): ("defects.api.ts › listDefects", "types/defects.ts"),
    ("GET", "/defects/{defect_id}"): ("defects.api.ts › getDefect", "types/defects.ts"),
    ("POST", "/routes/investigate"): ("routes.api.ts › investigateRoute", "types/routes.ts"),
    ("POST", "/autopsy/analyze"): ("autopsy.api.ts › analyzeAutopsy", "types/autopsy.ts"),
    ("POST", "/autopsy/scenario"): ("autopsy.api.ts › runScenario", "types/autopsy.ts"),
    ("GET", "/evidence/status"): ("evidence.api.ts › getEvidenceStatus", "types/evidence.ts"),
    ("POST", "/evidence/analyze"): ("evidence.api.ts › analyzeEvidence", "types/evidence.ts"),
    ("POST", "/evidence/confirm"): ("evidence.api.ts › confirmEvidence", "types/evidence.ts"),
}

UNTYPED_SHAPES = {
    ("GET", "/api/meta"): "`{demoMode, pilotArea, warning, nodes:[{id,name,position:[lat,lon]}], segments:[{id,name,area,from,to,widthM,surface,restrictionDataComplete,geometry:[[lat,lon],…]}]}` (illustrative Kochi graph)",
    ("GET", "/restrictions"): "list of restrictions `{id, roadSegmentId, restrictionType, limitValue, unit, appliesTo: \"all\" | [category], description, source, verificationStatus, lastVerifiedAt}`",
    ("GET", "/defects"): "list of defect records `{id, defectType, latitude, longitude, severity 1-5, description, observedAt, roadSegmentId, reportedAt, verificationStatus, maintenanceStatus, independentReportCount, isUserSubmitted, …provenance fields for evidence-created defects}`",
    ("GET", "/defects/{defect_id}"): "one defect record (same shape as a `/defects` item)",
}


def resolve(schema, spec):
    return spec["components"]["schemas"][schema["$ref"].split("/")[-1]] if "$ref" in schema else schema


def type_str(s):
    if "$ref" in s:
        return f"`{s['$ref'].split('/')[-1]}`"
    if "anyOf" in s or "oneOf" in s:
        parts = [type_str(x) for x in s.get("anyOf", s.get("oneOf"))]
        return " \\| ".join(parts)
    if "const" in s:
        return f"`{s['const']!r}`".replace("'", '"')
    if "enum" in s:
        return "enum(" + ", ".join(f'`{e}`' for e in s["enum"]) + ")"
    t = s.get("type")
    if t == "array":
        return f"array of {type_str(s.get('items', {}))}"
    if t == "object":
        ap = s.get("additionalProperties")
        return f"map of {type_str(ap)}" if isinstance(ap, dict) and ap else "object"
    if t == "null":
        return "null"
    extra = []
    for k, label in (("minimum", "≥"), ("exclusiveMinimum", ">"), ("maximum", "≤"), ("minLength", "minLen"), ("maxLength", "maxLen")):
        if k in s:
            extra.append(f"{label} {s[k]}")
    return f"{t or 'any'}" + (f" ({', '.join(extra)})" if extra else "")


def refs_in(s, acc):
    if isinstance(s, dict):
        for k, v in s.items():
            if k == "$ref":
                acc.add(v.split("/")[-1])
            else:
                refs_in(v, acc)
    elif isinstance(s, list):
        for v in s:
            refs_in(v, acc)


def collect(names, spec):
    seen, todo = set(), list(names)
    while todo:
        n = todo.pop()
        if n in seen or n not in spec["components"]["schemas"]:
            continue
        seen.add(n)
        more = set()
        refs_in(spec["components"]["schemas"][n], more)
        todo.extend(more)
    return sorted(seen)


def model_table(name, spec):
    sc = spec["components"]["schemas"][name]
    lines = [f"#### `{name}`", ""]
    if sc.get("description"):
        lines += [sc["description"].strip().split("\n")[0], ""]
    if "oneOf" in sc or "anyOf" in sc:
        lines += ["One of: " + type_str(sc), ""]
        return lines
    req = set(sc.get("required", []))
    props = sc.get("properties", {})
    if not props:
        return lines + ["_(free-form object)_", ""]
    lines += ["| Field | Type | Required | Notes |", "|---|---|---|---|"]
    for k, v in props.items():
        title = v.get("description", "").replace("|", "\\|").replace("\n", " ")
        default = f" default `{v['default']}`" if "default" in v and v["default"] not in (None, [], {}) else ""
        lines.append(f"| `{k}` | {type_str(v)} | {'yes' if k in req else 'no'} | {title}{default} |")
    return lines + [""]


def body_ref(op, kind, spec):
    if kind == "req":
        c = op.get("requestBody", {}).get("content", {})
        for mt, v in c.items():
            sch = v.get("schema", {})
            return mt, sch
        return None, None
    r = op.get("responses", {}).get("200") or op.get("responses", {}).get("201") or {}
    for mt, v in r.get("content", {}).items():
        return mt, v.get("schema", {})
    return None, None


def render():
    spec = app.openapi()
    ops = []
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if method in ("get", "post", "put", "patch", "delete"):
                ops.append((method.upper(), path, op))
    order = list(CONSUMED)
    ops.sort(key=lambda o: (order.index((o[0], o[1])) if (o[0], o[1]) in CONSUMED else 999, o[1], o[0]))
    consumed = [o for o in ops if (o[0], o[1]) in CONSUMED]
    other = [o for o in ops if (o[0], o[1]) not in CONSUMED]
    L = ["# Route Autopsy — API Contract", "",
         "> **Generated** from the FastAPI/Pydantic OpenAPI schema by `scripts/generate_api_contract.py` — do not edit by hand. "
         "`tests/test_api_contract_doc.py` fails if this file is stale or if the frontend calls an endpoint that does not exist.", "",
         "Base URL (local): `http://127.0.0.1:8000`. All bodies are JSON except `POST /evidence/analyze` (multipart). "
         "Errors use FastAPI's `{\"detail\": string | [{loc, msg, type}]}`.", "",
         "**Data warning:** the road graph, restrictions and seeded defects are illustrative demo data; sensitivity and `riskLevel` are evidence-attention measures, not accident or failure probabilities.", "",
         "## 1. Endpoints used by the frontend", "",
         "| Method | Path | Request | Response | Errors | Frontend consumer |", "|---|---|---|---|---|---|"]
    models = set()
    for m, p, op in consumed:
        rq_mt, rq = body_ref(op, "req", spec)
        rs_mt, rs = body_ref(op, "res", spec)
        refs = set()
        refs_in(rq or {}, refs)
        refs_in(rs or {}, refs)
        models |= refs
        rq_s = "—" if rq is None else (type_str(rq) if "multipart" not in (rq_mt or "") else "multipart: " + ", ".join(f"`{k}`" for k in spec["components"]["schemas"][rq["$ref"].split("/")[-1]]["properties"]))
        rs_s = UNTYPED_SHAPES.get((m, p)) if rs is None or rs == {} else type_str(rs)
        errs = sorted(c for c in op["responses"] if c not in ("200", "201"))
        L.append(f"| {m} | `{p}` | {rq_s} | {rs_s} | {', '.join(errs) or '—'} | `{CONSUMED[(m, p)][0]}` → `{CONSUMED[(m, p)][1]}` |")
    L += ["", "Documented HTTP errors beyond 422 (not in OpenAPI because they are raised in code):", "",
          "| Endpoint | Status | Meaning |", "|---|---|---|",
          "| `POST /routes/investigate`, `/autopsy/*` | 404 | unknown `vehicleId`, or no candidate path within the search bound |",
          "| `POST /routes/investigate`, `/autopsy/*` | 422 | unknown origin/destination (message lists valid node ids), origin = destination, unknown perturbation target |",
          "| `POST /evidence/analyze` | 413 / 415 / 422 | file too large / unsupported or mismatched type / empty file or half a location |",
          "| `POST /evidence/analyze` | 502 / 503 / 504 | invalid model output or provider error / not configured or rate-limited / provider timeout |",
          "| `POST /evidence/confirm` | 404 | unknown `evidenceId` |",
          "| `GET /vehicles/{vehicle_id}/restriction-check` | 404 | unknown vehicle |",
          "| `GET /defects/{defect_id}` | 404 | unknown defect |", ""]
    L += ["## 2. Behaviour rules the frontend relies on", "",
          "* `POST /routes/investigate` returns one route (`routeId, origin, destination, distanceKm, durationMin, segments`) plus `alternatives[]`. `recommended=false` + `recommendationStatus=\"no_usable_route\"` means the shown route is the least-bad option and is **not** recommended.",
          "* `riskLevel` per segment: `high` = verified blocking restriction or unresolved severity≥4 defect; `medium` = warnings, severity 2–3 defect, poor/unknown surface or incomplete data; else `low`.",
          "* `POST /autopsy/*`: perturbations are applied to in-memory copies only (`persisted` is always `false`). `sensitivityScore = Σw·[changed] / Σw`, `null` if nothing was tested. A scenario's `revisedRoute` is present only when the recommendation changed; `comparison` is always present when either side has a route.",
          "* `POST /evidence/analyze`: every observation has `verificationStatus=\"unverified\"`; `visualConfidence` is not verification; `location.status` is `unknown` unless the user supplied coordinates; images are never stored.",
          "* `POST /evidence/confirm`: only `candidateCategory=\"defect\"` observations can become defect reports (through the existing defect workflow, always `unverified`). Restriction/closure candidates always return `restriction_not_confirmed`. Outcomes: `defect_created`, `already_confirmed`, `duplicate_image_not_counted`, `needs_location`, `needs_severity`, `restriction_not_confirmed`, `not_actionable`, `unknown_observation`.",
          "* `GET /evidence/status` never exposes credentials; `configured=false` means `POST /evidence/analyze` will answer 503.",
          "* `GET /vehicles/{id}/restriction-check` uses the same per-restriction logic as the routing engine (pinned by a consistency test). `unknown_spec` means the vehicle's value is unknown, so clearance cannot be confirmed.", "",
          "### Why both `POST /routes` and `POST /routes/investigate` exist", "",
          "They are not duplicates created to avoid fixing the frontend. The frontend **was** corrected to call `/routes/investigate`. `POST /routes` is the original RouteWise contract "
          "(`originId`, `destinationId`, inline `vehicle` → list of alternatives) used by the original RouteWise client in the same repository, so removing or reshaping it would break a real consumer. "
          "It shares the same engine (`routing.compute_routes`). The Route Autopsy frontend does not call it.", "",
          "## 3. Models", ""]
    for n in collect(models, spec):
        L += model_table(n, spec)
    L += ["## 4. Untyped legacy responses (shapes verified by tests, not by OpenAPI)", ""]
    for (m, p), shape in UNTYPED_SHAPES.items():
        L.append(f"* `{m} {p}` → {shape}")
    L += ["", "## 5. Other backend endpoints (not used by this frontend)", "", "| Method | Path | Summary |", "|---|---|---|"]
    for m, p, op in other:
        L.append(f"| {m} | `{p}` | {(op.get('summary') or op.get('operationId', '')).replace('|', '/')} |")
    return "\n".join(L).rstrip() + "\n"


if __name__ == "__main__":
    text = render()
    if "--check" in sys.argv:
        cur = open(OUT).read() if os.path.exists(OUT) else ""
        sys.exit(0 if cur == text else 1)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write(text)
    print("wrote", OUT, len(text.splitlines()), "lines")
