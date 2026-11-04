// @vitest-environment node
/**
 * LIVE integration test: runs the frontend's real API modules (fetch, Zod validation, error mapping) against a RUNNING backend.
 * Skipped unless LIVE_API=1. Start the backend first, then:
 *
 *   VITE_APP_MODE=backend VITE_API_BASE_URL=http://127.0.0.1:8000 LIVE_API=1 npx vitest run src/test/live-backend.test.ts
 *
 * If the backend has a vision provider configured (META_API_KEY + META_MODEL), the evidence flow runs end to end;
 * otherwise the test asserts the documented "not configured" behaviour instead.
 * Set EXPECT_STUB=1 when the provider is scripts/stub_meta_server.py to also assert its [STUB] output.
 */
import { describe, expect, it } from "vitest";
import { apiConfig } from "@/lib/api/config";
import { isApiError } from "@/lib/api/errors";
import { getNetwork } from "@/lib/api/network.api";
import { listVehicles, getVehicleRestrictionCheck } from "@/lib/api/vehicles.api";
import { listDefects, getDefect } from "@/lib/api/defects.api";
import { listRestrictions } from "@/lib/api/restrictions.api";
import { investigateRoute } from "@/lib/api/routes.api";
import { analyzeAutopsy, runScenario } from "@/lib/api/autopsy.api";
import { analyzeEvidence, confirmEvidence, getEvidenceStatus } from "@/lib/api/evidence.api";

const live = process.env["LIVE_API"] === "1";
const JPEG = new Uint8Array(new ArrayBuffer(204));
JPEG.set([0xff, 0xd8, 0xff, 0xe0]);
const image = (name = "road.jpg", type = "image/jpeg", bytes: Uint8Array<ArrayBuffer> = JPEG) =>
  new File([bytes], name, { type });

