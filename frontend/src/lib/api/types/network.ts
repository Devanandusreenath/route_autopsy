import { z } from "zod";

/** GET /api/meta — the illustrative Kochi pilot graph (nodes for pickers, segment geometry for the map). */
export const networkNodeSchema = z.object({
  id: z.string(),
  name: z.string(),
  /** [latitude, longitude] */
  position: z.tuple([z.number(), z.number()]),
});

export const networkSegmentSchema = z.object({
  id: z.string(),
  name: z.string(),
  from: z.string(),
  to: z.string(),
  surface: z.string(),
  geometry: z.array(z.tuple([z.number(), z.number()])),
});

export const networkResponseSchema = z.object({
  demoMode: z.boolean().optional(),
  pilotArea: z.string().optional(),
  warning: z.string().optional(),
  nodes: z.array(networkNodeSchema),
  segments: z.array(networkSegmentSchema),
});
export type NetworkNode = z.infer<typeof networkNodeSchema>;
export type NetworkSegment = z.infer<typeof networkSegmentSchema>;
export type NetworkResponse = z.infer<typeof networkResponseSchema>;
