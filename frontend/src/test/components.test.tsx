import { beforeAll, describe, expect, it } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { RouteComparison } from "@/components/app/RouteComparison";
import { SensitivityMeter } from "@/components/app/SensitivityMeter";
import { MapView } from "@/components/app/MapView";
import { autopsyAnalyzeResponseSchema } from "@/lib/api/types/autopsy";
import { networkResponseSchema } from "@/lib/api/types/network";
import { defectListSchema } from "@/lib/api/types/defects";
import { restrictionListSchema } from "@/lib/api/types/restrictions";
import { routeResponseSchema } from "@/lib/api/types/routes";
import {
  alternativesToMapRoutes,
  defectMarkers,
  midpoint,
  restrictionMarkers,
  routeKind,
} from "@/lib/map-data";

const fx = (n: string) =>
  JSON.parse(readFileSync(resolve(__dirname, "fixtures", `${n}.json`), "utf8"));
const analysis = autopsyAnalyzeResponseSchema.parse(fx("autopsy_analyze"));
const changed = analysis.scenarios.find((s) => s.changed)!;
const stable = analysis.scenarios.find(
  (s) => !s.changed && s.inputChanged && s.comparison?.revisedRunnerUp,
)!;

describe("RouteComparison (real backend scenario data)", () => {
  it("changed scenario: shows before/after metrics, dropped/added segments and the changed variable", () => {
    render(<RouteComparison scenario={changed} />);
    const root = screen.getByTestId("route-comparison");
    expect(within(root).getByText(/Recommendation changed/i)).toBeInTheDocument();
    const c = changed.comparison!;
    expect(within(root).getByText(`${c.durationMinBefore} min`)).toBeInTheDocument();
    expect(within(root).getByText(`${c.durationMinAfter} min`)).toBeInTheDocument();
    for (const id of c.segmentsRemoved)
      expect(within(root).getAllByText(new RegExp(id)).length).toBeGreaterThan(0);
    for (const id of c.segmentsAdded)
      expect(within(root).getAllByText(new RegExp(id)).length).toBeGreaterThan(0);
    for (const v of changed.changedVariables)
      expect(
        within(root).getByText(new RegExp(v.variable.replace(/[[\]]/g, "\\$&"))),
      ).toBeInTheDocument();
  });

  it("stable scenario: labelled stable, same route compared under hypothetical evidence", () => {
    render(<RouteComparison scenario={stable} />);
    const root = screen.getByTestId("route-comparison");
    expect(within(root).getByText(/Recommendation stable/i)).toBeInTheDocument();
    expect(within(root).getByText(/Same route, hypothetical evidence/i)).toBeInTheDocument();
    expect(within(root).getByText("Lead over runner-up")).toBeInTheDocument();
  });

  it("renders a graceful message when no comparison exists", () => {
    render(<RouteComparison scenario={{ ...stable, comparison: null }} />);
    expect(screen.getByText(/No comparison available/i)).toBeInTheDocument();
  });
});

describe("SensitivityMeter", () => {
  it("shows the backend score and ALWAYS shows the 'not a probability' caveat without expanding anything", () => {
    render(<SensitivityMeter sensitivity={analysis.sensitivity} />);
    expect(screen.getByTestId("sensitivity-score")).toHaveTextContent(
      analysis.sensitivity.sensitivityScore!.toFixed(2),
    );
    expect(screen.getByTestId("sensitivity-caveat")).toBeVisible();
    expect(screen.getByTestId("sensitivity-caveat")).toHaveTextContent(
      /not an accident probability/i,
    );
    expect(
      screen.getByText(/tested hypothetical changes would alter the recommended route/),
    ).toHaveTextContent(
      `${analysis.sensitivity.scenariosChanged} of ${analysis.sensitivity.scenariosTested}`,
    );
  });

  it("renders n/a (not 0) when nothing was tested", () => {
    render(
      <SensitivityMeter
        sensitivity={{
          ...analysis.sensitivity,
          scenariosTested: 0,
          scenariosChanged: 0,
          sensitivityScore: null,
          totalWeight: 0,
          changedWeight: 0,
        }}
      />,
    );
    expect(screen.getByTestId("sensitivity-score")).toHaveTextContent("n/a");
  });
});

