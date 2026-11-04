# Route Autopsy backend (evolved from RouteWise)

FastAPI + Pydantic + SQLite. The original RouteWise capabilities (vehicle catalogue, defects, restrictions, maintenance, inspections/repairs, vehicle-aware routing on the illustrative Kochi graph) are **preserved**; Route Autopsy adds counterfactual sensitivity analysis and a Meta multimodal evidence pipeline on top.

> **Data warning.** The Kochi road graph, geometries, widths, surfaces, restrictions and seeded defects are **illustrative demo data**. They are not surveyed, live or official. This is not accurate real-world routing and must not be used for navigation. `riskLevel` and sensitivity scores are evidence-attention measures, **not** accident or failure probabilities.

## Quick start

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate        # Windows: py -3 -m venv .venv ; .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                       # Windows: copy .env.example .env
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Docs UI: <http://127.0.0.1:8000/docs> · health: <http://127.0.0.1:8000/health>

Frontend (separate folder): create `.env.local` with
```
VITE_APP_MODE=backend
VITE_API_BASE_URL=http://127.0.0.1:8000
```
then `npm install && npm run dev`. If the frontend runs on a non-localhost origin, add it to `CORS_ORIGINS`.

Reset the demo database: stop the server, delete `routewise.db`, start again.

## Configuration (`.env`) — only variables the code reads

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_PATH` | SQLite file | `backend/routewise.db` |
| `CORS_ORIGINS` | comma-separated allowed browser origins (localhost/127.0.0.1 on any port are always allowed) | common local dev ports |
| `SERPAPI_API_KEY`, `SERPAPI_TIMEOUT_SECONDS` | pre-existing optional vehicle-source discovery | off |
| `META_PROVIDER` | vision provider adapter; supported: `meta_model_api` | `meta_model_api` |
| `META_API_KEY` | Meta Model API key (server-side only, never returned or logged) | — |
| `META_MODEL` | model id to call. **Required, no default** (ids change; choose an image-capable one) | — |
| `META_API_BASE_URL` | override API base URL | `https://api.meta.ai/v1` |
| `META_TIMEOUT_SECONDS` | per-request model timeout (min 5) | `45` |
| `EVIDENCE_MAX_UPLOAD_BYTES` | max upload size | `10485760` (10 MB) |

