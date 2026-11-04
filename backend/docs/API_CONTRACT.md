# Route Autopsy — API Contract

> **Generated** from the FastAPI/Pydantic OpenAPI schema by `scripts/generate_api_contract.py` — do not edit by hand. `tests/test_api_contract_doc.py` fails if this file is stale or if the frontend calls an endpoint that does not exist.

Base URL (local): `http://127.0.0.1:8000`. All bodies are JSON except `POST /evidence/analyze` (multipart). Errors use FastAPI's `{"detail": string | [{loc, msg, type}]}`.

**Data warning:** the road graph, restrictions and seeded defects are illustrative demo data; sensitivity and `riskLevel` are evidence-attention measures, not accident or failure probabilities.

## 1. Endpoints used by the frontend

| Method | Path | Request | Response | Errors | Frontend consumer |
|---|---|---|---|---|---|
| GET | `/api/meta` | — | `{demoMode, pilotArea, warning, nodes:[{id,name,position:[lat,lon]}], segments:[{id,name,area,from,to,widthM,surface,restrictionDataComplete,geometry:[[lat,lon],…]}]}` (illustrative Kochi graph) | — | `network.api.ts › getNetwork` → `types/network.ts` |
| GET | `/vehicles` | — | array of `VehicleDisplay` | — | `vehicles.api.ts › listVehicles` → `types/vehicles.ts` |
| GET | `/vehicles/{vehicle_id}/restriction-check` | — | `VehicleRestrictionCheck` | 422 | `vehicles.api.ts › getVehicleRestrictionCheck` → `types/vehicles.ts` |
| GET | `/restrictions` | — | list of restrictions `{id, roadSegmentId, restrictionType, limitValue, unit, appliesTo: "all" | [category], description, source, verificationStatus, lastVerifiedAt}` | — | `restrictions.api.ts › listRestrictions` → `types/restrictions.ts` |
| GET | `/defects` | — | list of defect records `{id, defectType, latitude, longitude, severity 1-5, description, observedAt, roadSegmentId, reportedAt, verificationStatus, maintenanceStatus, independentReportCount, isUserSubmitted, …provenance fields for evidence-created defects}` | 422 | `defects.api.ts › listDefects` → `types/defects.ts` |
| GET | `/defects/{defect_id}` | — | one defect record (same shape as a `/defects` item) | 422 | `defects.api.ts › getDefect` → `types/defects.ts` |
| POST | `/routes/investigate` | `RouteInvestigationRequest` | `RouteInvestigationResponse` | 422 | `routes.api.ts › investigateRoute` → `types/routes.ts` |
| POST | `/autopsy/analyze` | `AutopsyAnalyzeRequest` | `AutopsyResponse` | 422 | `autopsy.api.ts › analyzeAutopsy` → `types/autopsy.ts` |
| POST | `/autopsy/scenario` | `AutopsyScenarioRequest` | `AutopsyResponse` | 422 | `autopsy.api.ts › runScenario` → `types/autopsy.ts` |
| GET | `/evidence/status` | — | `EvidenceStatus` | — | `evidence.api.ts › getEvidenceStatus` → `types/evidence.ts` |
| POST | `/evidence/analyze` | multipart: `file`, `notes`, `latitude`, `longitude` | `EvidenceAnalyzeResponse` | 422 | `evidence.api.ts › analyzeEvidence` → `types/evidence.ts` |
| POST | `/evidence/confirm` | `EvidenceConfirmRequest` | `EvidenceConfirmResponse` | 422 | `evidence.api.ts › confirmEvidence` → `types/evidence.ts` |

Documented HTTP errors beyond 422 (not in OpenAPI because they are raised in code):

| Endpoint | Status | Meaning |
|---|---|---|
| `POST /routes/investigate`, `/autopsy/*` | 404 | unknown `vehicleId`, or no candidate path within the search bound |
| `POST /routes/investigate`, `/autopsy/*` | 422 | unknown origin/destination (message lists valid node ids), origin = destination, unknown perturbation target |
| `POST /evidence/analyze` | 413 / 415 / 422 | file too large / unsupported or mismatched type / empty file or half a location |
| `POST /evidence/analyze` | 502 / 503 / 504 | invalid model output or provider error / not configured or rate-limited / provider timeout |
| `POST /evidence/confirm` | 404 | unknown `evidenceId` |
| `GET /vehicles/{vehicle_id}/restriction-check` | 404 | unknown vehicle |
| `GET /defects/{defect_id}` | 404 | unknown defect |