describe("map data helpers", () => {
  const network = networkResponseSchema.parse(fx("network"));
  const defects = defectListSchema.parse(fx("defects"));
  const restrictions = restrictionListSchema.parse(fx("restrictions"));
  const openDefects = defects.filter((d) => d.maintenanceStatus !== "resolved");

  it("defect markers come from API data and skip resolved defects", () => {
    expect(openDefects.length).toBeLessThan(defects.length); // the seed data really does contain resolved defects
    expect(defectMarkers(defects)).toHaveLength(openDefects.length);
    const withResolved = defects.map((d) =>
      d.id === openDefects[0]!.id ? { ...d, maintenanceStatus: "resolved" } : d,
    );
    const pins = defectMarkers(withResolved);
    expect(pins).toHaveLength(openDefects.length - 1);
    expect(pins.every((p) => p.kind === "defect")).toBe(true);
    const d = openDefects[1]!;
    const pin = pins.find((p) => p.id === `defect-${d.id}`)!;
    expect(pin.position).toEqual([d.latitude, d.longitude]);
    expect(pin.verified).toBe(d.verificationStatus === "verified");
  });

  it("restriction markers sit on their segment's midpoint", () => {
    const pins = restrictionMarkers(restrictions, network.segments);
    expect(pins).toHaveLength(restrictions.length);
    const r = restrictions[0]!;
    const seg = network.segments.find((s) => s.id === r.roadSegmentId)!;
    const mid = midpoint(seg.geometry)!;
    const pin = pins.find((p) => p.id === `restriction-${r.id}`)!;
    expect(Math.abs(pin.position[0] - mid[0])).toBeLessThan(0.001);
    expect(Math.abs(pin.position[1] - mid[1])).toBeLessThan(0.001);
  });

  it("midpoint edge cases", () => {
    expect(midpoint([])).toBeNull();
    expect(midpoint([[1, 2]])).toEqual([1, 2]);
    expect(
      midpoint([
        [0, 0],
        [2, 4],
      ]),
    ).toEqual([1, 2]);
  });

  it("alternatives map to route kinds: recommended / alternative / rejected, highlight → revised", () => {
    const r = routeResponseSchema.parse(fx("route_ecomet"));
    const kinds = r.alternatives.map(routeKind);
    expect(kinds.filter((k) => k === "recommended")).toHaveLength(1);
    expect(kinds).toContain("rejected");
    const other = r.alternatives.find(
      (a) => !a.recommended && a.suitabilityStatus !== "unsuitable",
    )!;
    const routes = alternativesToMapRoutes(r.alternatives, other.routeId);
    expect(routes.find((x) => x.id === other.routeId)!.kind).toBe("revised");
  });
});

describe("MapView (Leaflet in jsdom)", () => {
  // jsdom lacks SVG capability detection and layout sizes, so Leaflet would refuse to draw vector layers.
  // Real browsers have both (verified by e2e/e2e.mjs, which counts the drawn route lines).
  beforeAll(() => {
    (window.SVGElement.prototype as unknown as { createSVGRect: () => object }).createSVGRect =
      () => ({});
    Object.defineProperty(HTMLElement.prototype, "clientWidth", {
      configurable: true,
      get: () => 800,
    });
    Object.defineProperty(HTMLElement.prototype, "clientHeight", {
      configurable: true,
      get: () => 400,
    });
  });

  it("creates a map and draws one polyline per route plus markers", async () => {
    const r = routeResponseSchema.parse(fx("route_ecomet"));
    const routes = alternativesToMapRoutes(r.alternatives);
    const { container } = render(
      <MapView
        ariaLabel="test map"
        routes={routes}
        tiles={false}
        markers={[
          {
            id: "m",
            position: r.alternatives[0]!.geometry[0] as [number, number],
            kind: "defect",
            label: "D",
            severity: 4,
          },
        ]}
      />,
    );
    await waitFor(
      () => expect(screen.getByTestId("route-map")).toHaveAttribute("data-ready", "true"),
      { timeout: 5000 },
    );
    await waitFor(() =>
      expect(container.querySelectorAll("path.route-line").length).toBe(routes.length),
    );
    expect(container.querySelectorAll("path.marker-defect")).toHaveLength(1);
    expect(screen.getByLabelText("Map legend")).toHaveTextContent(/Recommended/);
  });
});
