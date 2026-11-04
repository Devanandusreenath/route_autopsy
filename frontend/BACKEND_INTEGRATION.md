# Frontend ↔ backend integration

The frontend talks to the Route Autopsy FastAPI backend through **one HTTP client** (`src/lib/api/client.ts`) and one **endpoint map** (`src/lib/api/endpoints.ts`). Every response is validated with a Zod schema (`src/lib/api/types/*`) that mirrors the backend's Pydantic models. A mismatch becomes a visible "unexpected response" error, never silently wrong data.

**The authoritative contract is `backend/docs/API_CONTRACT.md`.** It is generated from the backend's OpenAPI schema, and `backend/tests/test_api_contract_doc.py` fails if it is stale or if `endpoints.ts` calls a path the backend does not have.

## Run it

```bash
scripts/stack.sh start stub      # from the repo root: backend :8000 + local STUB vision provider :9100 + UI :5180 (backend mode) / :5181 (demo)
# or by hand:
cd backend && python -m uvicorn app.main:app --port 8000
cd frontend && printf 'VITE_APP_MODE=backend\nVITE_API_BASE_URL=http://127.0.0.1:8000\n' > .env.local && npm install && npm run dev
```

If the UI runs on a non-localhost origin, add it to the backend's `CORS_ORIGINS`.

## Modes (kept strictly separate)

| | Backend mode | Demo mode |
|---|---|---|
| Set by | `VITE_APP_MODE=backend` + `VITE_API_BASE_URL` | `VITE_APP_MODE=demo` (or neither variable) |
| Data | the real backend | hand-written synthetic data in `src/lib/demo/provider.ts` |
| Header badge | green `BACKEND · <url>` | amber `DEMO MODE · synthetic data` |
| Network | real HTTP | none |
| On failure | typed error + retry. **Never** falls back to demo data | n/a |

`src/test/no-demo-fallback.test.ts` proves the "never falls back" rule for all 12 API functions under network error, HTTP 500 and wrong-shape responses.

## Endpoints used

| Screen | Calls |
|---|---|
| Route Investigation | `GET /api/meta` (locations + map geometry), `GET /vehicles`, `GET /vehicles/{id}/restriction-check`, `POST /routes/investigate`, `GET /defects`, `GET /restrictions` |
| Autopsy Lab | the above plus `POST /autopsy/analyze`, `POST /autopsy/scenario` |
| Evidence Lab | `GET /evidence/status`, `POST /evidence/analyze` (multipart), `POST /evidence/confirm`, `GET /defects/{id}` (re-reads the created report) |
| Vehicle Profiles | `GET /vehicles`, `GET /vehicles/{id}/restriction-check` |

`POST /routes` (the original RouteWise list contract) still exists in the backend for the original RouteWise client; this app uses `/routes/investigate`. See "Why both exist" in the API contract.

## What the UI guarantees (and the test that checks it)

| Guarantee | Checked by |
|---|---|
| Sensitivity score shown is the backend's, with its "not an accident probability" caveat always visible | e2e: autopsy flow |
| Scenario explanation is the backend's text verbatim; before/after numbers come from `comparison` | e2e + `components.test.tsx` |
| Hypotheticals are never saved | e2e "nothing is persisted" + backend snapshot tests |
| AI observations are labelled "AI candidate · unverified"; visual confidence is labelled "not verification" | e2e: evidence flow |
| Restriction/closure candidates cannot be confirmed in the UI (and the backend would refuse) | e2e + backend tests |
| A defect report needs a user-supplied location; severity is required when the model gave none | e2e |
| The created report's ID and status shown are re-read from the backend, not echoed | e2e |
| Same image twice is flagged and creates no second report | e2e |
| Unknown vehicle specs show as "unknown" / "cannot confirm", never "fits" | e2e + backend consistency test |

## Maps

`MapView` uses Leaflet with OpenStreetMap tiles (public tile server; attribution shown). Tiles are **cosmetic**: if they can't load (offline), a notice appears and the road network, routes and markers still draw. Demo mode draws no tiles at all (synthetic schematic). The map reads only `geometry` already returned by the backend; no routing happens in the browser. Google Maps could replace it later without touching the API layer.

## Tests

| Command | What |
|---|---|
| `npm test` | api-client (15) + routing (1) + backend-contract (17, real backend responses parsed by the UI's Zod schemas) + no-demo-fallback (36) + components (10). Live tests are skipped unless `LIVE_API=1` |
| `LIVE_API=1 VITE_APP_MODE=backend VITE_API_BASE_URL=… npx vitest run src/test/live-backend.test.ts` | the real API modules against a **running** backend (9 tests) |
| `cd e2e && npm install && npm test` | real Chromium driving the real UI against the running stack (16 tests, screenshots in `e2e/screenshots`) |
| `scripts/verify_all.sh` (repo root) | everything above, from scratch |

Regenerate the contract fixtures after a backend change: `cd backend && python scripts/generate_contract_fixtures.py ../frontend/src/test/fixtures`.