## 2. Behaviour rules the frontend relies on

* `POST /routes/investigate` returns one route (`routeId, origin, destination, distanceKm, durationMin, segments`) plus `alternatives[]`. `recommended=false` + `recommendationStatus="no_usable_route"` means the shown route is the least-bad option and is **not** recommended.
* `riskLevel` per segment: `high` = verified blocking restriction or unresolved severity≥4 defect; `medium` = warnings, severity 2–3 defect, poor/unknown surface or incomplete data; else `low`.
* `POST /autopsy/*`: perturbations are applied to in-memory copies only (`persisted` is always `false`). `sensitivityScore = Σw·[changed] / Σw`, `null` if nothing was tested. A scenario's `revisedRoute` is present only when the recommendation changed; `comparison` is always present when either side has a route.
* `POST /evidence/analyze`: every observation has `verificationStatus="unverified"`; `visualConfidence` is not verification; `location.status` is `unknown` unless the user supplied coordinates; images are never stored.
* `POST /evidence/confirm`: only `candidateCategory="defect"` observations can become defect reports (through the existing defect workflow, always `unverified`). Restriction/closure candidates always return `restriction_not_confirmed`. Outcomes: `defect_created`, `already_confirmed`, `duplicate_image_not_counted`, `needs_location`, `needs_severity`, `restriction_not_confirmed`, `not_actionable`, `unknown_observation`.
* `GET /evidence/status` never exposes credentials; `configured=false` means `POST /evidence/analyze` will answer 503.
* `GET /vehicles/{id}/restriction-check` uses the same per-restriction logic as the routing engine (pinned by a consistency test). `unknown_spec` means the vehicle's value is unknown, so clearance cannot be confirmed.

### Why both `POST /routes` and `POST /routes/investigate` exist

They are not duplicates created to avoid fixing the frontend. The frontend **was** corrected to call `/routes/investigate`. `POST /routes` is the original RouteWise contract (`originId`, `destinationId`, inline `vehicle` → list of alternatives) used by the original RouteWise client in the same repository, so removing or reshaping it would break a real consumer. It shares the same engine (`routing.compute_routes`). The Route Autopsy frontend does not call it.

## 3. Models

#### `AutopsyAnalyzeRequest`

| Field | Type | Required | Notes |
|---|---|---|---|
| `origin` | string (minLen 1, maxLen 200) | yes |  |
| `destination` | string (minLen 1, maxLen 200) | yes |  |
| `vehicleId` | string (maxLen 200) \| null | no |  |
| `avoidSevereDefects` | boolean | no |  default `True` |
| `preferBetterSurfaces` | boolean | no |  default `True` |
| `maxAlternatives` | integer (≥ 1.0, ≤ 10.0) | no |  default `5` |
| `includeDefaultSuite` | boolean | no |  default `True` |
| `perturbations` | array of `ResolveDefect` \| `VerifyRestriction` \| `RemoveRestriction` \| `SetVehicleHeight` \| `SetVehicleWidth` \| `SetVehicleWeight` \| `CloseSegment` \| `SetEvidenceVerification` | no |  |

#### `AutopsyBaseline`

| Field | Type | Required | Notes |
|---|---|---|---|
| `route` | `RouteInvestigationResponse` | yes |  |
| `recommendedRouteId` | string \| null | yes |  |
| `suitabilityStatus` | enum(`suitable`, `warning`, `not_validated`, `unsuitable`) \| null | yes |  |
| `durationMin` | number \| null | yes |  |
| `hazardPenaltySeconds` | integer \| null | yes |  |
| `restrictionWarnings` | array of `RouteWarningOut` | yes |  |
| `missingVehicleSpecs` | array of string | yes |  |
| `unverifiedEvidence` | `UnverifiedEvidence` | yes |  |

#### `AutopsyResponse`

| Field | Type | Required | Notes |
|---|---|---|---|
| `analysisId` | string | yes |  |
| `generatedAt` | string | yes |  |
| `persisted` | `False` | no |  default `False` |
| `baseline` | `AutopsyBaseline` | yes |  |
| `baselineRecommendation` | `RecommendationSummary` \| null | yes |  |
| `scenarios` | array of `ScenarioResult` | yes |  |
| `sensitivity` | `SensitivitySummary` | yes |  |
| `suite` | object | yes |  |
| `explanation` | string | yes |  |
| `disclaimer` | string | yes |  |

