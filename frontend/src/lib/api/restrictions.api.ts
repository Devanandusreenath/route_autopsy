import { queryOptions } from "@tanstack/react-query";
import { request } from "./client";
import { isDemoMode } from "./config";
import { endpoints } from "./endpoints";
import type { ApiResult } from "./types/common";
import { restrictionListSchema, type Restriction } from "./types/restrictions";
import { demoProvider } from "@/lib/demo/provider";

export async function listRestrictions(): Promise<ApiResult<Restriction[]>> {
  if (isDemoMode()) return { data: await demoProvider.listRestrictions(), source: "demo" };
  const data = await request({
    method: "GET",
    path: endpoints.restrictions,
    responseSchema: restrictionListSchema,
  });
  return { data, source: "backend" };
}

export const restrictionsQuery = queryOptions({
  queryKey: ["restrictions"],
  queryFn: listRestrictions,
  retry: false,
});
