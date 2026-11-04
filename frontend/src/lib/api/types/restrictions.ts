import { z } from "zod";

/** GET /restrictions. `appliesTo` is "all" or a list of vehicle categories. */
export const restrictionSchema = z.object({
  id: z.string(),
  roadSegmentId: z.string(),
  restrictionType: z.string(),
  limitValue: z.number().nullish(),
  unit: z.string().nullish(),
  appliesTo: z.union([z.literal("all"), z.array(z.string())]),
  description: z.string().nullish(),
  source: z.string().nullish(),
  verificationStatus: z.string(),
  lastVerifiedAt: z.string().nullish(),
});
export type Restriction = z.infer<typeof restrictionSchema>;
export const restrictionListSchema = z.array(restrictionSchema);
