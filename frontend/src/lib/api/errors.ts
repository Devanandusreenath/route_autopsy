/** Normalized API errors. UI components only ever see ApiError. */
export type ApiErrorCategory =
  | "config"
  | "network"
  | "timeout"
  | "validation" // 400 / 422
  | "unauthorized" // 401
  | "forbidden" // 403
  | "not_found" // 404
  | "server" // 5xx
  | "http" // other non-2xx
  | "invalid_json"
  | "unexpected_response"
  | "aborted";

export class ApiError extends Error {
  readonly category: ApiErrorCategory;
  readonly status?: number | undefined;
  readonly retryable: boolean;
  /** Field-level messages from validation responses, if parseable. Safe for display. */
  readonly fieldErrors?: string[] | undefined;

  constructor(opts: {
    message: string;
    category: ApiErrorCategory;
    status?: number | undefined;
    retryable: boolean;
    fieldErrors?: string[] | undefined;
  }) {
    super(opts.message);
    this.name = "ApiError";
    this.category = opts.category;
    this.status = opts.status;
    this.retryable = opts.retryable;
    this.fieldErrors = opts.fieldErrors;
  }
}

export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError;
}

/**
 * Extract human-readable validation messages. Supports FastAPI's default
 * 422 shape ({ detail: [{ loc, msg }] }) and the backend's { detail: "string" } messages.
 */
function extractFieldErrors(body: unknown): string[] | undefined {
  if (!body || typeof body !== "object") return undefined;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string") return [detail.slice(0, 300)];
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => {
        if (!d || typeof d !== "object") return null;
        const msg = (d as { msg?: unknown }).msg;
        const loc = (d as { loc?: unknown }).loc;
        if (typeof msg !== "string") return null;
        const field = Array.isArray(loc) ? loc.filter((l) => l !== "body").join(".") : "";
        return field ? `${field}: ${msg}` : msg;
      })
      .filter((m): m is string => !!m);
    return msgs.length ? msgs.slice(0, 10) : undefined;
  }
  return undefined;
}

/** Map an HTTP status to a normalized error. Never includes raw server bodies/stack traces. */
export function errorFromStatus(status: number, body?: unknown): ApiError {
  const fieldErrors = status === 400 || status === 422 ? extractFieldErrors(body) : undefined;
  if (status === 400 || status === 422)
    return new ApiError({
      message: "The request was rejected because some inputs are invalid.",
      category: "validation",
      status,
      retryable: false,
      fieldErrors,
    });
  if (status === 401)
    return new ApiError({
      message: "The backend requires authentication.",
      category: "unauthorized",
      status,
      retryable: false,
    });
  if (status === 403)
    return new ApiError({
      message: "You don't have permission for this action.",
      category: "forbidden",
      status,
      retryable: false,
    });
  if (status === 404)
    return new ApiError({
      message:
        "The backend endpoint or resource was not found. The endpoint path may need updating.",
      category: "not_found",
      status,
      retryable: false,
    });
  if (status >= 500)
    return new ApiError({
      message: "The backend hit an internal error. Please try again.",
      category: "server",
      status,
      retryable: true,
    });
  return new ApiError({
    message: `The backend responded with an unexpected status (${status}).`,
    category: "http",
    status,
    retryable: status === 408 || status === 429,
  });
}

export function toApiError(e: unknown): ApiError {
  if (isApiError(e)) return e;
  return new ApiError({
    message: "Something unexpected went wrong.",
    category: "unexpected_response",
    retryable: true,
  });
}
