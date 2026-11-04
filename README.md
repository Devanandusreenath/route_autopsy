# Route Autopsy — integrated application

Vehicle-aware route investigation, counterfactual "autopsy" of recommendations, and AI-assisted road-evidence capture, as one working application.

```
backend/    FastAPI + Pydantic + SQLite (RouteWise evolved)      → backend/README.md, backend/docs/API_CONTRACT.md
frontend/   React + TanStack Router/Query + Zod + Leaflet        → frontend/BACKEND_INTEGRATION.md
scripts/    stack.sh (start/stop everything), verify_all.sh (re-run every check)
DEMO.md     5-minute demo walkthrough
```

> **Data warning.** The Kochi road graph, restrictions and seeded defects are illustrative demo data. This is not real-world routing. Sensitivity scores and `riskLevel` are evidence-attention measures, not accident or failure probabilities.

## Run it

```bash
scripts/stack.sh start stub     # backend :8000, LOCAL STUB vision provider :9100, UI :5180 (backend mode), UI :5181 (demo mode)
open http://127.0.0.1:5180      # follow DEMO.md
scripts/stack.sh stop
```
`stub` is a stand-in for the vision model so the image flow runs without a credential: **it is not Meta** and labels everything `[STUB]`. For real Meta analysis run the backend with `META_API_KEY` and `META_MODEL` (see `backend/.env.example`) and verify with `backend/scripts/check_meta_live.py photo.jpg`. Use `scripts/stack.sh start none` to see the "image analysis not configured" state.

Requirements: Python 3.11+, Node 20+. Manual setup per component is in the two READMEs.

## What was built, by phase

| Phase | Delivered |
|---|---|
| **1. Contracts** | `backend/docs/API_CONTRACT.md` is **generated from the backend's OpenAPI schema** and guarded by tests (stale doc or a frontend path missing from the backend fails the build). Frontend calls `/routes/investigate`; Autopsy requests/responses mirror the Pydantic models; the departure-time scenario is replaced by the 8 supported perturbations; evidence observation/confirmation schemas and vehicle responses are aligned; all "provisional/unconfirmed" comments were removed after verification. |
| **2. Autopsy experience** | Select route + vehicle → baseline + alternatives on a map → counterfactual list (filter changed/stable) → sensitivity score with its meaning and limits always visible → before/after comparison (metrics, segments dropped/added/kept, changed variables, warnings) → the backend's explanation of why it changed or stayed stable → what-if builder fed by real segments/defects/restrictions. Backend additions that make this honest: `comparison` and `revisedRoute` per scenario. |
| **3. Evidence Lab** | Upload → your original photo beside the model's structured observations → each badged "AI candidate · unverified" → location by map click or coordinates → severity → confirm → report ID and verification status re-read from the backend. Restriction/closure candidates cannot be confirmed (UI and backend). Duplicate images don't create second reports. |
| **4. Visual experience** | Leaflet map with route alternatives (recommended / rejected / alternative / baseline / revised), defect markers (size = severity, solid = verified) and restriction markers; before/after comparison; per-vehicle restriction check with unknown specs called out; loading, empty, error (with retry) and success (toast) states; existing dark/amber identity kept. |
| **5. Verification** | `scripts/verify_all.sh`, below. |

## Verified results

| Check | Result |
|---|---|
| Backend tests | **152 passed** (no network or credentials) |
| Frontend typecheck / lint | clean / 0 errors, 7 warnings (same as the original export, none from new code) |
| Frontend tests | **79 passed** + 9 live-only (contract tests parse real backend responses with the UI's Zod schemas; 36 tests prove backend mode never returns demo data) |
| Production build | succeeds; no credential-like strings in the bundle or frontend source |
| **Live API test** (the UI's real API modules vs a *running* backend) | **9/9**, run twice: no provider configured (503 path) and wired to the stub (full upload → analyze → confirm → re-read) |
| **Browser end-to-end** (real headless Chromium, real UI, real backend) | **16/16**: routes, map line/marker counts equal the API's, sensitivity equals the API's, comparison/explanation text equals the API's, evidence flow incl. map-click location, duplicates, error states, mobile width, demo mode makes zero backend calls, zero console errors |
| Database safety | autopsy runs leave every table byte-identical |

Screenshots from the browser run: `frontend/e2e/screenshots/`.

## Not verified — please read

* **Live Meta.** No credential was available, and this environment cannot reach `api.meta.ai`. The client targets Meta's documented Model API (`https://api.meta.ai/v1/chat/completions`) and is verified over real HTTP only against the local stub. Run `backend/scripts/check_meta_live.py` with your key; set `META_MODEL` to a current image-capable model. If Meta's behaviour differs from its documentation, expect to adjust `backend/app/meta_model_client.py` (isolated for that reason).
* **Map tiles.** The sandbox had no internet, so basemap tiles were never seen loading; the "tiles unavailable" fallback was. OpenStreetMap tiles are used on a best-effort demo basis (respect their usage policy for anything beyond a demo).
* **Browsers.** Tested in headless Chromium only, at 1366 px and 390 px widths.
* The stub's `[STUB]` output exercises plumbing, not model quality.
* No authentication exists anywhere (pre-existing). `POST /defects/{id}/confirm` still lets any caller mark a defect verified, and there is no authorized-verification workflow for restrictions. See `backend/README.md` → Known limitations.

## Decisions worth knowing

* **Both `POST /routes` and `POST /routes/investigate` exist, deliberately.** The frontend was corrected to `/routes/investigate`. The legacy endpoint is the original RouteWise contract (different request, list response) used by the original RouteWise client in the same repository, so removing it would break a real consumer. Both call the same engine. Explained in `API_CONTRACT.md`.
* The uploaded `route-autopsy_1.zip` was byte-identical to the original Lovable export (none of the earlier integration work), so this delivery applies everything on top of it; the uploaded backend was identical to the previous delivery.
* The routing algorithm was **not replaced**. The earlier fix (evaluate every bounded candidate, not just the 3 fastest) stands, with regression tests.
* New backend endpoints exist only because the UI needed real data it couldn't get otherwise: `GET /evidence/status`, `GET /vehicles/{id}/restriction-check`, and `comparison`/`revisedRoute` on scenarios.
