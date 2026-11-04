from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict

VehicleCategory = Literal["small_car", "sedan", "suv", "van", "lcv", "heavy_truck", "bus", "motorcycle", "other"]
SpecStatus = Literal["verified", "user_confirmed", "estimated", "unknown"]
DefectType = Literal["pothole", "damaged_surface", "cracked_road", "waterlogging", "damaged_edge", "obstruction", "clearance_issue", "other"]
MaintenanceStatus = Literal["open", "under_review", "inspected", "resolved"]
VerificationStatus = Literal["verified", "unverified"]

class VehicleProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    make: str
    model: str
    year: int | None = None
    variant: str = ""
    category: VehicleCategory = "other"
    lengthM: float | None = None
    widthM: float | None = None
    heightM: float | None = None
    grossVehicleWeightKg: float | None = None
    currentLoadedWeightKg: float | None = None
    specStatus: dict[str, SpecStatus] = Field(default_factory=dict)
    verificationStatus: SpecStatus = "unknown"
    sources: list[str] = Field(default_factory=list)
    isIllustrative: bool = False
    updatedAt: str | None = None
    lastVerifiedAt: str | None = None

class VehicleLookupQuery(BaseModel):
    make: str | None = None
    model: str | None = None
    year: int | None = None
    variant: str | None = None
    category: VehicleCategory | Literal[""] | None = None

class NewDefectInput(BaseModel):
    defectType: DefectType
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    severity: int = Field(ge=1, le=5)
    description: str = Field(default="", max_length=3000)
    photoUrl: str | None = None
    observedAt: str

class DefectStatusUpdate(BaseModel):
    status: MaintenanceStatus

class RouteRequest(BaseModel):
    originId: str
    destinationId: str
    vehicle: VehicleProfile | None = None
    avoidSevereDefects: bool = True
    preferBetterSurfaces: bool = True

class StatusUpdate(BaseModel):
    status: MaintenanceStatus

class InspectionInput(BaseModel):
    defectId: str
    inspectorId: str | None = None
    observedCondition: str
    notes: str = ""
    inspectedAt: str | None = None

class RepairInput(BaseModel):
    defectId: str
    status: str = "planned"
    contractor: str | None = None
    startedAt: str | None = None
    completedAt: str | None = None
    verificationEvidence: str | None = None


# =====================================================================
# Route Autopsy additions (existing models above are unchanged)
# =====================================================================
from typing import Annotated, Union  # noqa: E402
from pydantic import AliasChoices  # noqa: E402

RiskLevel = Literal["low", "medium", "high"]
SuitabilityStatus = Literal["suitable", "warning", "not_validated", "unsuitable"]


class VehicleDisplay(BaseModel):
    """Frontend-facing view of a stored VehicleProfile. Nothing is dropped: all
    dimensions, weights and verification metadata are carried through, and
    unknown specifications stay null."""
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    type: str
    category: VehicleCategory = "other"
    make: str
    model: str
    year: int | None = None
    variant: str = ""
    lengthM: float | None = None
    widthM: float | None = None
    heightM: float | None = None
    grossVehicleWeightKg: float | None = None
    currentLoadedWeightKg: float | None = None
    specStatus: dict[str, SpecStatus] = Field(default_factory=dict)
    verificationStatus: SpecStatus = "unknown"
    unknownSpecs: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    isIllustrative: bool = False
    notes: str | None = None
    updatedAt: str | None = None
    lastVerifiedAt: str | None = None


class RouteInvestigationRequest(BaseModel):
    """Frontend route request. `origin`/`destination` accept a pilot node id (e.g. 'FKC')
    or exact node name; the legacy field names originId/destinationId are accepted too."""
    model_config = ConfigDict(populate_by_name=True)
    origin: str = Field(min_length=1, max_length=200, validation_alias=AliasChoices("origin", "originId"))
    destination: str = Field(min_length=1, max_length=200, validation_alias=AliasChoices("destination", "destinationId"))
    vehicleId: str | None = Field(default=None, max_length=200)
    avoidSevereDefects: bool = True
    preferBetterSurfaces: bool = True
    maxAlternatives: int = Field(default=5, ge=1, le=10)


class RouteSegmentOut(BaseModel):
    id: str
    name: str
    distanceKm: float
    riskLevel: RiskLevel
    note: str | None = None


class RouteWarningOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    level: str
    message: str
    segmentId: str | None = None
    restrictionId: str | None = None
    defectId: str | None = None


class RouteSearchInfo(BaseModel):
    candidatesEnumerated: int
    candidatesEvaluated: int
    truncated: bool
    maxDepth: int
    maxCandidates: int
    statusCounts: dict[str, int]
    alternativesReturned: int


class RouteAlternativeOut(BaseModel):
    routeId: str
    label: str
    segmentIds: list[str]
    segments: list[RouteSegmentOut]
    distanceKm: float
    durationMin: float
    suitabilityStatus: SuitabilityStatus
    recommended: bool
    isFastestCandidate: bool
    rank: int
    scoreSeconds: int
    scoreBreakdown: dict[str, int]
    severeHazardCount: int
    warnings: list[RouteWarningOut]
    missingData: list[str]
    rejectionReasons: list[str]
    explanation: str
    geometry: list[list[float]]


