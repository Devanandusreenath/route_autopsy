/**
 * SYNTHETIC DEMO DATA PROVIDER (demo mode only).
 * Hand-written, deterministic sample data so the UI can be explored without a backend.
 * Nothing here is routing-engine output or AI inference, and the UI labels it as synthetic.
 * Only used when apiConfig.mode === "demo"; never as a fallback for backend failures.
 */
import type {
  RouteAlternative,
  RouteRequest,
  RouteResponse,
  RouteSegment,
} from "@/lib/api/types/routes";
import type {
  AutopsyAnalyzeRequest,
  AutopsyAnalyzeResponse,
  AutopsyScenarioRequest,
  AutopsyScenarioResponse,
  ScenarioResult,
} from "@/lib/api/types/autopsy";
import type {
  EvidenceAnalyzeInput,
  EvidenceAnalyzeResponse,
  EvidenceConfirmRequest,
  EvidenceConfirmResponse,
  EvidenceStatus,
} from "@/lib/api/types/evidence";
import type { Vehicle, VehicleRestrictionCheck } from "@/lib/api/types/vehicles";
import type { NetworkResponse } from "@/lib/api/types/network";
import type { Defect } from "@/lib/api/types/defects";
import type { Restriction } from "@/lib/api/types/restrictions";

const delay = (ms = 500) => new Promise((r) => setTimeout(r, ms));
const DISCLAIMER = "Synthetic demo data — not routing-engine output, not AI inference.";

const vehicles: Vehicle[] = [
  {
    id: "demo-v1",
    name: "Demo Van 01",
    type: "Light commercial vehicle",
    category: "lcv",
    make: "Demo",
    model: "Van 01",
    year: null,
    lengthM: 4.2,
    widthM: 1.7,
    heightM: 2.0,
    grossVehicleWeightKg: 2400,
    currentLoadedWeightKg: null,
    specStatus: {
      lengthM: "estimated",
      widthM: "estimated",
      heightM: "estimated",
      grossVehicleWeightKg: "estimated",
      currentLoadedWeightKg: "unknown",
    },
    verificationStatus: "estimated",
    unknownSpecs: [],
    sources: [],
    isIllustrative: true,
    notes: "Synthetic profile",
  },
  {
    id: "demo-v2",
    name: "Demo Truck 07",
    type: "Heavy truck",
    category: "heavy_truck",
    make: "Demo",
    model: "Truck 07",
    year: null,
    lengthM: 8.6,
    widthM: 2.5,
    heightM: null,
    grossVehicleWeightKg: 12000,
    currentLoadedWeightKg: null,
    specStatus: {
      lengthM: "estimated",
      widthM: "estimated",
      heightM: "unknown",
      grossVehicleWeightKg: "estimated",
      currentLoadedWeightKg: "unknown",
    },
    verificationStatus: "unknown",
    unknownSpecs: ["height"],
    sources: [],
    isIllustrative: true,
    notes: "Synthetic profile. Unknown: height.",
  },
];

// A tiny synthetic schematic (not a real place): three nodes in a line with a bypass.
const nodes = [
  { id: "N1", name: "Demo Depot", position: [0.0, 0.0] as [number, number] },
  { id: "N2", name: "Demo Junction", position: [0.0, 0.02] as [number, number] },
  { id: "N3", name: "Demo Market", position: [0.0, 0.04] as [number, number] },
];
const segs = [
  {
    id: "s1",
    name: "Depot Road",
    from: "N1",
    to: "N2",
    surface: "good",
    geometry: [
      [0.0, 0.0],
      [0.0, 0.02],
    ] as [number, number][],
  },
  {
    id: "s2",
    name: "Main Street",
    from: "N2",
    to: "N3",
    surface: "poor",
    geometry: [
      [0.0, 0.02],
      [0.0, 0.04],
    ] as [number, number][],
  },
  {
    id: "s3",
    name: "Bypass North",
    from: "N2",
    to: "N3",
    surface: "fair",
    geometry: [
      [0.0, 0.02],
      [0.012, 0.03],
      [0.0, 0.04],
    ] as [number, number][],
  },
];

const defects: Defect[] = [
  {
    id: "demo-d1",
    defectType: "pothole",
    latitude: 0.0,
    longitude: 0.03,
    severity: 4,
    description: "Synthetic sample defect",
    roadSegmentId: "s2",
    verificationStatus: "unverified",
    maintenanceStatus: "open",
    reportedAt: null,
    observedAt: null,
  },
  {
    id: "demo-d2",
    defectType: "cracked_road",
    latitude: 0.0,
    longitude: 0.01,
    severity: 2,
    description: "Synthetic sample defect",
    roadSegmentId: "s1",
    verificationStatus: "verified",
    maintenanceStatus: "open",
    reportedAt: null,
    observedAt: null,
  },
];

