import { request, validateInput } from "./client";
import { isDemoMode } from "./config";
import { endpoints } from "./endpoints";
import { queryOptions } from "@tanstack/react-query";
import { ApiError } from "./errors";
import type { ApiResult } from "./types/common";
import {
  ACCEPTED_EVIDENCE_TYPES,
  MAX_EVIDENCE_BYTES,
  evidenceAnalyzeResponseSchema,
  evidenceConfirmRequestSchema,
  evidenceConfirmResponseSchema,
  evidenceStatusSchema,
  type EvidenceAnalyzeInput,
  type EvidenceAnalyzeResponse,
  type EvidenceConfirmRequest,
  type EvidenceConfirmResponse,
  type EvidenceStatus,
} from "./types/evidence";
import { demoProvider } from "@/lib/demo/provider";

function validateFile(file: File) {
  if (!ACCEPTED_EVIDENCE_TYPES.includes(file.type) || file.size > MAX_EVIDENCE_BYTES)
    throw new ApiError({
      message: "Upload a JPEG, PNG or WebP image under 10 MB.",
      category: "validation",
      retryable: false,
    });
}

export async function analyzeEvidence(
  input: EvidenceAnalyzeInput,
): Promise<ApiResult<EvidenceAnalyzeResponse>> {
  validateFile(input.file);
  if (isDemoMode()) return { data: await demoProvider.analyzeEvidence(input), source: "demo" };
  // Multipart field names confirmed against the backend: file, notes, latitude, longitude.
  const form = new FormData();
  form.append("file", input.file);
  if (input.notes) form.append("notes", input.notes);
  if (input.latitude !== undefined && input.longitude !== undefined) {
    form.append("latitude", String(input.latitude));
    form.append("longitude", String(input.longitude));
  }
  const data = await request({
    method: "POST",
    path: endpoints.evidenceAnalyze,
    formData: form,
    responseSchema: evidenceAnalyzeResponseSchema,
    timeoutMs: 60000,
  });
  return { data, source: "backend" };
}

export async function confirmEvidence(
  input: EvidenceConfirmRequest,
): Promise<ApiResult<EvidenceConfirmResponse>> {
  if (isDemoMode())
    return {
      data: await demoProvider.confirmEvidence(validateInput(evidenceConfirmRequestSchema, input)),
      source: "demo",
    };
  const data = await request({
    method: "POST",
    path: endpoints.evidenceConfirm,
    body: input,
    requestSchema: evidenceConfirmRequestSchema,
    responseSchema: evidenceConfirmResponseSchema,
  });
  return { data, source: "backend" };
}

export async function getEvidenceStatus(): Promise<ApiResult<EvidenceStatus>> {
  if (isDemoMode()) return { data: await demoProvider.evidenceStatus(), source: "demo" };
  const data = await request({
    method: "GET",
    path: endpoints.evidenceStatus,
    responseSchema: evidenceStatusSchema,
  });
  return { data, source: "backend" };
}

export const evidenceStatusQuery = queryOptions({
  queryKey: ["evidence-status"],
  queryFn: getEvidenceStatus,
  retry: false,
});