Without `META_API_KEY`/`META_MODEL` everything except `POST /evidence/analyze` works; that endpoint answers `503` (after validating the upload).

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q          # 152 tests, ~13 s, no internet, no credentials needed
```

| Test file | Covers |
|---|---|
| `test_routing.py` (24) | candidate enumeration, slower-suitable routes, height/width/weight/closure, missing specs, legacy `/routes` |
| `test_autopsy.py` (27) | baseline, every perturbation type, sensitivity maths, **database never changes** |
| `test_evidence.py` (50) | upload validation, model-output parsing, trust rules, confirmation workflow, duplicate images |
| `test_integration.py` (18) | CORS, request/response compatibility, error shapes, OpenAPI, existing endpoints |
| `test_extensions.py` (18) | scenario `comparison`/`revisedRoute`, vehicle restriction check (pinned to the routing engine), evidence status |
| `test_meta_http_stub.py` (10) | the real Meta HTTP client over real HTTP against `scripts/stub_meta_server.py` (success, auth failure, timeout, bad JSON, unreachable) |
| `test_api_contract_doc.py` (5) | `docs/API_CONTRACT.md` is current; every path the frontend calls exists in OpenAPI |

Regenerate the frontend contract fixtures (real backend responses used by the frontend's vitest contract test):
```bash
python scripts/generate_contract_fixtures.py ../frontend/src/test/fixtures
```

## Endpoints

### Pre-existing (unchanged behaviour)
`GET /health` · `GET /api/health` · `GET /api/meta` · `GET|PUT /vehicles` · `GET|DELETE /vehicles/{id}` · `POST /vehicles/lookup` · `GET|POST /defects` · `GET /defects/{id}` · `PATCH /defects/{id}/status` · `POST /defects/{id}/confirm` · `POST /defects/{id}/resolve` · `GET /restrictions` · `GET /roads/nearby` · `GET /roads/{segment_id}` · `POST /routes` (legacy list contract) · `GET /maintenance/summary` · `GET /admin/defects` · `GET /admin/priority-segments` · `POST /admin/inspections` · `POST /admin/repairs`

Changes to pre-existing endpoints (all additive, except the two marked ⚠):
* `GET /vehicles`, `GET /vehicles/{id}`: each profile gains `name`, `type`, `unknownSpecs`, `notes` (derived by `compat.to_display_vehicle`). Every original field is retained. `PUT /vehicles` still stores the original model.
* `POST /routes`: same request/response shape; items gain `rank`, `isFastestCandidate`, `scoreSeconds`, `scoreBreakdown`, `rejectionReasons`; warnings may carry `restrictionId`/`defectId`. ⚠ Candidate selection changed (all candidates are evaluated, see below). ⚠ `recommended` is now `false` for every route when none is usable (previously the first, unsuitable, route was flagged).

### New
Full request/response schemas: **`docs/API_CONTRACT.md`** (generated from the code; `python scripts/generate_api_contract.py`).

| Endpoint | Purpose |
|---|---|
| `POST /routes/investigate` | Frontend contract: one route (`routeId, origin, destination, distanceKm, durationMin, segments`) **plus** `alternatives`, suitability, explanations, search stats |
| `POST /autopsy/analyze` | Baseline + default counterfactual suite (+ optional extra perturbations) + sensitivity |
| `POST /autopsy/scenario` | Caller-chosen perturbations against the same baseline |
| `GET /autopsy/health` | Engine/limits/weights/formula |
| `POST /evidence/analyze` | multipart image → candidate (unverified) observations via Meta model |
| `POST /evidence/confirm` | User confirms candidates → defects through the existing workflow |
| `GET /evidence/{id}` | Stored analysis (no image data) |
| `GET /evidence/status` | Is the vision provider configured? Model name only, never credentials |
| `GET /vehicles/{id}/restriction-check` | Every restriction classified for one vehicle (`blocks` / `may_block` / `unknown_spec` / `fits` / `not_applicable`), using the same per-restriction logic as routing |

Why `/routes/investigate` and not `POST /routes`: the legacy `POST /routes` has a different request (`originId`, `destinationId`, inline `vehicle`) and returns a list. Changing it would break existing clients, so the frontend contract lives beside it. `/routes/investigate` also accepts `originId`/`destinationId` as aliases.

## Routing engine (`app/routing.py`)

Pure functions (no DB access). Original function names (`enumerate_paths`, `oriented_geometry`, `applies`, `vehicle_value`, `evaluate_path`, `route_explanation`, `nearest_segment`, `calculate_routes`) remain importable from `app.main`.

Fix to the original limitation: it sorted candidates by duration and evaluated **only the 3 fastest**. Now:
1. Enumerate simple paths, bounded by depth (6 segments), candidates (5000) and DFS expansions (250k); `search.truncated` reports if a bound was hit.
2. Evaluate **every** candidate against hard restrictions (verified weight/height/width/access/closure ⇒ `unsuitable`), then rank by `(statusRank, score, duration)`. Slower suitable routes are never discarded because faster ones are blocked.
3. States: `suitable`, `warning` (unverified/unknown/incomplete data), `not_validated` (no vehicle), `unsuitable`.
4. Existing penalties are unchanged: +600 s per unresolved severity ≥ 4 defect, +240 s/km poor surface, +90 s/km unknown surface.
5. Returned: up to 5 usable alternatives, up to 3 rejected ones (fastest first) and always the overall fastest candidate, each with an explanation (`rejectionReasons` for blocked routes).

Scanning the seeded data (the 7 catalogue vehicles plus the no-vehicle case, every ordered node pair), 22 combinations had a better recommendation than the old top-3 shortcut found (e.g. `veh-swift` FKC→TPR: best route is the 4th fastest; score 3936 vs 4536).

## Route Autopsy (`app/route_autopsy.py`)

No routing logic of its own: every baseline and scenario calls `routing.compute_routes` on **deep copies** of vehicle/defects/restrictions. Nothing is written to SQLite (`persisted: false`; tested by snapshotting every table before/after).

Perturbation types (`type`): `resolve_defect`, `verify_restriction`, `remove_restriction`, `set_vehicle_height`, `set_vehicle_width`, `set_vehicle_weight`, `close_segment` (adds a hypothetical verified closure), `set_evidence_verification` (defect or restriction).

Each scenario also returns `comparison` (before/after duration, distance, suitability, severe defects, score, segments dropped/added/kept, and the score lead over the runner-up) and, when the recommendation changed, the full `revisedRoute` (segments, geometry, warnings). When the recommendation is stable the comparison re-scores the *same* route under the changed evidence, so the explanation can say how far ahead it stays.

Each scenario starts from the same baseline, changes exactly one input (`changedVariables`), recomputes, and returns `baselineRecommendation`, `revisedRecommendation`, `changed`, `changedWarnings` (added/removed warnings on the *baseline route* under the scenario), `baselineRouteUnderScenario` (status before/after) and a deterministic `explanation`. No-op perturbations (value already set) are flagged `skipped` and excluded from the score.

**Sensitivity**: `F = Σ w_i·[recommendation changes] / Σ w_i` over tested perturbations. Weights: 1.0 for evidence perturbations, 0.5 for vehicle-spec perturbations (their ±10 % size is arbitrary); a request may override `weight`. `sensitivityScore` is `null` if nothing was tested. It is **not** an accident probability, failure probability or verified road-safety risk.

Default suite (`/autopsy/analyze`): resolve each severity ≥ 4 defect on an evaluated alternative; remove / verify / un-verify each applicable restriction there; close each segment of the recommended route; vehicle height/width/weight ±10 % where known (unknown specs are skipped and reported). Defect verification status is displayed but is not a routing input, so it is excluded from the default suite (an explicit request is allowed and carries a note saying it cannot change the result). Max 60 scenarios.

## Meta multimodal evidence (`app/meta_model_client.py`, `app/vision_evidence.py`, `app/routers_evidence.py`)

Provider facts (checked against Meta's developer blog and the LiteLLM/promptfoo provider docs, 2026-10-30): Meta's Llama API preview was retired on 2026-07-06 and superseded by the **Meta Model API** (`https://api.meta.ai/v1`, OpenAI-compatible `/chat/completions`, bearer key from dev.meta.ai, images as base64 `image_url` data URLs; e.g. `muse-spark-1.1` lists image input). The client targets that. **It has not been run against the live API in this repository (no credential was available)**; the request shape and all error paths are tested against a mocked HTTP layer. The provider sits behind the `VisionModelClient` protocol, and the routing engine never imports it.

