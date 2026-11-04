import { z } from "zod";
import {
  routeAlternativeSchema,
  routeRequestSchema,
  routeResponseSchema,
  routeWarningSchema,
  suitabilitySchema,
} from "./routes";

/** Hypothetical changes. They are evaluated on in-memory copies and NEVER saved by the backend. */
export const perturbationSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("resolve_defect"), defectId: z.string().min(1) }),
  z.object({ type: z.literal("verify_restriction"), restrictionId: z.string().min(1) }),
  z.object({ type: z.literal("remove_restriction"), restrictionId: z.string().min(1) }),
  z.object({ type: z.literal("set_vehicle_height"), heightM: z.number().gt(0).max(10) }),
  z.object({ type: z.literal("set_vehicle_width"), widthM: z.number().gt(0).max(5) }),
  z.object({ type: z.literal("set_vehicle_weight"), weightKg: z.number().gt(0).max(100000) }),
  z.object({ type: z.literal("close_segment"), segmentId: z.string().min(1) }),
  z.object({
    type: z.literal("set_evidence_verification"),
    targetKind: z.enum(["defect", "restriction"]),
    targetId: z.string().min(1),
    status: z.enum(["verified", "unverified"]),
  }),
]);
export type Perturbation = z.infer<typeof perturbationSchema>;

export const autopsyAnalyzeRequestSchema = routeRequestSchema.extend({
  includeDefaultSuite: z.boolean().optional(),
  perturbations: z.array(perturbationSchema).max(25).optional(),
});
export type AutopsyAnalyzeRequest = z.infer<typeof autopsyAnalyzeRequestSchema>;

export const autopsyScenarioRequestSchema = routeRequestSchema.extend({
  perturbations: z.array(perturbationSchema).min(1, "Choose a change to test").max(25),
});
export type AutopsyScenarioRequest = z.infer<typeof autopsyScenarioRequestSchema>;

export const recommendationSchema = z.object({
  routeId: z.string(),
  via: z.array(z.string()),
  segmentIds: z.array(z.string()),
  durationMin: z.number(),
  suitabilityStatus: suitabilitySchema,
});

const runnerUpSchema = z
  .object({
    routeId: z.string(),
    segmentIds: z.array(z.string()),
    suitabilityStatus: suitabilitySchema,
    scoreSeconds: z.number(),
  })
  .nullable();

/** Before/after metrics: baseline recommendation vs the scenario's recommendation (same route re-scored when stable). */
export const scenarioComparisonSchema = z.object({
  routeIdBefore: z.string().nullable(),
  routeIdAfter: z.string().nullable(),
  durationMinBefore: z.number().nullable(),
  durationMinAfter: z.number().nullable(),
  distanceKmBefore: z.number().nullable(),
  distanceKmAfter: z.number().nullable(),
  suitabilityBefore: suitabilitySchema.nullable(),
  suitabilityAfter: suitabilitySchema.nullable(),
  severeHazardsBefore: z.number().nullable(),
  severeHazardsAfter: z.number().nullable(),
  scoreSecondsBefore: z.number().nullable(),
  scoreSecondsAfter: z.number().nullable(),
  segmentsRemoved: z.array(z.string()),
  segmentsAdded: z.array(z.string()),
  segmentsShared: z.array(z.string()),
  baselineRunnerUp: runnerUpSchema,
  revisedRunnerUp: runnerUpSchema,
  baselineMarginSeconds: z.number().nullable(),
  revisedMarginSeconds: z.number().nullable(),
});
export type ScenarioComparison = z.infer<typeof scenarioComparisonSchema>;

export const scenarioResultSchema = z.object({
  scenarioId: z.string(),
  perturbation: z.record(z.string(), z.unknown()),
  description: z.string(),
  weight: z.number(),
  inputChanged: z.boolean(),
  changed: z.boolean(),
  skipped: z.boolean(),
  baselineRecommendation: recommendationSchema.nullable(),
  revisedRecommendation: recommendationSchema.nullable(),
  deltaDurationMin: z.number().nullable(),
  changedVariables: z.array(
    z.object({
      variable: z.string(),
      from: z.union([z.string(), z.number()]).nullish(),
      to: z.union([z.string(), z.number()]).nullish(),
    }),
  ),
  changedWarnings: z.object({ added: z.array(z.string()), removed: z.array(z.string()) }),
  baselineRouteUnderScenario: z
    .object({
      routeId: z.string(),
      statusBefore: suitabilitySchema,
      statusAfter: suitabilitySchema,
      durationSecondsBefore: z.number(),
      durationSecondsAfter: z.number(),
    })
    .nullable(),
  comparison: scenarioComparisonSchema.nullable(),
  /** Full detail of the revised recommendation; present only when it differs from the baseline recommendation. */
  revisedRoute: routeAlternativeSchema.nullable(),
  explanation: z.string(),
  notes: z.array(z.string()),
});
export type ScenarioResult = z.infer<typeof scenarioResultSchema>;

export const sensitivitySchema = z.object({
  scenariosTested: z.number(),
  scenariosChanged: z.number(),
  scenariosSkipped: z.number(),
  /** null when nothing was tested. NOT an accident or failure probability. */
  sensitivityScore: z.number().nullable(),
  totalWeight: z.number(),
  changedWeight: z.number(),
  changedScenarioIds: z.array(z.string()),
  formula: z.string(),
  interpretation: z.string(),
});

export const autopsyResponseSchema = z.object({
  analysisId: z.string(),
  generatedAt: z.string(),
  persisted: z.literal(false),
  baseline: z.object({
    route: routeResponseSchema,
    recommendedRouteId: z.string().nullable(),
    suitabilityStatus: suitabilitySchema.nullable(),
    durationMin: z.number().nullable(),
    hazardPenaltySeconds: z.number().nullable(),
    restrictionWarnings: z.array(routeWarningSchema),
    missingVehicleSpecs: z.array(z.string()),
    unverifiedEvidence: z.object({
      defects: z.array(z.record(z.string(), z.unknown())),
      restrictions: z.array(z.record(z.string(), z.unknown())),
    }),
  }),
  baselineRecommendation: recommendationSchema.nullable(),
  scenarios: z.array(scenarioResultSchema),
  sensitivity: sensitivitySchema,
  suite: z.record(z.string(), z.unknown()),
  explanation: z.string(),
  disclaimer: z.string(),
});
export type AutopsyResponse = z.infer<typeof autopsyResponseSchema>;

// /autopsy/analyze and /autopsy/scenario share one response shape.
export const autopsyAnalyzeResponseSchema = autopsyResponseSchema;
export const autopsyScenarioResponseSchema = autopsyResponseSchema;
export type AutopsyAnalyzeResponse = AutopsyResponse;
export type AutopsyScenarioResponse = AutopsyResponse;