#### `AutopsyScenarioRequest`

| Field | Type | Required | Notes |
|---|---|---|---|
| `origin` | string (minLen 1, maxLen 200) | yes |  |
| `destination` | string (minLen 1, maxLen 200) | yes |  |
| `vehicleId` | string (maxLen 200) \| null | no |  |
| `avoidSevereDefects` | boolean | no |  default `True` |
| `preferBetterSurfaces` | boolean | no |  default `True` |
| `maxAlternatives` | integer (≥ 1.0, ≤ 10.0) | no |  default `5` |
| `perturbations` | array of `ResolveDefect` \| `VerifyRestriction` \| `RemoveRestriction` \| `SetVehicleHeight` \| `SetVehicleWidth` \| `SetVehicleWeight` \| `CloseSegment` \| `SetEvidenceVerification` | yes |  |

#### `BaselineRouteUnderScenario`

| Field | Type | Required | Notes |
|---|---|---|---|
| `routeId` | string | yes |  |
| `statusBefore` | enum(`suitable`, `warning`, `not_validated`, `unsuitable`) | yes |  |
| `statusAfter` | enum(`suitable`, `warning`, `not_validated`, `unsuitable`) | yes |  |
| `durationSecondsBefore` | integer | yes |  |
| `durationSecondsAfter` | integer | yes |  |

#### `Body_evidence_analyze_evidence_analyze_post`

| Field | Type | Required | Notes |
|---|---|---|---|
| `file` | string | yes |  |
| `notes` | string (maxLen 3000) \| null | no |  |
| `latitude` | number (≥ -90.0, ≤ 90.0) \| null | no |  |
| `longitude` | number (≥ -180.0, ≤ 180.0) \| null | no |  |

#### `ChangedVariable`

| Field | Type | Required | Notes |
|---|---|---|---|
| `variable` | string | yes |  |
| `from` | string \| number \| integer \| null | no |  |
| `to` | string \| number \| integer \| null | no |  |

#### `ChangedWarnings`

| Field | Type | Required | Notes |
|---|---|---|---|
| `added` | array of string | yes |  |
| `removed` | array of string | yes |  |

#### `CloseSegment`

| Field | Type | Required | Notes |
|---|---|---|---|
| `weight` | number (> 0.0, ≤ 10.0) \| null | no | Optional override of this perturbation's weight in the sensitivity score. |
| `type` | `"close_segment"` | yes |  |
| `segmentId` | string | yes |  |

#### `EvidenceAnalyzeResponse`

| Field | Type | Required | Notes |
|---|---|---|---|
| `evidenceId` | string | yes |  |
| `createdAt` | string | yes |  |
| `modelProvider` | string | yes |  |
| `model` | string | yes |  |
| `location` | `EvidenceLocation` | yes |  |
| `imageQuality` | string \| null | no |  |
| `observations` | array of `EvidenceObservation` | yes |  |
| `warnings` | array of string | no |  |
| `duplicateOf` | string \| null | no |  |
| `modelExtras` | object | no |  |
| `disclaimer` | string | yes |  |

#### `EvidenceConfirmItem`

| Field | Type | Required | Notes |
|---|---|---|---|
| `observationId` | string | yes |  |
| `outcome` | enum(`defect_created`, `already_confirmed`, `duplicate_image_not_counted`, `needs_location`, `needs_severity`, `restriction_not_confirmed`, `not_actionable`, `unknown_observation`) | yes |  |
| `defectId` | string \| null | no |  |
| `verificationStatus` | enum(`unverified`, `not_applicable`) | no |  default `not_applicable` |
| `message` | string | yes |  |

#### `EvidenceConfirmRequest`

| Field | Type | Required | Notes |
|---|---|---|---|
| `evidenceId` | string (minLen 1, maxLen 100) | yes |  |
| `confirmedObservationIds` | array of string | yes |  |
| `latitude` | number (≥ -90.0, ≤ 90.0) \| null | no |  |
| `longitude` | number (≥ -180.0, ≤ 180.0) \| null | no |  |
| `severityOverrides` | map of integer | no |  |
| `notes` | string (maxLen 3000) \| null | no |  |

#### `EvidenceConfirmResponse`

