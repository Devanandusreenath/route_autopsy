import { z } from "zod";

export interface EvidenceAnalyzeInput {
  file: File;
  notes?: string;
  /** Optional, user-stated location. The image model never supplies coordinates. */
  latitude?: number;
  longitude?: number;
}

export const MAX_EVIDENCE_BYTES = 10 * 1024 * 1024;
export const ACCEPTED_EVIDENCE_TYPES = ["image/jpeg", "image/png", "image/webp"];

export const observationSchema = z.object({
  id: z.string(),
  observationType: z.string(),
  candidateCategory: z.enum(["defect", "restriction_candidate", "closure_candidate", "unknown"]),
  suggestedDefectType: z.string().nullish(),
  description: z.string(),
  severityEstimate: z.number().int().min(1).max(5).nullish(),
  /** The model's self-reported visual confidence. This is NOT verification. */
  visualConfidence: z.number().min(0).max(1),
  observedAttributes: z.record(z.string(), z.unknown()),
  unknownAttributes: z.array(z.string()),
  verificationStatus: z.literal("unverified"),
  requiresAuthorizedVerification: z.boolean(),
  source: z.string(),
  modelProvider: z.string(),
  model: z.string(),
  observedAt: z.string(),
  modelExtras: z.record(z.string(), z.unknown()),
  discardedModelFields: z.array(z.string()),
});
export type Observation = z.infer<typeof observationSchema>;

export const evidenceAnalyzeResponseSchema = z.object({
  evidenceId: z.string(),
  createdAt: z.string(),
  modelProvider: z.string(),
  model: z.string(),
  location: z.object({
    status: z.enum(["unknown", "user_provided"]),
    latitude: z.number().nullish(),
    longitude: z.number().nullish(),
    note: z.string(),
  }),
  imageQuality: z.string().nullish(),
  observations: z.array(observationSchema),
  warnings: z.array(z.string()),
  duplicateOf: z.string().nullish(),
  modelExtras: z.record(z.string(), z.unknown()),
  disclaimer: z.string(),
});
export type EvidenceAnalyzeResponse = z.infer<typeof evidenceAnalyzeResponseSchema>;

export const evidenceConfirmRequestSchema = z.object({
  evidenceId: z.string().min(1),
  confirmedObservationIds: z.array(z.string()).max(50),
  latitude: z.number().min(-90).max(90).optional(),
  longitude: z.number().min(-180).max(180).optional(),
  severityOverrides: z.record(z.string(), z.number().int().min(1).max(5)).optional(),
  notes: z.string().max(3000).optional(),
});
export type EvidenceConfirmRequest = z.infer<typeof evidenceConfirmRequestSchema>;

export const evidenceConfirmResponseSchema = z.object({
  evidenceId: z.string(),
  status: z.string(),
  results: z.array(
    z.object({
      observationId: z.string(),
      outcome: z.string(),
      defectId: z.string().nullish(),
      verificationStatus: z.string(),
      message: z.string(),
    }),
  ),
  disclaimer: z.string(),
});
export type EvidenceConfirmResponse = z.infer<typeof evidenceConfirmResponseSchema>;

/** GET /evidence/status — is the server-side vision provider configured? Never includes credentials. */
export const evidenceStatusSchema = z.object({
  configured: z.boolean(),
  provider: z.string(),
  supportedProvider: z.boolean(),
  model: z.string().nullish(),
  maxUploadBytes: z.number(),
  acceptedTypes: z.array(z.string()),
  message: z.string(),
});
export type EvidenceStatus = z.infer<typeof evidenceStatusSchema>;
