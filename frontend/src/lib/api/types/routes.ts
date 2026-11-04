import { z } from "zod";
import { vehicleSchema } from "./vehicles";

export const routeRequestSchema = z.object({
  /** Pilot node id (e.g. "FKC") or exact node name. */
  origin: z.string().trim().min(1, "Origin is required").max(200),
  destination: z.string().trim().min(1, "Destination is required").max(200),
  vehicleId: z.string().optional(),
  avoidSevereDefects: z.boolean().optional(),
  preferBetterSurfaces: z.boolean().optional(),
  maxAlternatives: z.number().int().min(1).max(10).optional(),
});
export type RouteRequest = z.infer<typeof routeRequestSchema>;

export const suitabilitySchema = z.enum(["suitable", "warning", "not_validated", "unsuitable"]);
export type Suitability = z.infer<typeof suitabilitySchema>;

export const routeSegmentSchema = z.object({
  id: z.string(),
  name: z.string(),
  distanceKm: z.number(),
  /** Evidence-attention heuristic derived from warnings/defects — not an accident probability. */
  riskLevel: z.enum(["low", "medium", "high"]),
  note: z.string().nullish(),
});

export const routeWarningSchema = z.object({
  level: z.string(),
  message: z.string(),
  segmentId: z.string().nullish(),
  restrictionId: z.string().nullish(),
  defectId: z.string().nullish(),
});

export const routeAlternativeSchema = z.object({
  routeId: z.string(),
  label: z.string(),
  segmentIds: z.array(z.string()),
  segments: z.array(routeSegmentSchema),
  distanceKm: z.number(),
  durationMin: z.number(),
  suitabilityStatus: suitabilitySchema,
  recommended: z.boolean(),
  isFastestCandidate: z.boolean(),
  rank: z.number(),
  scoreSeconds: z.number(),
  scoreBreakdown: z.record(z.string(), z.number()),
  severeHazardCount: z.number(),
  warnings: z.array(routeWarningSchema),
  missingData: z.array(z.string()),
  rejectionReasons: z.array(z.string()),
  explanation: z.string(),
  geometry: z.array(z.array(z.number())),
});

export const routeSearchSchema = z.object({
  candidatesEnumerated: z.number(),
  candidatesEvaluated: z.number(),
  truncated: z.boolean(),
  maxDepth: z.number(),
  maxCandidates: z.number(),
  statusCounts: z.record(z.string(), z.number()),
  alternativesReturned: z.number(),
});

export const routeResponseSchema = z.object({
  routeId: z.string(),
  origin: z.string(),
  destination: z.string(),
  originId: z.string(),
  destinationId: z.string(),
  distanceKm: z.number(),
  durationMin: z.number(),
  segments: z.array(routeSegmentSchema),
  vehicle: vehicleSchema.nullish(),
  suitabilityStatus: suitabilitySchema,
  recommended: z.boolean(),
  recommendationStatus: z.enum(["recommended", "no_usable_route"]),
  explanation: z.string(),
  warnings: z.array(routeWarningSchema),
  missingData: z.array(z.string()),
  alternatives: z.array(routeAlternativeSchema),
  search: routeSearchSchema,
  disclaimer: z.string(),
});
export type RouteResponse = z.infer<typeof routeResponseSchema>;
export type RouteSegment = z.infer<typeof routeSegmentSchema>;
export type RouteAlternative = z.infer<typeof routeAlternativeSchema>;