| Field | Type | Required | Notes |
|---|---|---|---|
| `evidenceId` | string | yes |  |
| `status` | string | yes |  |
| `results` | array of `EvidenceConfirmItem` | yes |  |
| `disclaimer` | string | yes |  |

#### `EvidenceLocation`

| Field | Type | Required | Notes |
|---|---|---|---|
| `status` | enum(`unknown`, `user_provided`) | yes |  |
| `latitude` | number \| null | no |  |
| `longitude` | number \| null | no |  |
| `note` | string | yes |  |

#### `EvidenceObservation`

A CANDIDATE observation produced by a vision model. Always unverified.

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes |  |
| `observationType` | enum(`pothole`, `cracked_road`, `damaged_edge`, `standing_water`, `road_obstruction`, `restriction_sign`, `road_closure`, `other`) | yes |  |
| `candidateCategory` | enum(`defect`, `restriction_candidate`, `closure_candidate`, `unknown`) | yes |  |
| `suggestedDefectType` | enum(`pothole`, `damaged_surface`, `cracked_road`, `waterlogging`, `damaged_edge`, `obstruction`, `clearance_issue`, `other`) \| null | no |  |
| `description` | string (maxLen 1000) | yes |  |
| `severityEstimate` | integer (≥ 1.0, ≤ 5.0) \| null | no |  |
| `visualConfidence` | number (≥ 0.0, ≤ 1.0) | yes | Model's self-reported visual confidence. NOT verification. |
| `observedAttributes` | object | no |  |
| `unknownAttributes` | array of string | no |  |
| `verificationStatus` | `"unverified"` | no |  default `unverified` |
| `requiresAuthorizedVerification` | boolean | no |  default `False` |
| `source` | `"image_upload"` | no |  default `image_upload` |
| `modelProvider` | string | yes |  |
| `model` | string | yes |  |
| `observedAt` | string | yes |  |
| `modelExtras` | object | no | Unrecognised fields returned by the model, preserved verbatim. |
| `discardedModelFields` | array of string | no | Fields the model returned that the backend refuses to accept (e.g. coordinates, clearance). |

#### `EvidenceStatus`

| Field | Type | Required | Notes |
|---|---|---|---|
| `configured` | boolean | yes |  |
| `provider` | string | yes |  |
| `supportedProvider` | boolean | yes |  |
| `model` | string \| null | no |  |
| `maxUploadBytes` | integer | yes |  |
| `acceptedTypes` | array of string | yes |  |
| `message` | string | yes |  |

#### `RecommendationSummary`

| Field | Type | Required | Notes |
|---|---|---|---|
| `routeId` | string | yes |  |
| `via` | array of string | yes |  |
| `segmentIds` | array of string | yes |  |
| `durationMin` | number | yes |  |
| `suitabilityStatus` | enum(`suitable`, `warning`, `not_validated`, `unsuitable`) | yes |  |

#### `RemoveRestriction`

| Field | Type | Required | Notes |
|---|---|---|---|
| `weight` | number (> 0.0, ≤ 10.0) \| null | no | Optional override of this perturbation's weight in the sensitivity score. |
| `type` | `"remove_restriction"` | yes |  |
| `restrictionId` | string | yes |  |

#### `ResolveDefect`

| Field | Type | Required | Notes |
|---|---|---|---|
| `weight` | number (> 0.0, ≤ 10.0) \| null | no | Optional override of this perturbation's weight in the sensitivity score. |
| `type` | `"resolve_defect"` | yes |  |
| `defectId` | string | yes |  |

#### `RestrictionCheckItem`

| Field | Type | Required | Notes |
|---|---|---|---|
| `restrictionId` | string | yes |  |
| `roadSegmentId` | string | yes |  |
| `segmentName` | string | yes |  |
| `restrictionType` | string | yes |  |
| `description` | string | no |  default `` |
| `limitValue` | number \| null | no |  |
| `unit` | string \| null | no |  |
| `verificationStatus` | string | yes |  |
| `appliesToVehicle` | boolean | yes |  |
| `vehicleValue` | number \| null | no |  |
| `outcome` | enum(`blocks`, `may_block`, `unknown_spec`, `fits`, `not_applicable`) | yes |  |
| `message` | string | yes |  |

#### `RouteAlternativeOut`

