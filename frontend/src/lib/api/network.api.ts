import { queryOptions } from "@tanstack/react-query";
import { request } from "./client";
import { isDemoMode } from "./config";
import { endpoints } from "./endpoints";
import type { ApiResult } from "./types/common";
import { networkResponseSchema, type NetworkResponse } from "./types/network";
import { demoProvider } from "@/lib/demo/provider";

export async function getNetwork(): Promise<ApiResult<NetworkResponse>> {
  if (isDemoMode()) return { data: await demoProvider.getNetwork(), source: "demo" };
  const data = await request({
    method: "GET",
    path: endpoints.network,
    responseSchema: networkResponseSchema,
  });
  return { data, source: "backend" };
}

export const networkQuery = queryOptions({
  queryKey: ["network"],
  queryFn: getNetwork,
  retry: false,
});