const seg = (
  id: string,
  risk: RouteSegment["riskLevel"],
  note: string | null = null,
): RouteSegment => {
  const s = segs.find((x) => x.id === id)!;
  return { id, name: s.name, distanceKm: 2.2, riskLevel: risk, note };
};
const geom = (ids: string[]) => ids.flatMap((id) => segs.find((s) => s.id === id)!.geometry);

function alt(
  label: string,
  ids: string[],
  recommended: boolean,
  status: RouteAlternative["suitabilityStatus"],
  mins: number,
): RouteAlternative {
  return {
    routeId: `N1-N3-${ids.join("_")}`,
    label,
    segmentIds: ids,
    segments: ids.map((i) =>
      seg(i, i === "s2" ? "high" : "low", i === "s2" ? "Synthetic: sample severe defect" : null),
    ),
    distanceKm: ids.length * 2.2,
    durationMin: mins,
    suitabilityStatus: status,
    recommended,
    isFastestCandidate: label === "Route A",
    rank: recommended ? 1 : 2,
    scoreSeconds: mins * 60 + (ids.includes("s2") ? 600 : 0),
    scoreBreakdown: {
      travelSeconds: mins * 60,
      severeDefectPenaltySeconds: ids.includes("s2") ? 600 : 0,
      surfacePenaltySeconds: 0,
    },
    severeHazardCount: ids.includes("s2") ? 1 : 0,
    warnings: [],
    missingData: [],
    rejectionReasons: [],
    explanation: `Synthetic example explanation for ${label}.`,
    geometry: geom(ids),
  };
}
const A = alt("Route A", ["s1", "s2"], true, "suitable", 9);
const B = alt("Route B", ["s1", "s3"], false, "warning", 12);

function route(req: RouteRequest): RouteResponse {
  return {
    routeId: A.routeId,
    origin: req.origin,
    destination: req.destination,
    originId: "N1",
    destinationId: "N3",
    distanceKm: A.distanceKm,
    durationMin: A.durationMin,
    segments: A.segments,
    vehicle: vehicles.find((v) => v.id === req.vehicleId) ?? null,
    suitabilityStatus: "suitable",
    recommended: true,
    recommendationStatus: "recommended",
    explanation: "Synthetic example: this is not a real recommendation.",
    warnings: [],
    missingData: [],
    alternatives: [A, B],
    search: {
      candidatesEnumerated: 2,
      candidatesEvaluated: 2,
      truncated: false,
      maxDepth: 6,
      maxCandidates: 5000,
      statusCounts: { suitable: 1, warning: 1, not_validated: 0, unsuitable: 0 },
      alternativesReturned: 2,
    },
    disclaimer: DISCLAIMER,
  };
}

const rec = (a: RouteAlternative) => ({
  routeId: a.routeId,
  via: a.segments.map((s) => s.name),
  segmentIds: a.segmentIds,
  durationMin: a.durationMin,
  suitabilityStatus: a.suitabilityStatus,
});