class RouteInvestigationResponse(BaseModel):
    routeId: str
    origin: str
    destination: str
    originId: str
    destinationId: str
    distanceKm: float
    durationMin: float
    segments: list[RouteSegmentOut]
    vehicle: VehicleDisplay | None = None
    suitabilityStatus: SuitabilityStatus
    recommended: bool
    recommendationStatus: Literal["recommended", "no_usable_route"]
    explanation: str
    warnings: list[RouteWarningOut]
    missingData: list[str]
    alternatives: list[RouteAlternativeOut]
    search: RouteSearchInfo
    disclaimer: str


# ---- Route Autopsy: hypothetical perturbations (never persisted) ----

class _PerturbationBase(BaseModel):
    weight: float | None = Field(default=None, gt=0, le=10, description="Optional override of this perturbation's weight in the sensitivity score.")


class ResolveDefect(_PerturbationBase):
    type: Literal["resolve_defect"]
    defectId: str


class VerifyRestriction(_PerturbationBase):
    type: Literal["verify_restriction"]
    restrictionId: str


class RemoveRestriction(_PerturbationBase):
    type: Literal["remove_restriction"]
    restrictionId: str


class SetVehicleHeight(_PerturbationBase):
    type: Literal["set_vehicle_height"]
    heightM: float = Field(gt=0, le=10)


class SetVehicleWidth(_PerturbationBase):
    type: Literal["set_vehicle_width"]
    widthM: float = Field(gt=0, le=5)


class SetVehicleWeight(_PerturbationBase):
    type: Literal["set_vehicle_weight"]
    weightKg: float = Field(gt=0, le=100000)


class CloseSegment(_PerturbationBase):
    type: Literal["close_segment"]
    segmentId: str


class SetEvidenceVerification(_PerturbationBase):
    type: Literal["set_evidence_verification"]
    targetKind: Literal["defect", "restriction"]
    targetId: str
    status: Literal["verified", "unverified"]


Perturbation = Annotated[
    Union[ResolveDefect, VerifyRestriction, RemoveRestriction, SetVehicleHeight, SetVehicleWidth, SetVehicleWeight, CloseSegment, SetEvidenceVerification],
    Field(discriminator="type"),
]


class AutopsyAnalyzeRequest(RouteInvestigationRequest):
    includeDefaultSuite: bool = True
    perturbations: list[Perturbation] = Field(default_factory=list, max_length=25)


class AutopsyScenarioRequest(RouteInvestigationRequest):
    perturbations: list[Perturbation] = Field(min_length=1, max_length=25)


class RecommendationSummary(BaseModel):
    routeId: str
    via: list[str]
    segmentIds: list[str]
    durationMin: float
    suitabilityStatus: SuitabilityStatus


class ChangedVariable(BaseModel):
    variable: str
    from_: str | float | int | None = Field(default=None, serialization_alias="from", validation_alias=AliasChoices("from_", "from"))
    to: str | float | int | None = None
    model_config = ConfigDict(populate_by_name=True)


class ChangedWarnings(BaseModel):
    added: list[str]
    removed: list[str]


class BaselineRouteUnderScenario(BaseModel):
    routeId: str
    statusBefore: SuitabilityStatus
    statusAfter: SuitabilityStatus
    durationSecondsBefore: int
    durationSecondsAfter: int


class RunnerUp(BaseModel):
    routeId: str
    segmentIds: list[str]
    suitabilityStatus: SuitabilityStatus
    scoreSeconds: int


class ScenarioComparison(BaseModel):
    """Before/after metrics for the baseline recommendation vs the scenario's recommendation
    (same route compared under changed evidence when the recommendation is stable)."""
    routeIdBefore: str | None
    routeIdAfter: str | None
    durationMinBefore: float | None
    durationMinAfter: float | None
    distanceKmBefore: float | None
    distanceKmAfter: float | None
    suitabilityBefore: SuitabilityStatus | None
    suitabilityAfter: SuitabilityStatus | None
    severeHazardsBefore: int | None
    severeHazardsAfter: int | None
    scoreSecondsBefore: int | None
    scoreSecondsAfter: int | None
    segmentsRemoved: list[str]
    segmentsAdded: list[str]
    segmentsShared: list[str]
    baselineRunnerUp: RunnerUp | None
    revisedRunnerUp: RunnerUp | None
    baselineMarginSeconds: int | None = Field(description="Score lead of the recommended route over the best other usable candidate (baseline).")
    revisedMarginSeconds: int | None


class ScenarioResult(BaseModel):
    scenarioId: str
    perturbation: dict[str, Any]
    description: str
    weight: float
    inputChanged: bool
    changed: bool
    skipped: bool = False
    baselineRecommendation: RecommendationSummary | None
    revisedRecommendation: RecommendationSummary | None
    deltaDurationMin: float | None
    changedVariables: list[ChangedVariable]
    changedWarnings: ChangedWarnings
    baselineRouteUnderScenario: BaselineRouteUnderScenario | None
    comparison: ScenarioComparison | None = None
    revisedRoute: RouteAlternativeOut | None = Field(default=None, description="Full detail (segments, geometry, warnings) of the revised recommendation; present only when it differs from the baseline recommendation.")
    explanation: str
    notes: list[str] = Field(default_factory=list)


