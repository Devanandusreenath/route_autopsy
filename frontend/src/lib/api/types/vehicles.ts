import { z } from "zod";

const specStatus = z.enum(["verified", "user_confirmed", "estimated", "unknown"]);

/**
 * Display view of a stored VehicleProfile (backend adapter `to_display_vehicle`).
 * Dimensions, weights and verification metadata are NOT dropped; unknown specs are null, never guessed.
 */
export const vehicleSchema = z.object({
  id: z.string(),
  name: z.string(),
  type: z.string(),
  category: z.string(),
  make: z.string(),
  model: z.string(),
  year: z.number().nullish(),
  variant: z.string().optional(),
  lengthM: z.number().nullish(),
  widthM: z.number().nullish(),
  heightM: z.number().nullish(),
  grossVehicleWeightKg: z.number().nullish(),
  currentLoadedWeightKg: z.number().nullish(),
  specStatus: z.record(z.string(), specStatus),
  verificationStatus: specStatus,
  unknownSpecs: z.array(z.string()),
  sources: z.array(z.string()),
  isIllustrative: z.boolean(),
  notes: z.string().nullish(),
});
export type Vehicle = z.infer<typeof vehicleSchema>;

export const vehicleListResponseSchema = z.array(vehicleSchema);

/** GET /vehicles/{id}/restriction-check — same per-restriction logic as the routing engine. */
export const restrictionOutcomeSchema = z.enum([
  "blocks",
  "may_block",
  "unknown_spec",
  "fits",
  "not_applicable",
]);
export type RestrictionOutcome = z.infer<typeof restrictionOutcomeSchema>;

export const restrictionCheckItemSchema = z.object({
  restrictionId: z.string(),
  roadSegmentId: z.string(),
  segmentName: z.string(),
  restrictionType: z.string(),
  description: z.string(),
  limitValue: z.number().nullish(),
  unit: z.string().nullish(),
  verificationStatus: z.string(),
  appliesToVehicle: z.boolean(),
  vehicleValue: z.number().nullish(),
  outcome: restrictionOutcomeSchema,
  message: z.string(),
});

export const vehicleRestrictionCheckSchema = z.object({
  vehicleId: z.string(),
  vehicleName: z.string(),
  unknownSpecs: z.array(z.string()),
  summary: z.record(z.string(), z.number()),
  items: z.array(restrictionCheckItemSchema),
  disclaimer: z.string(),
});
export type VehicleRestrictionCheck = z.infer<typeof vehicleRestrictionCheckSchema>;