function scenarios(changed: boolean): ScenarioResult[] {
  const common = {
    weight: 1,
    inputChanged: true,
    skipped: false,
    baselineRecommendation: rec(A),
    baselineRouteUnderScenario: null,
    changedWarnings: { added: [], removed: [] },
    notes: [] as string[],
  };
  const cmpStable = {
    routeIdBefore: A.routeId,
    routeIdAfter: A.routeId,
    durationMinBefore: 9,
    durationMinAfter: 9,
    distanceKmBefore: A.distanceKm,
    distanceKmAfter: A.distanceKm,
    suitabilityBefore: "suitable" as const,
    suitabilityAfter: "suitable" as const,
    severeHazardsBefore: 1,
    severeHazardsAfter: 1,
    scoreSecondsBefore: 1140,
    scoreSecondsAfter: 1140,
    segmentsRemoved: [],
    segmentsAdded: [],
    segmentsShared: A.segmentIds,
    baselineRunnerUp: {
      routeId: B.routeId,
      segmentIds: B.segmentIds,
      suitabilityStatus: "warning" as const,
      scoreSeconds: 1500,
    },
    revisedRunnerUp: {
      routeId: B.routeId,
      segmentIds: B.segmentIds,
      suitabilityStatus: "warning" as const,
      scoreSeconds: 1500,
    },
    baselineMarginSeconds: 360,
    revisedMarginSeconds: 360,
  };
  const out: ScenarioResult[] = [
    {
      ...common,
      scenarioId: "sc-01",
      perturbation: { type: "close_segment", segmentId: "s2" },
      description: "segment s2 (Main Street) is closed (synthetic)",
      changed,
      revisedRecommendation: changed ? rec(B) : rec(A),
      deltaDurationMin: changed ? 3 : 0,
      changedVariables: [
        { variable: "segment[s2].closure", from: "none", to: "hypothetical verified closure" },
      ],
      comparison: changed
        ? {
            ...cmpStable,
            routeIdAfter: B.routeId,
            durationMinAfter: 12,
            distanceKmAfter: B.distanceKm,
            suitabilityAfter: "warning",
            severeHazardsAfter: 0,
            scoreSecondsAfter: 720,
            segmentsRemoved: ["s2"],
            segmentsAdded: ["s3"],
            segmentsShared: ["s1"],
            baselineMarginSeconds: 360,
            revisedMarginSeconds: null,
            revisedRunnerUp: null,
          }
        : cmpStable,
      revisedRoute: changed ? B : null,
      explanation: "Synthetic example scenario — no routing engine was run.",
    },
    {
      ...common,
      scenarioId: "sc-02",
      perturbation: { type: "set_vehicle_height", heightM: 3.0 },
      description: "vehicle height is 3 m (synthetic)",
      changed: false,
      weight: 0.5,
      revisedRecommendation: rec(A),
      deltaDurationMin: 0,
      changedVariables: [{ variable: "vehicle.heightM", from: 2.0, to: 3.0 }],
      comparison: cmpStable,
      revisedRoute: null,
      explanation:
        "Synthetic example: the recommendation is unchanged. Its score lead over the runner-up stays at 360 s.",
    },
  ];
  return out;
}

function autopsy(
  req: AutopsyAnalyzeRequest | AutopsyScenarioRequest,
  changed: boolean,
): AutopsyAnalyzeResponse {
  const r = route(req);
  const sc = scenarios(changed);
  const n = sc.length;
  const c = sc.filter((s) => s.changed).length;
  const wTot = sc.reduce((a, s) => a + s.weight, 0);
  const wCh = sc.filter((s) => s.changed).reduce((a, s) => a + s.weight, 0);
  return {
    analysisId: "demo-analysis",
    generatedAt: new Date(0).toISOString(),
    persisted: false,
    baseline: {
      route: r,
      recommendedRouteId: r.routeId,
      suitabilityStatus: "suitable",
      durationMin: 9,
      hazardPenaltySeconds: 600,
      restrictionWarnings: [],
      missingVehicleSpecs: [],
      unverifiedEvidence: { defects: [{ id: "demo-d1" }], restrictions: [] },
    },
    baselineRecommendation: rec(A),
    scenarios: sc,
    sensitivity: {
      scenariosTested: n,
      scenariosChanged: c,
      scenariosSkipped: 0,
      sensitivityScore: wCh / wTot,
      totalWeight: wTot,
      changedWeight: wCh,
      changedScenarioIds: sc.filter((s) => s.changed).map((s) => s.scenarioId),
      formula: "F = changed weight / total weight (synthetic)",
      interpretation: "Synthetic demo. Real analyses state: not an accident probability.",
    },
    suite: {
      description: "Synthetic",
      generated: n,
      truncated: false,
      vehicleSpecsSkippedBecauseUnknown: [],
    },
    explanation: "Synthetic demo autopsy — no routing engine was run.",
    disclaimer: DISCLAIMER,
  };
}