Pipeline: upload → declared MIME **and** magic bytes must be JPEG/PNG/WebP, size ≤ limit (read capped at limit+1 bytes) → model call (timeout, error mapping) → strict parse → candidates returned → **user confirms** → existing defect workflow.

Trust rules enforced in code (each has tests, and the key ones were mutation-checked):
* Every observation is `verificationStatus: "unverified"`; `visualConfidence` is labelled as not verification.
* The backend, not the model, assigns the category. Signs/closures become `restriction_candidate`/`closure_candidate` and **can never be confirmed** here (`restriction_not_confirmed`); no restriction is ever written, so routing is unaffected.
* Model-supplied coordinates, addresses, dimensions, clearance, ids, or "verified" flags are discarded and listed in `discardedModelFields`. Unknown extra fields are preserved verbatim in `modelExtras` but never trusted.
* Location is `unknown` unless the user supplies lat/lon (at upload or confirm). Without it a defect cannot be created (`needs_location`).
* Defects are created through `defects.create_defect_record` (same code as `POST /defects`): unverified, open, `independentReportCount: 1`, plus provenance (`evidenceId`, `modelProvider`, `visualConfidence`, `userConfirmedObservation`, `observedAtBasis: "upload_time"`). `photoUrl` stays null; **images are never stored**, only a SHA-256.
* Duplicate images are flagged (`duplicateOf`); confirming the same image again returns the existing defect (`duplicate_image_not_counted`) and does not raise the report count.
* User notes are stored with the report but not sent to the model. The key never appears in responses, logs or OpenAPI.