| Field | Type | Required | Notes |
|---|---|---|---|
| `routeId` | string | yes |  |
| `label` | string | yes |  |
| `segmentIds` | array of string | yes |  |
| `segments` | array of `RouteSegmentOut` | yes |  |
| `distanceKm` | number | yes |  |
| `durationMin` | number | yes |  |
| `suitabilityStatus` | enum(`suitable`, `warning`, `not_validated`, `unsuitable`) | yes |  |
| `recommended` | boolean | yes |  |
| `isFastestCandidate` | boolean | yes |  |
| `rank` | integer | yes |  |
| `scoreSeconds` | integer | yes |  |
| `scoreBreakdown` | map of integer | yes |  |
| `severeHazardCount` | integer | yes |  |
| `warnings` | array of `RouteWarningOut` | yes |  |
| `missingData` | array of string | yes |  |
| `rejectionReasons` | array of string | yes |  |
| `explanation` | string | yes |  |
| `geometry` | array of array of number | yes |  |

#### `RouteInvestigationRequest`

Frontend route request. `origin`/`destination` accept a pilot node id (e.g. 'FKC')

| Field | Type | Required | Notes |
|---|---|---|---|
| `origin` | string (minLen 1, maxLen 200) | yes |  |
| `destination` | string (minLen 1, maxLen 200) | yes |  |
| `vehicleId` | string (maxLen 200) \| null | no |  |
| `avoidSevereDefects` | boolean | no |  default `True` |
| `preferBetterSurfaces` | boolean | no |  default `True` |
| `maxAlternatives` | integer (≥ 1.0, ≤ 10.0) | no |  default `5` |

#### `RouteInvestigationResponse`

| Field | Type | Required | Notes |
|---|---|---|---|
| `routeId` | string | yes |  |
| `origin` | string | yes |  |
| `destination` | string | yes |  |
| `originId` | string | yes |  |
| `destinationId` | string | yes |  |
| `distanceKm` | number | yes |  |
| `durationMin` | number | yes |  |
| `segments` | array of `RouteSegmentOut` | yes |  |
| `vehicle` | `VehicleDisplay` \| null | no |  |
| `suitabilityStatus` | enum(`suitable`, `warning`, `not_validated`, `unsuitable`) | yes |  |
| `recommended` | boolean | yes |  |
| `recommendationStatus` | enum(`recommended`, `no_usable_route`) | yes |  |
| `explanation` | string | yes |  |
| `warnings` | array of `RouteWarningOut` | yes |  |
| `missingData` | array of string | yes |  |
| `alternatives` | array of `RouteAlternativeOut` | yes |  |
| `search` | `RouteSearchInfo` | yes |  |
| `disclaimer` | string | yes |  |

#### `RouteSearchInfo`

| Field | Type | Required | Notes |
|---|---|---|---|
| `candidatesEnumerated` | integer | yes |  |
| `candidatesEvaluated` | integer | yes |  |
| `truncated` | boolean | yes |  |
| `maxDepth` | integer | yes |  |
| `maxCandidates` | integer | yes |  |
| `statusCounts` | map of integer | yes |  |
| `alternativesReturned` | integer | yes |  |

#### `RouteSegmentOut`

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes |  |
| `name` | string | yes |  |
| `distanceKm` | number | yes |  |
| `riskLevel` | enum(`low`, `medium`, `high`) | yes |  |
| `note` | string \| null | no |  |

#### `RouteWarningOut`

| Field | Type | Required | Notes |
|---|---|---|---|
| `level` | string | yes |  |
| `message` | string | yes |  |
| `segmentId` | string \| null | no |  |
| `restrictionId` | string \| null | no |  |
| `defectId` | string \| null | no |  |

#### `RunnerUp`

| Field | Type | Required | Notes |
|---|---|---|---|
| `routeId` | string | yes |  |
| `segmentIds` | array of string | yes |  |
| `suitabilityStatus` | enum(`suitable`, `warning`, `not_validated`, `unsuitable`) | yes |  |
| `scoreSeconds` | integer | yes |  |

#### `ScenarioComparison`

Before/after metrics for the baseline recommendation vs the scenario's recommendation