export const demoProvider = {
  async getNetwork(): Promise<NetworkResponse> {
    await delay(200);
    return {
      demoMode: true,
      pilotArea: "Synthetic schematic",
      warning: DISCLAIMER,
      nodes,
      segments: segs,
    };
  },
  async investigateRoute(req: RouteRequest): Promise<RouteResponse> {
    await delay();
    return route(req);
  },
  async analyzeAutopsy(req: AutopsyAnalyzeRequest): Promise<AutopsyAnalyzeResponse> {
    await delay(700);
    return autopsy(req, true);
  },
  async runScenario(req: AutopsyScenarioRequest): Promise<AutopsyScenarioResponse> {
    await delay(500);
    return autopsy(req, false);
  },
  async evidenceStatus(): Promise<EvidenceStatus> {
    await delay(150);
    return {
      configured: true,
      provider: "demo",
      supportedProvider: true,
      model: "synthetic",
      maxUploadBytes: 10 * 1024 * 1024,
      acceptedTypes: ["image/jpeg", "image/png", "image/webp"],
      message: "Demo mode: observations are synthetic samples, not AI analysis of your photo.",
    };
  },
  async analyzeEvidence(_input: EvidenceAnalyzeInput): Promise<EvidenceAnalyzeResponse> {
    await delay(800);
    const base = {
      source: "image_upload",
      modelProvider: "demo",
      model: "synthetic",
      observedAt: new Date(0).toISOString(),
      modelExtras: {},
      discardedModelFields: [],
      verificationStatus: "unverified" as const,
    };
    return {
      evidenceId: "demo-evidence-001",
      createdAt: new Date(0).toISOString(),
      modelProvider: "demo",
      model: "synthetic",
      location: {
        status: "unknown",
        latitude: null,
        longitude: null,
        note: "Location is unknown (synthetic demo).",
      },
      imageQuality: "synthetic",
      warnings: [],
      duplicateOf: null,
      modelExtras: {},
      disclaimer: DISCLAIMER,
      observations: [
        {
          ...base,
          id: "obs-1",
          observationType: "pothole",
          candidateCategory: "defect",
          suggestedDefectType: "pothole",
          description: "Sample pothole (synthetic, not detected from your image).",
          severityEstimate: 3,
          visualConfidence: 0.8,
          observedAttributes: {},
          unknownAttributes: ["exact geographic location"],
          requiresAuthorizedVerification: false,
        },
        {
          ...base,
          id: "obs-2",
          observationType: "restriction_sign",
          candidateCategory: "restriction_candidate",
          suggestedDefectType: null,
          description: "Sample restriction sign (synthetic).",
          severityEstimate: null,
          visualConfidence: 0.6,
          observedAttributes: {},
          unknownAttributes: ["legal or official validity"],
          requiresAuthorizedVerification: true,
        },
      ],
    };
  },
  async confirmEvidence(req: EvidenceConfirmRequest): Promise<EvidenceConfirmResponse> {
    await delay(400);
    return {
      evidenceId: req.evidenceId,
      status: "demo_only_not_saved",
      disclaimer: DISCLAIMER,
      results: req.confirmedObservationIds.map((id) => ({
        observationId: id,
        outcome: "demo_only",
        defectId: `demo-report-${id}`,
        verificationStatus: "unverified",
        message: "Not saved (demo mode).",
      })),
    };
  },
  async listVehicles(): Promise<Vehicle[]> {
    await delay(300);
    return vehicles;
  },
  async vehicleRestrictionCheck(vehicleId: string): Promise<VehicleRestrictionCheck> {
    await delay(300);
    const v = vehicles.find((x) => x.id === vehicleId) ?? vehicles[0]!;
    const unknownH = v.heightM == null;
    const items: VehicleRestrictionCheck["items"] = [
      {
        restrictionId: "demo-r1",
        roadSegmentId: "s2",
        segmentName: "Main Street",
        restrictionType: "height",
        description: "Synthetic rail underpass",
        limitValue: 3.2,
        unit: "m",
        verificationStatus: "verified",
        appliesToVehicle: true,
        vehicleValue: unknownH ? null : (v.heightM ?? null),
        outcome: unknownH ? "unknown_spec" : "fits",
        message: unknownH
          ? "Vehicle height is unknown, so clearance cannot be confirmed."
          : "Within the limit (synthetic).",
      },
    ];
    return {
      vehicleId: v.id,
      vehicleName: v.name,
      unknownSpecs: v.unknownSpecs,
      summary: {
        blocks: 0,
        may_block: 0,
        unknown_spec: unknownH ? 1 : 0,
        fits: unknownH ? 0 : 1,
        not_applicable: 0,
      },
      items,
      disclaimer: DISCLAIMER,
    };
  },
  async listRestrictions(): Promise<Restriction[]> {
    await delay(200);
    return [
      {
        id: "demo-r1",
        roadSegmentId: "s2",
        restrictionType: "height",
        limitValue: 3.2,
        unit: "m",
        appliesTo: "all",
        description: "Synthetic rail underpass",
        source: "synthetic",
        verificationStatus: "verified",
        lastVerifiedAt: null,
      },
    ];
  },
  async listDefects(): Promise<Defect[]> {
    await delay(250);
    return defects;
  },
  async getDefect(id: string): Promise<Defect> {
    await delay(150);
    return (
      defects.find((d) => d.id === id) ?? {
        id,
        defectType: "pothole",
        latitude: 0,
        longitude: 0.02,
        severity: 3,
        description: "Synthetic (demo report)",
        verificationStatus: "unverified",
        maintenanceStatus: "open",
      }
    );
  },
};