**New table (documented because the spec asks):** `evidence_analyses(id, payload, created_at)`. Needed so `POST /evidence/confirm` acts on what the backend recorded rather than trusting client-supplied observation content. Created with `CREATE TABLE IF NOT EXISTS`; no existing table or column changed.

### Sample requests and (real, trimmed) responses

```bash
curl -s -X POST localhost:8000/routes/investigate -H 'content-type: application/json' \
  -d '{"origin":"VYT","destination":"KKD","vehicleId":"veh-ecomet"}'
```
```json
{"routeId":"VYT-KKD-S6_S13","origin":"Vyttila Hub","destination":"Kakkanad","originId":"VYT","destinationId":"KKD",
 "distanceKm":10.08,"durationMin":20.1,
 "segments":[{"id":"S6","name":"NH 66 Bypass (Vyttila–Palarivattom)","distanceKm":5.11,"riskLevel":"medium","note":"Severity 2 damaged surface reported (unverified)."}, "…"],
 "vehicle":{"id":"veh-ecomet","name":"Ashok Leyland Ecomet 2022 1615 HE","type":"Heavy truck","heightM":3.3,"widthM":2.5,"verificationStatus":"estimated","unknownSpecs":[], "…":"…"},
 "suitabilityStatus":"suitable","recommended":true,"recommendationStatus":"recommended",
 "explanation":"Route A (via NH 66 Bypass (Vyttila–Palarivattom), Civil Line Rd) is recommended and is the fastest option, with 2 known hazards (1 severe). Estimated 20 min.",
 "alternatives":[{"routeId":"VYT-KKD-S6_S13","label":"Route A","recommended":true,"rank":1,"scoreBreakdown":{"travelSeconds":1204,"severeDefectPenaltySeconds":600,"surfacePenaltySeconds":0},"…":"…"},
                 {"routeId":"VYT-KKD-S12","label":"Route B","suitabilityStatus":"unsuitable","rejectionReasons":["Height limit 3.2 m on Thammanam–Kakkanad Link (rail underpass); your vehicle is 3.30 m. Vehicle is not permitted / cannot pass.", "…"],"…":"…"}],
 "search":{"candidatesEnumerated":11,"candidatesEvaluated":11,"truncated":false,"maxDepth":6,"…":"…"}}
```

```bash
curl -s -X POST localhost:8000/autopsy/scenario -H 'content-type: application/json' \
  -d '{"origin":"VYT","destination":"KKD","vehicleId":"veh-ecomet","perturbations":[{"type":"close_segment","segmentId":"S6"}]}'
```
```json
{"analysisId":"ra-8c37a28821ed","persisted":false,
 "baselineRecommendation":{"routeId":"VYT-KKD-S6_S13","segmentIds":["S6","S13"],"durationMin":20.1,"suitabilityStatus":"suitable"},
 "scenarios":[{"scenarioId":"sc-01","description":"segment S6 (NH 66 Bypass (Vyttila–Palarivattom)) is closed","weight":1.0,"changed":true,
   "revisedRecommendation":{"routeId":"VYT-KKD-S4_S3_S5_S13","segmentIds":["S4","S3","S5","S13"],"durationMin":31.4,"suitabilityStatus":"suitable"},
   "deltaDurationMin":11.3,
   "changedVariables":[{"variable":"segment[S6].closure","from":"none","to":"hypothetical verified closure"}],
   "changedWarnings":{"added":["Road closure on NH 66 Bypass (Vyttila–Palarivattom): Hypothetical closure (Route Autopsy scenario, not real)"],"removed":[]},
   "baselineRouteUnderScenario":{"statusBefore":"suitable","statusAfter":"unsuitable"},
   "explanation":"Hypothetically, segment S6 (…) is closed. The recommendation would change from route S6 → S13 to route S4 → S3 → S5 → S13 (11.3 min longer) because the baseline route would change from suitable to unsuitable (new constraint: Road closure on …)."}],
 "sensitivity":{"scenariosTested":1,"scenariosChanged":1,"sensitivityScore":1.0,"totalWeight":1.0,"changedWeight":1.0,"formula":"F = sum(weight_i …) / sum(weight_i …)","interpretation":"… not an accident probability, a failure probability, or a verified road-safety risk."}}
```