describe.skipIf(!live)("frontend API modules against the RUNNING backend", () => {
  it("is in backend mode (never demo) and points at the live server", () => {
    expect(apiConfig.mode).toBe("backend");
    expect(apiConfig.baseUrl).toBeTruthy();
  });

  it("network, vehicles, defects and restrictions load and are tagged 'backend'", async () => {
    const [net, veh, def, res] = await Promise.all([
      getNetwork(),
      listVehicles(),
      listDefects(),
      listRestrictions(),
    ]);
    for (const r of [net, veh, def, res]) expect(r.source).toBe("backend");
    expect(net.data.nodes.length).toBe(10);
    expect(net.data.segments.length).toBe(16);
    expect(veh.data.length).toBe(7);
    expect(def.data.length).toBeGreaterThanOrEqual(15);
    expect(res.data.length).toBe(7);
    const ecomet = veh.data.find((v) => v.id === "veh-ecomet")!;
    expect([ecomet.heightM, ecomet.widthM]).toEqual([3.3, 2.5]);
    expect(veh.data.find((v) => v.id === "veh-bus")!.unknownSpecs).toContain("height");
  });

  it("vehicle restriction check", async () => {
    const r = await getVehicleRestrictionCheck("veh-ecomet");
    expect(r.source).toBe("backend");
    expect(r.data.summary["blocks"]).toBe(3);
    await expect(getVehicleRestrictionCheck("nope")).rejects.toMatchObject({
      category: "not_found",
      status: 404,
    });
  });

  it("route investigation (id and name accepted), alternatives, rejection reasons", async () => {
    const byId = await investigateRoute({
      origin: "FKC",
      destination: "ALV",
      vehicleId: "veh-ecomet",
    });
    const byName = await investigateRoute({
      origin: "Fort Kochi",
      destination: "Aluva",
      vehicleId: "veh-ecomet",
    });
    expect(byId.source).toBe("backend");
    expect(byName.data.routeId).toBe(byId.data.routeId);
    expect(
      byId.data.alternatives.some(
        (a) => a.suitabilityStatus === "unsuitable" && a.rejectionReasons.length > 0,
      ),
    ).toBe(true);
    expect(byId.data.alternatives.filter((a) => a.recommended)).toHaveLength(1);
    const noVehicle = await investigateRoute({ origin: "VYT", destination: "KKD" });
    expect(noVehicle.data.suitabilityStatus).toBe("not_validated");
  });

  it("route errors surface as typed ApiErrors with backend messages", async () => {
    const bad = await investigateRoute({ origin: "Atlantis", destination: "ALV" }).catch((e) => e);
    expect(isApiError(bad)).toBe(true);
    expect(bad).toMatchObject({ category: "validation", status: 422 });
    expect(bad.fieldErrors?.join(" ")).toContain("FKC");
    await expect(
      investigateRoute({ origin: "FKC", destination: "ALV", vehicleId: "nope" }),
    ).rejects.toMatchObject({ category: "not_found" });
    await expect(investigateRoute({ origin: "FKC", destination: "FKC" })).rejects.toMatchObject({
      category: "validation",
    });
  });

  it("autopsy analyze: baseline, scenarios, sensitivity, comparison, nothing persisted", async () => {
    const before = (await listDefects()).data;
    const r = await analyzeAutopsy({
      origin: "VYT",
      destination: "KKD",
      vehicleId: "veh-ecomet",
      includeDefaultSuite: true,
    });
    expect(r.source).toBe("backend");
    expect(r.data.persisted).toBe(false);
    expect(r.data.sensitivity.scenariosTested).toBeGreaterThan(10);
    expect(r.data.sensitivity.sensitivityScore).toBeGreaterThan(0);
    const changed = r.data.scenarios.filter((s) => s.changed);
    expect(changed.length).toBeGreaterThan(0);
    expect(changed.every((s) => s.revisedRoute && s.comparison)).toBe(true);
    expect((await listDefects()).data).toEqual(before); // hypotheticals did not touch stored data
  });

  it("autopsy scenario with each supported perturbation type", async () => {
    const base = { origin: "VYT", destination: "KKD", vehicleId: "veh-ecomet" };
    const r = await runScenario({
      ...base,
      perturbations: [
        { type: "close_segment", segmentId: "S6" },
        { type: "resolve_defect", defectId: "D10" },
        { type: "remove_restriction", restrictionId: "R2" },
        { type: "verify_restriction", restrictionId: "R4" },
        { type: "set_vehicle_height", heightM: 3.0 },
        { type: "set_vehicle_width", widthM: 2.2 },
        { type: "set_vehicle_weight", weightKg: 9000 },
        {
          type: "set_evidence_verification",
          targetKind: "restriction",
          targetId: "R1",
          status: "unverified",
        },
      ],
    });
    expect(r.data.scenarios).toHaveLength(8);
    expect(r.data.scenarios[0]!.changed).toBe(true);
    await expect(
      runScenario({ ...base, perturbations: [{ type: "close_segment", segmentId: "S99" }] }),
    ).rejects.toMatchObject({ category: "validation" });
  });

  it("evidence: status, analyze, confirm, re-read the stored report", async () => {
    const status = await getEvidenceStatus();
    expect(status.source).toBe("backend");
    if (!status.data.configured) {
      // documented behaviour without credentials: validation first (415), then 503
      await expect(analyzeEvidence({ file: image() })).rejects.toMatchObject({
        status: 503,
        category: "server",
      });
      return;
    }
    const a = await analyzeEvidence({
      file: image(),
      latitude: 10.0,
      longitude: 76.3,
      notes: "live test",
    });
    expect(a.source).toBe("backend");
    expect(a.data.observations.length).toBeGreaterThan(0);
    expect(a.data.observations.every((o) => o.verificationStatus === "unverified")).toBe(true);
    expect(a.data.location.status).toBe("user_provided");
    if (process.env["EXPECT_STUB"] === "1") {
      expect(a.data.model).toBe("stub-not-meta-model");
      expect(a.data.observations.every((o) => o.description.startsWith("[STUB"))).toBe(true);
    }
    const defectObs = a.data.observations.find((o) => o.candidateCategory === "defect")!;
    const restrictionObs = a.data.observations.find(
      (o) => o.candidateCategory === "restriction_candidate",
    );
    const ids = [defectObs.id, ...(restrictionObs ? [restrictionObs.id] : [])];
    const c = await confirmEvidence({
      evidenceId: a.data.evidenceId,
      confirmedObservationIds: ids,
      severityOverrides: { [defectObs.id]: 3 },
    });
    const created = c.data.results.find((r) => r.outcome === "defect_created")!;
    expect(created.defectId).toBeTruthy();
    if (restrictionObs)
      expect(c.data.results.find((r) => r.observationId === restrictionObs.id)!.outcome).toBe(
        "restriction_not_confirmed",
      );
    const stored = await getDefect(created.defectId!);
    expect(stored.data.verificationStatus).toBe("unverified");
    expect(stored.data.userConfirmedObservation).toBe(true);
    expect((await listRestrictions()).data).toHaveLength(7); // an AI observation never becomes a restriction
  });

  it("evidence upload validation errors", async () => {
    await expect(
      analyzeEvidence({ file: image("a.txt", "text/plain", new Uint8Array(new ArrayBuffer(2))) }),
    ).rejects.toMatchObject({ category: "validation" }); // client-side check
    await expect(
      confirmEvidence({ evidenceId: "EV-NOPE", confirmedObservationIds: [] }),
    ).rejects.toMatchObject({ category: "not_found" });
  });
});
