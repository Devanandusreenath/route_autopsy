import { z } from "zod";

/** GET /defects, GET /defects/{id}. Required fields only; provenance fields on evidence-created reports are kept as optional extras. */
export const defectSchema = z.object({
  id: z.string(),
  defectType: z.string(),
  latitude: z.number(),
  longitude: z.number(),
  severity: z.number().int().min(1).max(5),
  description: z.string().nullish(),
  observedAt: z.string().nullish(),
  roadSegmentId: z.string().nullish(),
  reportedAt: z.string().nullish(),
  verificationStatus: z.string(),
  maintenanceStatus: z.string(),
  independentReportCount: z.number().optional(),
  isUserSubmitted: z.boolean().optional(),
  evidenceId: z.string().nullish(),
  evidenceSource: z.string().nullish(),
  modelProvider: z.string().nullish(),
  visualConfidence: z.number().nullish(),
  userConfirmedObservation: z.boolean().nullish(),
});
export type Defect = z.infer<typeof defectSchema>;
export const defectListSchema = z.array(defectSchema);
