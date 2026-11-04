/**
 * Contracts in this folder mirror the backend's Pydantic models (backend/app/schemas.py) and are verified against the
 * backend's real responses (src/test/backend-contract.test.ts, src/test/live-backend.test.ts). Reference: backend/docs/API_CONTRACT.md.
 */
export type DataSource = "demo" | "backend";

/** Every API function returns its data tagged with where it came from. */
export interface ApiResult<T> {
  data: T;
  source: DataSource;
}

export type RiskLevel = "low" | "medium" | "high";
