import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { networkResponseSchema } from "@/lib/api/types/network";
import { vehicleListResponseSchema, vehicleRestrictionCheckSchema } from "@/lib/api/types/vehicles";
import { defectListSchema, defectSchema } from "@/lib/api/types/defects";
import { restrictionListSchema } from "@/lib/api/types/restrictions";
import { routeRequestSchema, routeResponseSchema } from "@/lib/api/types/routes";
import {
  autopsyAnalyzeRequestSchema,
  autopsyAnalyzeResponseSchema,
  autopsyScenarioRequestSchema,
  autopsyScenarioResponseSchema,
} from "@/lib/api/types/autopsy";
import {
  evidenceAnalyzeResponseSchema,
  evidenceConfirmRequestSchema,
  evidenceConfirmResponseSchema,
  evidenceStatusSchema,
} from "@/lib/api/types/evidence";

/**
 * Fixtures are REAL responses captured from the FastAPI backend by
 * backend/scripts/generate_contract_fixtures.py. If the backend contract drifts from
 * the Zod schemas the UI relies on, these tests fail.
 */
const fx = (n: string) =>
  JSON.parse(readFileSync(resolve(__dirname, "fixtures", `${n}.json`), "utf8"));

describe("backend responses satisfy the frontend Zod contracts", () => {
  it("GET /api/meta", () =>
    expect(networkResponseSchema.parse(fx("network")).nodes.length).toBe(10));

  it("GET /vehicles keeps dimensions, weights and verification metadata", () => {
    const list = vehicleListResponseSchema.parse(fx("vehicles"));
    expect(list).toHaveLength(7);
    const ecomet = list.find((v) => v.id === "veh-ecomet")!;
    expect(ecomet.name).toBe("Ashok Leyland Ecomet 2022 1615 HE");
    expect([ecomet.heightM, ecomet.widthM, ecomet.currentLoadedWeightKg]).toEqual([
      3.3, 2.5, 14000,
    ]);
    expect(ecomet.specStatus["currentLoadedWeightKg"]).toBe("user_confirmed");
    const bus = list.find((v) => v.id === "veh-bus")!;
    expect(bus.heightM).toBeNull();
    expect(bus.unknownSpecs).toContain("height");
  });

  it("POST /routes/investigate (with vehicle)", () => {
    const r = routeResponseSchema.parse(fx("route_ecomet"));
    expect(r.recommended).toBe(true);
    expect(
      r.alternatives.some(
        (a) => a.suitabilityStatus === "unsuitable" && a.rejectionReasons.length > 0,
      ),
    ).toBe(true);
    expect(r.vehicle?.id).toBe("veh-ecomet");
  });

  it("POST /routes/investigate (no vehicle)", () => {
    const r = routeResponseSchema.parse(fx("route_no_vehicle"));
    expect(r.suitabilityStatus).toBe("not_validated");
    expect(r.vehicle ?? null).toBeNull();
  });

  it("POST /autopsy/analyze", () => {
    const a = autopsyAnalyzeResponseSchema.parse(fx("autopsy_analyze"));
    expect(a.persisted).toBe(false);
    expect(a.sensitivity.scenariosTested).toBeGreaterThan(10);
    const changed = a.scenarios.find((s) => s.changed)!;
    expect(changed.changedVariables[0]!.variable).toBeTruthy();
    expect(Object.keys(changed.changedVariables[0]!)).toContain("from"); // wire key is "from", not "from_"
  });

  it("POST /autopsy/scenario", () => {
    const a = autopsyScenarioResponseSchema.parse(fx("autopsy_scenario"));
    expect(a.scenarios).toHaveLength(2);
    expect(a.sensitivity.sensitivityScore).toBeCloseTo(1 / 1.5, 3); // close S6 (w=1, changes) + height (w=0.5, no change)
  });

  it("POST /autopsy/analyze with unknown vehicle specs", () => {
    expect(
      autopsyAnalyzeResponseSchema.parse(fx("autopsy_traveller")).baseline.missingVehicleSpecs,
    ).toEqual(["height", "gross vehicle weight"]);
  });

  it("POST /evidence/analyze: every observation is unverified, location is user-provided", () => {
    const e = evidenceAnalyzeResponseSchema.parse(fx("evidence_analyze"));
    expect(e.observations.every((o) => o.verificationStatus === "unverified")).toBe(true);
    expect(e.location.status).toBe("user_provided");
    expect(e.observations[1]!.requiresAuthorizedVerification).toBe(true);
  });

  it("POST /evidence/confirm: defect created, restriction not confirmed", () => {
    const c = evidenceConfirmResponseSchema.parse(fx("evidence_confirm"));
    expect(c.results.map((r) => r.outcome)).toEqual([
      "defect_created",
      "restriction_not_confirmed",
    ]);
  });
});

