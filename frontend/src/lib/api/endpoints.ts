/**
 * Endpoint map for the Route Autopsy backend (FastAPI). Every entry is covered by backend/tests/test_api_contract_doc.py,
 * which fails if a path here does not exist in the backend's OpenAPI schema. See backend/docs/API_CONTRACT.md.
 *
 * `POST /routes` (the original RouteWise list contract) also exists for the original RouteWise client; this app uses `/routes/investigate`.
 */
const id = encodeURIComponent;

export const endpoints = {
  routes: "/routes/investigate",
  autopsyAnalyze: "/autopsy/analyze",
  autopsyScenario: "/autopsy/scenario",
  evidenceStatus: "/evidence/status",
  evidenceAnalyze: "/evidence/analyze",
  evidenceConfirm: "/evidence/confirm",
  vehicles: "/vehicles",
  vehicleRestrictionCheck: (vehicleId: string) => `/vehicles/${id(vehicleId)}/restriction-check`,
  restrictions: "/restrictions",
  defects: "/defects",
  defect: (defectId: string) => `/defects/${id(defectId)}`,
  network: "/api/meta",
} as const;