| Field | Type | Required | Notes |
|---|---|---|---|
| `routeIdBefore` | string \| null | yes |  |
| `routeIdAfter` | string \| null | yes |  |
| `durationMinBefore` | number \| null | yes |  |
| `durationMinAfter` | number \| null | yes |  |
| `distanceKmBefore` | number \| null | yes |  |
| `distanceKmAfter` | number \| null | yes |  |
| `suitabilityBefore` | enum(`suitable`, `warning`, `not_validated`, `unsuitable`) \| null | yes |  |
| `suitabilityAfter` | enum(`suitable`, `warning`, `not_validated`, `unsuitable`) \| null | yes |  |
| `severeHazardsBefore` | integer \| null | yes |  |
| `severeHazardsAfter` | integer \| null | yes |  |
| `scoreSecondsBefore` | integer \| null | yes |  |
| `scoreSecondsAfter` | integer \| null | yes |  |
| `segmentsRemoved` | array of string | yes |  |
| `segmentsAdded` | array of string | yes |  |
| `segmentsShared` | array of string | yes |  |
| `baselineRunnerUp` | `RunnerUp` \| null | yes |  |
| `revisedRunnerUp` | `RunnerUp` \| null | yes |  |
| `baselineMarginSeconds` | integer \| null | yes | Score lead of the recommended route over the best other usable candidate (baseline). |
| `revisedMarginSeconds` | integer \| null | yes |  |

#### `ScenarioResult`

| Field | Type | Required | Notes |
|---|---|---|---|
| `scenarioId` | string | yes |  |
| `perturbation` | object | yes |  |
| `description` | string | yes |  |
| `weight` | number | yes |  |
| `inputChanged` | boolean | yes |  |
| `changed` | boolean | yes |  |
| `skipped` | boolean | no |  default `False` |
| `baselineRecommendation` | `RecommendationSummary` \| null | yes |  |
| `revisedRecommendation` | `RecommendationSummary` \| null | yes |  |
| `deltaDurationMin` | number \| null | yes |  |
| `changedVariables` | array of `ChangedVariable` | yes |  |
| `changedWarnings` | `ChangedWarnings` | yes |  |
| `baselineRouteUnderScenario` | `BaselineRouteUnderScenario` \| null | yes |  |
| `comparison` | `ScenarioComparison` \| null | no |  |
| `revisedRoute` | `RouteAlternativeOut` \| null | no | Full detail (segments, geometry, warnings) of the revised recommendation; present only when it differs from the baseline recommendation. |
| `explanation` | string | yes |  |
| `notes` | array of string | no |  |

#### `SensitivitySummary`

| Field | Type | Required | Notes |
|---|---|---|---|
| `scenariosTested` | integer | yes |  |
| `scenariosChanged` | integer | yes |  |
| `scenariosSkipped` | integer | yes |  |
| `sensitivityScore` | number \| null | yes |  |
| `totalWeight` | number | yes |  |
| `changedWeight` | number | yes |  |
| `changedScenarioIds` | array of string | yes |  |
| `formula` | string | yes |  |
| `interpretation` | string | yes |  |

#### `SetEvidenceVerification`

| Field | Type | Required | Notes |
|---|---|---|---|
| `weight` | number (> 0.0, ≤ 10.0) \| null | no | Optional override of this perturbation's weight in the sensitivity score. |
| `type` | `"set_evidence_verification"` | yes |  |
| `targetKind` | enum(`defect`, `restriction`) | yes |  |
| `targetId` | string | yes |  |
| `status` | enum(`verified`, `unverified`) | yes |  |

#### `SetVehicleHeight`

| Field | Type | Required | Notes |
|---|---|---|---|
| `weight` | number (> 0.0, ≤ 10.0) \| null | no | Optional override of this perturbation's weight in the sensitivity score. |
| `type` | `"set_vehicle_height"` | yes |  |
| `heightM` | number (> 0.0, ≤ 10.0) | yes |  |

#### `SetVehicleWeight`

| Field | Type | Required | Notes |
|---|---|---|---|
| `weight` | number (> 0.0, ≤ 10.0) \| null | no | Optional override of this perturbation's weight in the sensitivity score. |
| `type` | `"set_vehicle_weight"` | yes |  |
| `weightKg` | number (> 0.0, ≤ 100000.0) | yes |  |

#### `SetVehicleWidth`

| Field | Type | Required | Notes |
|---|---|---|---|
| `weight` | number (> 0.0, ≤ 10.0) \| null | no | Optional override of this perturbation's weight in the sensitivity score. |
| `type` | `"set_vehicle_width"` | yes |  |
| `widthM` | number (> 0.0, ≤ 5.0) | yes |  |

#### `UnverifiedEvidence`