describe("additional endpoints used by the maps, vehicle page and Evidence Lab", () => {
  it("GET /restrictions and GET /defects", () => {
    expect(restrictionListSchema.parse(fx("restrictions"))).toHaveLength(7);
    const defects = defectListSchema.parse(fx("defects"));
    expect(defects.length).toBeGreaterThanOrEqual(15);
    expect(
      defects.every((d) => typeof d.latitude === "number" && typeof d.longitude === "number"),
    ).toBe(true);
  });
  it("GET /vehicles/{id}/restriction-check", () => {
    const e = vehicleRestrictionCheckSchema.parse(fx("restriction_check_ecomet"));
    expect(e.items.filter((i) => i.outcome === "blocks").map((i) => i.restrictionId)).toEqual([
      "R1",
      "R2",
      "R3",
    ]);
    const t = vehicleRestrictionCheckSchema.parse(fx("restriction_check_traveller"));
    expect(t.unknownSpecs).toEqual(["height", "gross vehicle weight"]);
    expect(t.items.find((i) => i.restrictionId === "R2")!.outcome).toBe("unknown_spec");
  });
  it("GET /evidence/status exposes only non-secret fields", () => {
    const raw = fx("evidence_status");
    expect(evidenceStatusSchema.parse(raw).supportedProvider).toBe(true);
    // the whitelist of keys: nothing credential-shaped can hide in an unexpected field
    expect(Object.keys(raw).sort()).toEqual([
      "acceptedTypes",
      "configured",
      "maxUploadBytes",
      "message",
      "model",
      "provider",
      "supportedProvider",
    ]);
    // the message may *name* the env var for admins, but must never contain a key-like value
    expect(JSON.stringify(raw)).not.toMatch(/sk-[A-Za-z0-9]{8,}|Bearer\s/);
  });
  it("GET /defects/{id} for an evidence-created report: unverified with provenance", () => {
    const d = defectSchema.parse(fx("defect_created"));
    expect(d.verificationStatus).toBe("unverified");
    expect(d.evidenceSource).toBe("image_upload");
    expect(d.userConfirmedObservation).toBe(true);
  });
});

describe("scenario comparison data from the backend", () => {
  it("changed scenarios carry a full revised route and consistent segment diff", () => {
    const a = autopsyAnalyzeResponseSchema.parse(fx("autopsy_analyze"));
    const base = a.baseline.route.alternatives.find((x) => x.recommended)!;
    const changed = a.scenarios.filter((s) => s.changed);
    expect(changed.length).toBeGreaterThan(0);
    for (const s of changed) {
      expect(s.revisedRoute).not.toBeNull();
      expect(s.revisedRoute!.geometry.length).toBeGreaterThan(1);
      expect(s.comparison!.routeIdBefore).toBe(base.routeId);
      expect(
        s.comparison!.segmentsAdded.every(
          (id) => s.revisedRoute!.segmentIds.includes(id) && !base.segmentIds.includes(id),
        ),
      ).toBe(true);
    }
    for (const s of a.scenarios.filter((x) => !x.changed && x.inputChanged))
      expect(s.revisedRoute).toBeNull();
  });
});

describe("frontend requests satisfy what the backend accepts", () => {
  it("route request as sent by the Investigation form", () => {
    expect(
      routeRequestSchema.parse({ origin: "FKC", destination: "ALV", vehicleId: "veh-ecomet" }),
    ).toBeTruthy();
    expect(() => routeRequestSchema.parse({ origin: "", destination: "ALV" })).toThrow();
  });
  it("autopsy requests", () => {
    expect(autopsyAnalyzeRequestSchema.parse({ origin: "VYT", destination: "KKD" })).toBeTruthy();
    expect(
      autopsyScenarioRequestSchema.parse({
        origin: "VYT",
        destination: "KKD",
        perturbations: [{ type: "close_segment", segmentId: "S6" }],
      }),
    ).toBeTruthy();
    expect(() =>
      autopsyScenarioRequestSchema.parse({ origin: "VYT", destination: "KKD", perturbations: [] }),
    ).toThrow();
    expect(() =>
      autopsyScenarioRequestSchema.parse({
        origin: "A",
        destination: "B",
        perturbations: [{ type: "teleport" }],
      }),
    ).toThrow();
  });
  it("evidence confirm request", () => {
    expect(
      evidenceConfirmRequestSchema.parse({
        evidenceId: "EV-1",
        confirmedObservationIds: ["obs-1"],
        severityOverrides: { "obs-1": 3 },
      }),
    ).toBeTruthy();
    expect(() =>
      evidenceConfirmRequestSchema.parse({
        evidenceId: "EV-1",
        confirmedObservationIds: [],
        latitude: 999,
      }),
    ).toThrow();
  });
});
