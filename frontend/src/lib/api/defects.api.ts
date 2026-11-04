import { queryOptions } from "@tanstack/react-query";
import { request } from "./client";
import { isDemoMode } from "./config";
import { endpoints } from "./endpoints";
import type { ApiResult } from "./types/common";
import { defectListSchema, defectSchema, type Defect } from "./types/defects";
import { demoProvider } from "@/lib/demo/provider";

export async function listDefects(): Promise<ApiResult<Defect[]>> {
  if (isDemoMode()) return { data: await demoProvider.listDefects(), source: "demo" };
  const data = await request({
    method: "GET",
    path: endpoints.defects,
    responseSchema: defectListSchema,
  });
  return { data, source: "backend" };
}

export async function getDefect(defectId: string): Promise<ApiResult<Defect>> {
  if (isDemoMode()) return { data: await demoProvider.getDefect(defectId), source: "demo" };
  const data = await request({
    method: "GET",
    path: endpoints.defect(defectId),
    responseSchema: defectSchema,
  });
  return { data, source: "backend" };
}

export const defectsQuery = queryOptions({
  queryKey: ["defects"],
  queryFn: listDefects,
  retry: false,
});