| Field | Type | Required | Notes |
|---|---|---|---|
| `defects` | array of object | yes |  |
| `restrictions` | array of object | yes |  |

#### `VehicleDisplay`

Frontend-facing view of a stored VehicleProfile. Nothing is dropped: all

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes |  |
| `name` | string | yes |  |
| `type` | string | yes |  |
| `category` | enum(`small_car`, `sedan`, `suv`, `van`, `lcv`, `heavy_truck`, `bus`, `motorcycle`, `other`) | no |  default `other` |
| `make` | string | yes |  |
| `model` | string | yes |  |
| `year` | integer \| null | no |  |
| `variant` | string | no |  default `` |
| `lengthM` | number \| null | no |  |
| `widthM` | number \| null | no |  |
| `heightM` | number \| null | no |  |
| `grossVehicleWeightKg` | number \| null | no |  |
| `currentLoadedWeightKg` | number \| null | no |  |
| `specStatus` | map of enum(`verified`, `user_confirmed`, `estimated`, `unknown`) | no |  |
| `verificationStatus` | enum(`verified`, `user_confirmed`, `estimated`, `unknown`) | no |  default `unknown` |
| `unknownSpecs` | array of string | no |  |
| `sources` | array of string | no |  |
| `isIllustrative` | boolean | no |  default `False` |
| `notes` | string \| null | no |  |
| `updatedAt` | string \| null | no |  |
| `lastVerifiedAt` | string \| null | no |  |

#### `VehicleRestrictionCheck`

| Field | Type | Required | Notes |
|---|---|---|---|
| `vehicleId` | string | yes |  |
| `vehicleName` | string | yes |  |
| `unknownSpecs` | array of string | yes |  |
| `summary` | map of integer | yes |  |
| `items` | array of `RestrictionCheckItem` | yes |  |
| `disclaimer` | string | yes |  |

#### `VerifyRestriction`

| Field | Type | Required | Notes |
|---|---|---|---|
| `weight` | number (> 0.0, ≤ 10.0) \| null | no | Optional override of this perturbation's weight in the sensitivity score. |
| `type` | `"verify_restriction"` | yes |  |
| `restrictionId` | string | yes |  |

## 4. Untyped legacy responses (shapes verified by tests, not by OpenAPI)

* `GET /api/meta` → `{demoMode, pilotArea, warning, nodes:[{id,name,position:[lat,lon]}], segments:[{id,name,area,from,to,widthM,surface,restrictionDataComplete,geometry:[[lat,lon],…]}]}` (illustrative Kochi graph)
* `GET /restrictions` → list of restrictions `{id, roadSegmentId, restrictionType, limitValue, unit, appliesTo: "all" | [category], description, source, verificationStatus, lastVerifiedAt}`
* `GET /defects` → list of defect records `{id, defectType, latitude, longitude, severity 1-5, description, observedAt, roadSegmentId, reportedAt, verificationStatus, maintenanceStatus, independentReportCount, isUserSubmitted, …provenance fields for evidence-created defects}`
* `GET /defects/{defect_id}` → one defect record (same shape as a `/defects` item)

## 5. Other backend endpoints (not used by this frontend)

| Method | Path | Summary |
|---|---|---|
| GET | `/` | Root |
| GET | `/admin/defects` | Admin Defects |
| POST | `/admin/inspections` | Create Inspection |
| GET | `/admin/priority-segments` | Priority Segments |
| POST | `/admin/repairs` | Create Repair |
| GET | `/api/health` | Health |
| GET | `/autopsy/health` | Autopsy Health |
| POST | `/defects` | Create Defect |
| POST | `/defects/{defect_id}/confirm` | Confirm Defect |
| POST | `/defects/{defect_id}/resolve` | Resolve Defect |
| PATCH | `/defects/{defect_id}/status` | Update Defect Status |
| GET | `/evidence/{evidence_id}` | Retrieve a stored analysis (no image data) |
| GET | `/health` | Health |
| GET | `/maintenance/summary` | Maintenance Summary |
| GET | `/roads/nearby` | Nearby Roads |
| GET | `/roads/{segment_id}` | Get Road |
| POST | `/routes` | Calculate Routes |
| PUT | `/vehicles` | Save Vehicle |
| POST | `/vehicles/lookup` | Lookup Vehicles |
| DELETE | `/vehicles/{vehicle_id}` | Delete Vehicle |
| GET | `/vehicles/{vehicle_id}` | Get Vehicle |
