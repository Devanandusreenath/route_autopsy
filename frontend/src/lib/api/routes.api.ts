import { request, validateInput } from "./client";
import { isDemoMode } from "./config";
import { endpoints } from "./endpoints";
import type { ApiResult } from "./types/common";
import {
  routeRequestSchema,
  routeResponseSchema,
  type RouteRequest,
  type RouteResponse,
} from "./types/routes";
import { demoProvider } from "@/lib/demo/provider";

export async function investigateRoute(input: RouteRequest): Promise<ApiResult<RouteResponse>> {
  if (isDemoMode())
    return {
      data: await demoProvider.investigateRoute(validateInput(routeRequestSchema, input)),
      source: "demo",
    };
  const data = await request({
    method: "POST",
    path: endpoints.routes,
    body: input,
    requestSchema: routeRequestSchema,
    responseSchema: routeResponseSchema,
  });
  return { data, source: "backend" };
}
