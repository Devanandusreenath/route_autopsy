# Project structure

Generated folders (`node_modules`, `.venv`, `.output`, `.stack`) are not shipped. `frontend/src/components/ui` is the unmodified shadcn/ui kit.

```
./
├── backend/                                            # FastAPI backend
│   ├── app/                                            # Application package
│   │   ├── __init__.py
│   │   ├── compat.py                                   # Vehicle adapter + route-response mapping
│   │   ├── config.py                                   # Environment config
│   │   ├── database.py                                 # SQLite helpers
│   │   ├── defects.py                                  # Shared defect-creation workflow
│   │   ├── main.py                                     # App, CORS, pre-existing endpoints, legacy POST /routes
│   │   ├── meta_model_client.py                        # Isolated Meta Model API client
│   │   ├── pilot.py                                    # Illustrative Kochi graph (unchanged)
│   │   ├── route_autopsy.py                            # Counterfactuals, comparison, sensitivity (uses routing.py)
│   │   ├── routers_autopsy.py                          # /routes/investigate, /autopsy/*
│   │   ├── routers_evidence.py                         # /evidence/*
│   │   ├── routers_vehicles.py                         # /vehicles/{id}/restriction-check
│   │   ├── routing.py                                  # Pure routing engine (bounded enumeration, evaluation, ranking, check_restriction)
│   │   ├── schemas.py                                  # Pydantic models
│   │   ├── seed.py                                     # Seed data (unchanged)
│   │   └── vision_evidence.py                          # Upload validation + strict model-output parsing
│   ├── docs/
│   │   └── API_CONTRACT.md                             # Definitive API contract (GENERATED from OpenAPI; guarded by tests)
│   ├── scripts/                                        # Backend utility scripts
│   │   ├── check_meta_live.py                          # One-command check of the REAL Meta integration (needs a key)
│   │   ├── generate_api_contract.py                    # Generates docs/API_CONTRACT.md
│   │   ├── generate_contract_fixtures.py               # Captures real responses for the frontend contract tests
│   │   └── stub_meta_server.py                         # LOCAL STUB of a vision API (NOT Meta; labels output [STUB])
│   ├── tests/                                          # Backend tests (152)
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_api_contract_doc.py
│   │   ├── test_autopsy.py
│   │   ├── test_evidence.py
│   │   ├── test_extensions.py
│   │   ├── test_integration.py
│   │   ├── test_meta_http_stub.py
│   │   └── test_routing.py
│   ├── .env.example                                    # Environment template (copy to .env)
│   ├── .gitignore
│   ├── README.md                                       # Backend setup, endpoints, trust rules, limitations
│   ├── requirements-dev.txt
│   └── requirements.txt
├── frontend/                                           # React app (TanStack Router/Query, Zod, Leaflet)
│   ├── e2e/                                            # Browser end-to-end tests (real Chromium)
│   │   ├── fixtures/                                   # Test photo
│   │   │   └── … (1 files)
│   │   ├── screenshots/                                # Screenshots from the verified run
│   │   │   └── … (10 files)
│   │   ├── e2e.mjs                                     # 16 browser tests
│   │   ├── package-lock.json
│   │   └── package.json
│   ├── public/
│   │   └── … (2 files)
│   ├── src/
│   │   ├── components/
│   │   │   ├── app/                                    # Application components
│   │   │   │   ├── AppShell.tsx
│   │   │   │   ├── MapView.tsx                         # Leaflet map (routes, markers, click-to-set-location)
│   │   │   │   ├── RouteComparison.tsx                 # Before/after comparison
│   │   │   │   ├── RouteInputs.tsx                     # Origin/destination/vehicle pickers
│   │   │   │   ├── SensitivityMeter.tsx                # Score + meaning/caveat
│   │   │   │   ├── status.tsx
│   │   │   │   └── VehicleRestrictionsPanel.tsx        # Per-vehicle restriction check
│   │   │   └── ui/
│   │   │       └── … (46 files)
│   │   ├── hooks/
│   │   │   └── use-mobile.tsx
│   │   ├── lib/
│   │   │   ├── api/                                    # One module per backend area; Zod schemas in types/
│   │   │   │   ├── types/
│   │   │   │   │   ├── autopsy.ts
│   │   │   │   │   ├── common.ts
│   │   │   │   │   ├── defects.ts
│   │   │   │   │   ├── evidence.ts
│   │   │   │   │   ├── network.ts
│   │   │   │   │   ├── restrictions.ts
│   │   │   │   │   ├── routes.ts
│   │   │   │   │   └── vehicles.ts
│   │   │   │   ├── autopsy.api.ts
│   │   │   │   ├── client.ts
│   │   │   │   ├── config.ts
│   │   │   │   ├── defects.api.ts
│   │   │   │   ├── endpoints.ts                        # The single endpoint map (checked against the backend by a test)
│   │   │   │   ├── errors.ts
│   │   │   │   ├── evidence.api.ts
│   │   │   │   ├── network.api.ts
│   │   │   │   ├── restrictions.api.ts
│   │   │   │   ├── routes.api.ts
│   │   │   │   └── vehicles.api.ts
│   │   │   ├── demo/                                   # Synthetic provider (demo mode only)
│   │   │   │   └── provider.ts
│   │   │   ├── error-capture.ts
│   │   │   ├── error-page.ts
│   │   │   ├── error-reporting.ts
│   │   │   ├── map-data.ts                             # Builds map markers/routes from real API data
│   │   │   ├── use-overlay-data.ts                     # Loads network, defects, restrictions for map overlays
│   │   │   └── utils.ts
│   │   ├── routes/                                     # Pages
│   │   │   ├── __root.tsx
│   │   │   ├── autopsy.tsx                             # Autopsy Lab (full flow)
│   │   │   ├── evidence.tsx                            # Evidence Lab
│   │   │   ├── index.tsx                               # Route Investigation
│   │   │   ├── README.md
│   │   │   └── vehicles.tsx                            # Vehicle profiles + restriction check
│   │   ├── test/                                       # Frontend tests
│   │   │   ├── fixtures/                               # REAL backend responses used by the contract tests
│   │   │   │   └── … (15 files)
│   │   │   ├── api-client.test.ts
│   │   │   ├── app-routing.test.tsx
│   │   │   ├── backend-contract.test.ts                # Real responses parse with the UI's Zod schemas
│   │   │   ├── components.test.tsx                     # Component + map-data tests
│   │   │   ├── live-backend.test.ts                    # Real API modules vs a running backend
│   │   │   ├── no-demo-fallback.test.ts                # Backend mode never returns demo data
│   │   │   └── setup.ts
│   │   ├── router.tsx
│   │   ├── routeTree.gen.ts
│   │   ├── server.ts
│   │   ├── start.ts
│   │   └── styles.css
│   ├── .env.example
│   ├── .gitignore
│   ├── .prettierignore
│   ├── .prettierrc
│   ├── AGENTS.md
│   ├── BACKEND_INTEGRATION.md                          # How the frontend connects; guarantees and the tests behind them
│   ├── bunfig.toml
│   ├── components.json
│   ├── eslint.config.js
│   ├── package-lock.json
│   ├── package.json
│   ├── README.md
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── vitest.config.ts
├── scripts/                                            # Project-level scripts
│   ├── stack.sh                                        # Start/stop backend + stub provider + UI (backend and demo modes)
│   └── verify_all.sh                                   # Re-run every verification step from scratch
├── DEMO.md                                             # 5-minute demo walkthrough
├── README.md                                           # Overview, run instructions, verified results, limitations
└── STRUCTURE.md                                        # This file
```

