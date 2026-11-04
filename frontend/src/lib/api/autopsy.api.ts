import { request, validateInput } from "./client";
import { isDemoMode } from "./config";
import { endpoints } from "./endpoints";
import type { ApiResult } from "./types/common";
import {
  autopsyAnalyzeRequestSchema,
  autopsyAnalyzeResponseSchema,
  autopsyScenarioRequestSchema,
  autopsyScenarioResponseSchema,
  type AutopsyAnalyzeRequest,
  type AutopsyAnalyzeResponse,
  type AutopsyScenarioRequest,
  type AutopsyScenarioResponse,
} from "./types/autopsy";
import { demoProvider } from "@/lib/demo/provider";

export async function analyzeAutopsy(
  input: AutopsyAnalyzeRequest,
): Promise<ApiResult<AutopsyAnalyzeResponse>> {
  if (isDemoMode())
    return {
      data: await demoProvider.analyzeAutopsy(validateInput(autopsyAnalyzeRequestSchema, input)),
      source: "demo",
    };
  const data = await request({
    method: "POST",
    path: endpoints.autopsyAnalyze,
    body: input,
    requestSchema: autopsyAnalyzeRequestSchema,
    responseSchema: autopsyAnalyzeResponseSchema,
  });
  return { data, source: "backend" };
}

export async function runScenario(
  input: AutopsyScenarioRequest,
): Promise<ApiResult<AutopsyScenarioResponse>> {
  if (isDemoMode())
    return {
      data: await demoProvider.runScenario(validateInput(autopsyScenarioRequestSchema, input)),
      source: "demo",
    };
  const data = await request({
    method: "POST",
    path: endpoints.autopsyScenario,
    body: input,
    requestSchema: autopsyScenarioRequestSchema,
    responseSchema: autopsyScenarioResponseSchema,
  });
  return { data, source: "backend" };
}
