/**
 * Environment configuration for the API layer.
 *
 * Mode resolution (explicit):
 *  - VITE_APP_MODE="demo"    -> synthetic demo provider, no network calls.
 *  - VITE_APP_MODE="backend" -> real HTTP calls to VITE_API_BASE_URL.
 *  - unset                   -> "backend" if VITE_API_BASE_URL is set, otherwise "demo".
 *
 * If backend mode is requested without a base URL, the config is marked
 * misconfigured and every request fails with a CONFIG error. We never
 * silently pretend a backend is available.
 *
 * Only public, non-secret values may live in VITE_* variables.
 */
export type AppMode = "demo" | "backend";

export interface ApiConfig {
  mode: AppMode;
  baseUrl: string | null;
  timeoutMs: number;
  misconfigured: boolean;
  misconfigReason?: string | undefined;
}

function readEnv(key: string): string | undefined {
  const value = (import.meta.env as Record<string, string | undefined>)[key];
  return value && value.trim() !== "" ? value.trim() : undefined;
}

export function resolveConfig(env: {
  mode?: string | undefined;
  baseUrl?: string | undefined;
  timeoutMs?: string | undefined;
}): ApiConfig {
  const baseUrl = env.baseUrl ? env.baseUrl.replace(/\/+$/, "") : null;
  const requested = env.mode?.toLowerCase();
  const mode: AppMode =
    requested === "demo" || requested === "backend" ? requested : baseUrl ? "backend" : "demo";
  const timeout = Number(env.timeoutMs);
  const misconfigured = mode === "backend" && !baseUrl;
  return {
    mode,
    baseUrl,
    timeoutMs: Number.isFinite(timeout) && timeout > 0 ? timeout : 15000,
    misconfigured,
    misconfigReason: misconfigured
      ? "Backend mode is enabled but VITE_API_BASE_URL is not set."
      : undefined,
  };
}

export const apiConfig: ApiConfig = resolveConfig({
  mode: readEnv("VITE_APP_MODE"),
  baseUrl: readEnv("VITE_API_BASE_URL"),
  timeoutMs: readEnv("VITE_API_TIMEOUT_MS"),
});

export const isDemoMode = () => apiConfig.mode === "demo";
