import type { z } from "zod";
import { apiConfig, type ApiConfig } from "./config";
import { ApiError, errorFromStatus } from "./errors";

export interface RequestOptions<TReq extends z.ZodTypeAny, TRes extends z.ZodTypeAny> {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  path: string;
  /** Validated before sending. */
  body?: z.input<TReq>;
  requestSchema?: TReq;
  /** Validated after receiving. Required: TS types do not guarantee runtime shape. */
  responseSchema: TRes;
  /** Send multipart instead of JSON (e.g. evidence uploads). Not schema-validated. */
  formData?: FormData;
  signal?: AbortSignal;
  timeoutMs?: number;
}

/**
 * Shared HTTP client. The only place in the app that calls fetch().
 * No auth headers are attached: the backend currently has no authentication (see backend/README.md, known limitations).
 */
export async function request<TReq extends z.ZodTypeAny, TRes extends z.ZodTypeAny>(
  opts: RequestOptions<TReq, TRes>,
  config: ApiConfig = apiConfig,
  fetchImpl: typeof fetch = fetch,
): Promise<z.output<TRes>> {
  if (config.misconfigured || !config.baseUrl) {
    throw new ApiError({
      message: config.misconfigReason ?? "No backend URL is configured.",
      category: "config",
      retryable: false,
    });
  }

  let payload: BodyInit | undefined;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.formData) {
    payload = opts.formData;
  } else if (opts.body !== undefined) {
    const parsed = opts.requestSchema ? opts.requestSchema.safeParse(opts.body) : null;
    if (parsed && !parsed.success) {
      throw new ApiError({
        message: "Some inputs are invalid.",
        category: "validation",
        retryable: false,
        fieldErrors: parsed.error.issues.map((i) => `${i.path.join(".") || "input"}: ${i.message}`),
      });
    }
    payload = JSON.stringify(parsed ? parsed.data : opts.body);
    headers["Content-Type"] = "application/json";
  }

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, opts.timeoutMs ?? config.timeoutMs);
  const onExternalAbort = () => controller.abort();
  opts.signal?.addEventListener("abort", onExternalAbort);

  let res: Response;
  try {
    res = await fetchImpl(`${config.baseUrl}${opts.path}`, {
      method: opts.method ?? (payload ? "POST" : "GET"),
      headers,
      body: payload ?? null,
      signal: controller.signal,
    });
  } catch {
    if (timedOut)
      throw new ApiError({
        message: "The backend took too long to respond.",
        category: "timeout",
        retryable: true,
      });
    if (opts.signal?.aborted)
      throw new ApiError({ message: "Request cancelled.", category: "aborted", retryable: true });
    // Browsers report connection refused, DNS failure and CORS rejection identically.
    throw new ApiError({
      message: `Couldn't reach the backend at ${config.baseUrl}. It may be offline, refusing connections, or blocking this origin (CORS).`,
      category: "network",
      retryable: true,
    });
  } finally {
    clearTimeout(timer);
    opts.signal?.removeEventListener("abort", onExternalAbort);
  }

  const text = await res.text().catch(() => "");
  let json: unknown = undefined;
  let jsonOk = true;
  if (text) {
    try {
      json = JSON.parse(text);
    } catch {
      jsonOk = false;
    }
  }

  if (!res.ok) throw errorFromStatus(res.status, jsonOk ? json : undefined);

  if (!jsonOk)
    throw new ApiError({
      message: "The backend returned a response that isn't valid JSON.",
      category: "invalid_json",
      status: res.status,
      retryable: false,
    });

  const validated = opts.responseSchema.safeParse(json);
  if (!validated.success) {
    if (import.meta.env.DEV)
      console.warn("[api] response schema mismatch", opts.path, validated.error.issues);
    throw new ApiError({
      message:
        "The backend response didn't match the expected format. The frontend contract may need updating.",
      category: "unexpected_response",
      status: res.status,
      retryable: false,
    });
  }
  return validated.data;
}

/** Validate request input and throw a normalized ApiError (used by demo paths too). */
export function validateInput<S extends z.ZodTypeAny>(schema: S, input: unknown): z.output<S> {
  const parsed = schema.safeParse(input);
  if (!parsed.success)
    throw new ApiError({
      message: "Some inputs are invalid.",
      category: "validation",
      retryable: false,
      fieldErrors: parsed.error.issues.map((i) => `${i.path.join(".") || "input"}: ${i.message}`),
    });
  return parsed.data;
}