```bash
curl -s -X POST localhost:8000/evidence/analyze -F 'file=@road.jpg;type=image/jpeg' -F latitude=10.0 -F longitude=76.3
```
```json
{"evidenceId":"EV-6CF92CC7F5","modelProvider":"meta_model_api","model":"<META_MODEL>",
 "location":{"status":"user_provided","latitude":10.0,"longitude":76.3,"note":"Location was supplied by the uploader, not inferred from the image."},
 "observations":[{"id":"obs-1","observationType":"pothole","candidateCategory":"defect","suggestedDefectType":"pothole","description":"Deep pothole in the left lane.",
   "severityEstimate":4,"visualConfidence":0.9,"unknownAttributes":["road dimensions and vehicle clearance"],"verificationStatus":"unverified",
   "requiresAuthorizedVerification":false,"source":"image_upload","modelExtras":{},"discardedModelFields":[]}],
 "duplicateOf":null}
```
```bash
curl -s -X POST localhost:8000/evidence/confirm -H 'content-type: application/json' \
  -d '{"evidenceId":"EV-6CF92CC7F5","confirmedObservationIds":["obs-1"]}'
# → {"status":"defects_created","results":[{"observationId":"obs-1","outcome":"defect_created","defectId":"U-A349A477","verificationStatus":"unverified", …}]}
```
Error statuses: `415` unsupported/mismatched file, `413` too large, `422` empty/invalid fields, `502` invalid model output or provider error, `503` not configured or rate-limited, `504` provider timeout. All errors use FastAPI's `{"detail": …}`.

### Verifying the Meta integration

| What | How | Status |
|---|---|---|
| Real Meta credential | `python scripts/check_meta_live.py photo.jpg` (needs `META_API_KEY`, `META_MODEL`) | **Not run: no credential was available.** Exit codes: 0 ok, 2 bad input/config, 3 provider error, 4 invalid model output |
| Our HTTP client, over the wire | `scripts/stub_meta_server.py` (OpenAI-compatible stand-in, **not Meta**, every observation labelled `[STUB]`) + `tests/test_meta_http_stub.py` + the browser tests | Done: request shape (auth header, base64 data-URL image, system prompt), success, 401, 5xx, invalid JSON, timeout, unreachable |

Passing the stub tests shows our client and parsing behave correctly when a server speaks the documented protocol. It says nothing about Meta's service, model id, rate limits or output quality.

## Google Maps readiness

The engine and evidence store depend only on the pilot graph; no map-provider code or SDK is imported. A future Google Maps layer would only render `geometry`/`segments` or supply coordinates for `POST /evidence/analyze`. Google route geometry does **not** supply a segment graph or restriction database, and this repo does not claim it does.

## Known limitations

* Illustrative Kochi graph only (10 nodes, 16 undirected segments): not real routing; no turn restrictions, directions, time-of-day or live traffic.
* Meta integration is untested against the live API (no credential); see "Verifying the Meta integration".
* `GET /defects`, `GET /restrictions` and `GET /api/meta` are pre-existing and untyped in OpenAPI; their shapes are documented in `docs/API_CONTRACT.md` and parsed (and so verified) by the frontend's Zod schemas. Model id, `response_format`/structured-output support and rate limits must be confirmed with a real key; the code asks for JSON in the prompt and validates strictly instead of relying on provider-side schema enforcement.
* Vision output is a single-image, unverified suggestion. It can be wrong or injected via text in the photo (mitigated by validation, never auto-confirmation, no restriction writes).
* No authentication/authorization anywhere (pre-existing). `POST /defects/{id}/confirm` still lets any caller mark a defect `verified`, and there is no "authorized verification workflow" for restrictions, so restriction candidates stay candidates.
* Defect `verificationStatus` is not a routing input; unverified severe defects are penalised like verified ones (pre-existing behaviour, unchanged).
* `riskLevel` per segment and the sensitivity score are transparent heuristics, not validated risk models. The ±10 % vehicle perturbations and the weights are design choices, documented above.
* Sensitivity is stateless: `analysisId` is not stored, and results can't be re-fetched.
* The `@app.on_event("startup")` hook (pre-existing) emits a FastAPI deprecation warning.
* SQLite, single process: fine for the demo, not for multi-user deployment.
