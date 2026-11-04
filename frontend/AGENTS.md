## Architecture rules
- All HTTP goes through `src/lib/api/client.ts`; UI calls only `src/lib/api/*.api.ts` — keeps backend swaps in one layer.
- Endpoint paths live only in `src/lib/api/endpoints.ts`; they are confirmed against the Route Autopsy backend (backend/README.md).
- Request/response Zod schemas in `src/lib/api/types/` mirror the backend Pydantic models and are checked against real backend responses by `src/test/backend-contract.test.ts` (see BACKEND_INTEGRATION.md).
- Demo data lives only in `src/lib/demo/`, used only when mode is demo, never as a fallback for failed backend calls — avoids fake success.
- No secrets in `VITE_*` vars; Meta/model calls go through the backend.