class SensitivitySummary(BaseModel):
    scenariosTested: int
    scenariosChanged: int
    scenariosSkipped: int
    sensitivityScore: float | None
    totalWeight: float
    changedWeight: float
    changedScenarioIds: list[str]
    formula: str
    interpretation: str


class UnverifiedEvidence(BaseModel):
    defects: list[dict[str, Any]]
    restrictions: list[dict[str, Any]]


class AutopsyBaseline(BaseModel):
    route: RouteInvestigationResponse
    recommendedRouteId: str | None
    suitabilityStatus: SuitabilityStatus | None
    durationMin: float | None
    hazardPenaltySeconds: int | None
    restrictionWarnings: list[RouteWarningOut]
    missingVehicleSpecs: list[str]
    unverifiedEvidence: UnverifiedEvidence


class AutopsyResponse(BaseModel):
    analysisId: str
    generatedAt: str
    persisted: Literal[False] = False
    baseline: AutopsyBaseline
    baselineRecommendation: RecommendationSummary | None
    scenarios: list[ScenarioResult]
    sensitivity: SensitivitySummary
    suite: dict[str, Any]
    explanation: str
    disclaimer: str


# ---- Evidence (Meta multimodal) ----

ObservationType = Literal["pothole", "cracked_road", "damaged_edge", "standing_water", "road_obstruction", "restriction_sign", "road_closure", "other"]
CandidateCategory = Literal["defect", "restriction_candidate", "closure_candidate", "unknown"]


class EvidenceObservation(BaseModel):
    """A CANDIDATE observation produced by a vision model. Always unverified."""
    id: str
    observationType: ObservationType
    candidateCategory: CandidateCategory
    suggestedDefectType: DefectType | None = None
    description: str = Field(max_length=1000)
    severityEstimate: int | None = Field(default=None, ge=1, le=5)
    visualConfidence: float = Field(ge=0, le=1, description="Model's self-reported visual confidence. NOT verification.")
    observedAttributes: dict[str, Any] = Field(default_factory=dict)
    unknownAttributes: list[str] = Field(default_factory=list)
    verificationStatus: Literal["unverified"] = "unverified"
    requiresAuthorizedVerification: bool = False
    source: Literal["image_upload"] = "image_upload"
    modelProvider: str
    model: str
    observedAt: str
    modelExtras: dict[str, Any] = Field(default_factory=dict, description="Unrecognised fields returned by the model, preserved verbatim.")
    discardedModelFields: list[str] = Field(default_factory=list, description="Fields the model returned that the backend refuses to accept (e.g. coordinates, clearance).")


class EvidenceLocation(BaseModel):
    status: Literal["unknown", "user_provided"]
    latitude: float | None = None
    longitude: float | None = None
    note: str


class EvidenceAnalyzeResponse(BaseModel):
    evidenceId: str
    createdAt: str
    modelProvider: str
    model: str
    location: EvidenceLocation
    imageQuality: str | None = None
    observations: list[EvidenceObservation]
    warnings: list[str] = Field(default_factory=list)
    duplicateOf: str | None = None
    modelExtras: dict[str, Any] = Field(default_factory=dict)
    disclaimer: str


class EvidenceConfirmRequest(BaseModel):
    evidenceId: str = Field(min_length=1, max_length=100)
    confirmedObservationIds: list[str] = Field(max_length=50)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    severityOverrides: dict[str, int] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=3000)


class EvidenceConfirmItem(BaseModel):
    observationId: str
    outcome: Literal["defect_created", "already_confirmed", "duplicate_image_not_counted", "needs_location", "needs_severity", "restriction_not_confirmed", "not_actionable", "unknown_observation"]
    defectId: str | None = None
    verificationStatus: Literal["unverified", "not_applicable"] = "not_applicable"
    message: str


class EvidenceConfirmResponse(BaseModel):
    evidenceId: str
    status: str
    results: list[EvidenceConfirmItem]
    disclaimer: str


# ---- Evidence status / vehicle restriction check ----

class EvidenceStatus(BaseModel):
    configured: bool
    provider: str
    supportedProvider: bool
    model: str | None = None
    maxUploadBytes: int
    acceptedTypes: list[str]
    message: str


class RestrictionCheckItem(BaseModel):
    restrictionId: str
    roadSegmentId: str
    segmentName: str
    restrictionType: str
    description: str = ""
    limitValue: float | None = None
    unit: str | None = None
    verificationStatus: str
    appliesToVehicle: bool
    vehicleValue: float | None = None
    outcome: Literal["blocks", "may_block", "unknown_spec", "fits", "not_applicable"]
    message: str


class VehicleRestrictionCheck(BaseModel):
    vehicleId: str
    vehicleName: str
    unknownSpecs: list[str]
    summary: dict[str, int]
    items: list[RestrictionCheckItem]
    disclaimer: str
