import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * In backend mode, no API module may ever return demo data. When the backend is down or misbehaves, every function must
 * reject with an ApiError and the demo provider must not be touched.
 */
vi.mock("@/lib/api/config", async (orig) => {
  const real = await orig<typeof import("@/lib/api/config")>();
  return {
    ...real,
    apiConfig: {
      mode: "backend",
      baseUrl: "http://backend.invalid",
      timeoutMs: 2000,
      misconfigured: false,
    },
    isDemoMode: () => false,
  };
});

import { demoProvider } from "@/lib/demo/provider";
import { isApiError } from "@/lib/api/errors";
import { getNetwork } from "@/lib/api/network.api";
import { listVehicles, getVehicleRestrictionCheck } from "@/lib/api/vehicles.api";
import { listDefects, getDefect } from "@/lib/api/defects.api";
import { listRestrictions } from "@/lib/api/restrictions.api";
import { investigateRoute } from "@/lib/api/routes.api";
import { analyzeAutopsy, runScenario } from "@/lib/api/autopsy.api";
import { analyzeEvidence, confirmEvidence, getEvidenceStatus } from "@/lib/api/evidence.api";

const calls: Record<string, () => Promise<unknown>> = {
  getNetwork: () => getNetwork(),
  listVehicles: () => listVehicles(),
  getVehicleRestrictionCheck: () => getVehicleRestrictionCheck("veh-x"),
  listDefects: () => listDefects(),
  getDefect: () => getDefect("D1"),
  listRestrictions: () => listRestrictions(),
  investigateRoute: () => investigateRoute({ origin: "FKC", destination: "ALV" }),
  analyzeAutopsy: () => analyzeAutopsy({ origin: "FKC", destination: "ALV" }),
  runScenario: () =>
    runScenario({
      origin: "FKC",
      destination: "ALV",
      perturbations: [{ type: "close_segment", segmentId: "S1" }],
    }),
  getEvidenceStatus: () => getEvidenceStatus(),
  analyzeEvidence: () =>
    analyzeEvidence({ file: new File([new Uint8Array(4)], "a.jpg", { type: "image/jpeg" }) }),
  confirmEvidence: () => confirmEvidence({ evidenceId: "EV-1", confirmedObservationIds: [] }),
};

describe("backend mode never returns demo data", () => {
  const provider = demoProvider as unknown as Record<string, (...a: unknown[]) => unknown>;
  const spies = Object.keys(provider).map((k) => vi.spyOn(provider, k));
  afterEach(() => vi.unstubAllGlobals());
  beforeEach(() => spies.forEach((s) => s.mockClear()));

  for (const [name, call] of Object.entries(calls)) {
    it(`${name}: network failure → ApiError, not demo data`, async () => {
      vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
      const err = await call().catch((e: unknown) => e);
      expect(isApiError(err)).toBe(true);
      spies.forEach((s) => expect(s).not.toHaveBeenCalled());
    });

    it(`${name}: HTTP 500 → ApiError, not demo data`, async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
          new Response('{"detail":"boom"}', {
            status: 500,
            headers: { "content-type": "application/json" },
          }),
        ),
      );
      const err = await call().catch((e: unknown) => e);
      expect(isApiError(err)).toBe(true);
      spies.forEach((s) => expect(s).not.toHaveBeenCalled());
    });

    it(`${name}: a 200 with the wrong shape → ApiError (schema mismatch is surfaced, not hidden)`, async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
          new Response('{"unexpected": true}', {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        ),
      );
      const err = await call().catch((e: unknown) => e);
      expect(isApiError(err)).toBe(true);
      spies.forEach((s) => expect(s).not.toHaveBeenCalled());
    });
  }
});
