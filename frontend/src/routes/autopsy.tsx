import { createFileRoute } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Disclaimer,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  SourceTag,
  SuitabilityBadge,
} from "@/components/app/status";
import { MapView, type MapMarker, type MapRoute } from "@/components/app/MapView";
import { RouteComparison } from "@/components/app/RouteComparison";
import { RouteInputs, type RouteInputsValue } from "@/components/app/RouteInputs";
import { SensitivityMeter } from "@/components/app/SensitivityMeter";
import { analyzeAutopsy, runScenario } from "@/lib/api/autopsy.api";
import type { AutopsyResponse, Perturbation, ScenarioResult } from "@/lib/api/types/autopsy";
import { alternativesToMapRoutes, midpoint } from "@/lib/map-data";
import { useOverlayData } from "@/lib/use-overlay-data";

export const Route = createFileRoute("/autopsy")({
  head: () => ({
    meta: [
      { title: "Autopsy Lab — Route Autopsy" },
      {
        name: "description",
        content: "Test how sensitive a route recommendation is to changes in its evidence.",
      },
      { property: "og:title", content: "Autopsy Lab — Route Autopsy" },
      {
        property: "og:description",
        content: "Test how sensitive a route recommendation is to changes in its evidence.",
      },
    ],
  }),
  component: AutopsyLab,
});

type Item = { scenario: ScenarioResult; origin: "suite" | "custom"; key: string };
type Filter = "all" | "changed" | "stable";

function AutopsyLab() {
  const [form, setForm] = useState<RouteInputsValue>({
    origin: "",
    destination: "",
    vehicleId: undefined,
  });
  const [custom, setCustom] = useState<Item[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | undefined>();
  const [filter, setFilter] = useState<Filter>("all");
  const overlay = useOverlayData();

  const analyze = useMutation({
    mutationFn: analyzeAutopsy,
    onSuccess: (r) => {
      setCustom([]);
      const first = r.data.scenarios.find((s) => s.changed) ?? r.data.scenarios[0];
      setSelectedKey(first ? `suite-${first.scenarioId}` : undefined);
      toast.success(
        `Autopsy complete: ${r.data.sensitivity.scenariosChanged} of ${r.data.sensitivity.scenariosTested} changes alter the recommendation`,
      );
    },
  });
  const ready = form.origin !== "" && form.destination !== "" && form.origin !== form.destination;
  const run = () => ready && analyze.mutate({ ...form, includeDefaultSuite: true });
  const data = analyze.data?.data;

  const items: Item[] = useMemo(
    () => [
      ...(data?.scenarios ?? []).map((s) => ({
        scenario: s,
        origin: "suite" as const,
        key: `suite-${s.scenarioId}`,
      })),
      ...custom,
    ],
    [data, custom],
  );
  const selected = items.find((i) => i.key === selectedKey) ?? null;

  return (
    <>
      <PageHeader
        code="02 / AUTOPSY"
        title="Autopsy Lab"
        desc="Re-run the real routing engine on hypothetical changes to its evidence and see whether the recommendation survives. Hypotheticals are never saved."
      />
      <Step n={1} title="Choose route and vehicle">
        <div className="grid max-w-3xl gap-4 rounded border border-border bg-card p-5 sm:grid-cols-3">
          <RouteInputs value={form} onChange={setForm} />
          <div className="sm:col-span-3">
            <Button onClick={run} disabled={analyze.isPending || !ready}>
              {analyze.isPending ? "Analyzing…" : "Run autopsy"}
            </Button>
            {!ready && (
              <span className="ml-3 text-sm text-muted-foreground">
                Select two different locations to begin.
              </span>
            )}
          </div>
        </div>
      </Step>

      {analyze.isPending ? (
        <LoadingState label="Calculating the baseline and re-running the routing engine for every counterfactual…" />
      ) : analyze.isError ? (
        <ErrorState error={analyze.error} onRetry={run} />
      ) : !data ? (
        <EmptyState>
          Run an autopsy to see the baseline, the counterfactual results and the sensitivity score.
        </EmptyState>
      ) : (
        <div className="space-y-10">
          <div className="flex items-center justify-between gap-2">
            <p className="label-mono">Analysis {data.analysisId} · not saved to the database</p>
            <SourceTag source={analyze.data!.source} />
          </div>
          <Baseline data={data} overlay={overlay} />
          <Step n={3} title="Counterfactual scenarios">
            <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
              <ScenarioList
                items={items}
                filter={filter}
                onFilter={setFilter}
                selectedKey={selectedKey}
                onSelect={setSelectedKey}
              />
              <div className="space-y-6">
                <SensitivityMeter sensitivity={data.sensitivity} />
              </div>
            </div>
          </Step>
          <Step n={4} title="Baseline vs revised recommendation">
            {selected ? (
              <ScenarioDetail item={selected} data={data} overlay={overlay} />
            ) : (
              <EmptyState>Select a scenario to compare it with the baseline.</EmptyState>
            )}
          </Step>
          <Step n={5} title="Try your own what-if">
            <WhatIf
              form={form}
              overlay={overlay}
              baselineId={data.baselineRecommendation?.routeId ?? null}
              onResult={(items2) => {
                setCustom((c) => [...c, ...items2]);
                const last = items2[items2.length - 1];
                if (last) setSelectedKey(last.key);
              }}
            />
          </Step>
          <Disclaimer>{data.disclaimer}</Disclaimer>
        </div>
      )}
    </>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section className="mb-8 space-y-3" aria-labelledby={`step-${n}`}>
      <h2 id={`step-${n}`} className="flex items-center gap-3 text-lg font-medium">
        <span className="grid size-6 place-items-center rounded-full border border-primary font-mono text-xs text-primary">
          {n}
        </span>
        {title}
      </h2>
      {children}
    </section>
  );
}

type Overlay = ReturnType<typeof useOverlayData>;

function Baseline({ data, overlay }: { data: AutopsyResponse; overlay: Overlay }) {
  const b = data.baseline;
  const alts = b.route.alternatives;
  const rec = alts.find((a) => a.recommended);
  const routes = useMemo(() => alternativesToMapRoutes(alts), [alts]);
  const markers = useMemo(
    () => [...overlay.defectPins, ...overlay.restrictionPins],
    [overlay.defectPins, overlay.restrictionPins],
  );
  const unvDef = b.unverifiedEvidence.defects.map((d) => String(d["id"] ?? "?"));
  const unvRes = b.unverifiedEvidence.restrictions.map((d) => String(d["id"] ?? "?"));
  return (
    <Step n={2} title="Baseline route and alternatives">
      <div className="grid gap-6 lg:grid-cols-2">
        <MapView
          ariaLabel="Baseline route alternatives"
          network={overlay.segments}
          routes={routes}
          markers={markers}
          tiles={overlay.tiles}
          fitKey={data.analysisId}
          height={340}
        />
        <div className="space-y-3">
          {rec ? (
            <div
              className="rounded border border-primary/40 bg-primary/5 p-4"
              data-testid="baseline-card"
            >
              <p className="label-mono">Baseline recommendation</p>
              <p className="mt-1 font-mono text-sm">{rec.segmentIds.join(" → ")}</p>
              <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
                <span className="font-mono">
                  {rec.durationMin} min · {rec.distanceKm} km
                </span>
                <SuitabilityBadge status={rec.suitabilityStatus} />
                <span className="text-muted-foreground">
                  penalties {b.hazardPenaltySeconds ?? 0} s
                </span>
              </div>
              <p className="mt-2 text-sm text-muted-foreground">{rec.explanation}</p>
            </div>
          ) : (
            <div
              role="alert"
              className="rounded border border-destructive/50 bg-destructive/10 p-4 text-sm"
            >
              The baseline has <strong>no usable route</strong> for this vehicle. Counterfactuals
              show what would make one usable.
            </div>
          )}
          {b.missingVehicleSpecs.length > 0 && (
            <p className="rounded border border-warning/40 bg-warning/10 p-3 text-sm text-warning">
              Unknown vehicle specs: <strong>{b.missingVehicleSpecs.join(", ")}</strong>. They are
              not assumed to fit.
            </p>
          )}
          <div className="rounded border border-border bg-card p-4 text-sm">
            <p className="label-mono mb-1">Unverified evidence on the recommended route</p>
            <p>
              Defects:{" "}
              <span className="font-mono">{unvDef.length ? unvDef.join(", ") : "none"}</span>
            </p>
            <p>
              Restrictions:{" "}
              <span className="font-mono">{unvRes.length ? unvRes.join(", ") : "none"}</span>
            </p>
          </div>
          {b.restrictionWarnings.length > 0 && (
            <ul className="list-disc space-y-1 pl-5 text-sm text-warning">
              {b.restrictionWarnings.map((w, i) => (
                <li key={`${w.message}-${i}`}>{w.message}</li>
              ))}
            </ul>
          )}
          <p className="label-mono">
            {alts.length} alternatives · {b.route.search.candidatesEvaluated} candidates evaluated
          </p>
        </div>
      </div>
    </Step>
  );
}

function ScenarioList({
  items,
  filter,
  onFilter,
  selectedKey,
  onSelect,
}: {
  items: Item[];
  filter: Filter;
  onFilter: (f: Filter) => void;
  selectedKey: string | undefined;
  onSelect: (k: string) => void;
}) {
  const shown = items.filter((i) =>
    filter === "all" ? true : filter === "changed" ? i.scenario.changed : !i.scenario.changed,
  );
  const tabs: Filter[] = ["all", "changed", "stable"];
  return (
    <div className="space-y-2">
      <div role="tablist" aria-label="Filter scenarios" className="flex gap-1">
        {tabs.map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={filter === t}
            onClick={() => onFilter(t)}
            className={`rounded px-3 py-1 text-sm ${filter === t ? "bg-secondary text-primary" : "text-muted-foreground hover:text-foreground"}`}
          >
            {t} (
            {
              items.filter((i) =>
                t === "all" ? true : t === "changed" ? i.scenario.changed : !i.scenario.changed,
              ).length
            }
            )
          </button>
        ))}
      </div>
      <ul className="max-h-[460px] space-y-1.5 overflow-y-auto pr-1" aria-label="Scenarios">
        {shown.length === 0 && (
          <li className="p-3 text-sm text-muted-foreground">No scenarios in this filter.</li>
        )}
        {shown.map(({ scenario: s, key, origin }) => (
          <li key={key}>
            <button
              type="button"
              aria-pressed={selectedKey === key}
              onClick={() => onSelect(key)}
              className={`w-full rounded border p-3 text-left text-sm transition-colors ${selectedKey === key ? "border-primary bg-primary/5" : "border-border bg-card hover:border-primary/50"}`}
            >
              <span className="flex items-start justify-between gap-2">
                <span>{s.description}</span>
                <span
                  className={`label-mono shrink-0 rounded border px-1.5 py-0.5 ${s.skipped ? "" : s.changed ? "border-warning/40 !text-warning" : "border-success/40 !text-success"}`}
                >
                  {s.skipped ? "no-op" : s.changed ? "changes" : "stable"}
                </span>
              </span>
              <span className="label-mono mt-1 block">
                {origin === "custom" ? "your what-if · " : ""}weight {s.weight}
                {s.changed && s.deltaDurationMin != null
                  ? ` · ${s.deltaDurationMin > 0 ? "+" : ""}${s.deltaDurationMin} min`
                  : ""}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

const asStr = (v: unknown) => (typeof v === "string" ? v : undefined);

function ScenarioDetail({
  item,
  data,
  overlay,
}: {
  item: Item;
  data: AutopsyResponse;
  overlay: Overlay;
}) {
  const s = item.scenario;
  const baseRoute = data.baseline.route.alternatives.find((a) => a.recommended) ?? null;
  const { routes, markers } = useMemo(() => {
    const routes: MapRoute[] = [];
    const markers: MapMarker[] = [];
    if (baseRoute)
      routes.push({
        id: "baseline",
        label: "Baseline",
        geometry: baseRoute.geometry,
        kind: s.changed ? "baseline" : "recommended",
      });
    if (s.revisedRoute)
      routes.push({
        id: "revised",
        label: "Revised",
        geometry: s.revisedRoute.geometry,
        kind: "revised",
      });
    const p = s.perturbation;
    const type = asStr(p["type"]);
    if (type === "close_segment") {
      const seg = overlay.segments?.find((x) => x.id === asStr(p["segmentId"]));
      if (seg)
        routes.push({
          id: "closure",
          label: `Hypothetically closed: ${seg.name}`,
          geometry: seg.geometry,
          kind: "rejected",
        });
    }
    const defId =
      type === "resolve_defect"
        ? asStr(p["defectId"])
        : type === "set_evidence_verification" && p["targetKind"] === "defect"
          ? asStr(p["targetId"])
          : undefined;
    const d = defId ? overlay.defectList?.find((x) => x.id === defId) : undefined;
    if (d)
      markers.push({
        id: "perturbed-defect",
        position: [d.latitude, d.longitude],
        kind: "evidence",
        label: `Changed: defect ${d.id}`,
        detail: s.description,
      });
    const resId =
      type === "remove_restriction" || type === "verify_restriction"
        ? asStr(p["restrictionId"])
        : type === "set_evidence_verification" && p["targetKind"] === "restriction"
          ? asStr(p["targetId"])
          : undefined;
    const r = resId ? overlay.restrictionList?.find((x) => x.id === resId) : undefined;
    const seg = r ? overlay.segments?.find((x) => x.id === r.roadSegmentId) : undefined;
    const mid = seg ? midpoint(seg.geometry) : null;
    if (r && mid)
      markers.push({
        id: "perturbed-restriction",
        position: mid,
        kind: "evidence",
        label: `Changed: restriction ${r.id}`,
        detail: s.description,
      });
    return { routes, markers };
  }, [s, baseRoute, overlay.segments, overlay.defectList, overlay.restrictionList]);

  return (
    <div className="space-y-4" data-testid="scenario-detail">
      <div
        className={`rounded border p-4 ${s.changed ? "border-warning/50 bg-warning/5" : "border-success/40 bg-success/5"}`}
      >
        <p className="label-mono">
          {s.changed
            ? "Why the recommendation changed"
            : s.skipped
              ? "No change to inputs"
              : "Why the recommendation stayed stable"}
        </p>
        <p className="mt-1 text-sm" data-testid="scenario-explanation">
          {s.explanation}
        </p>
        {s.notes.map((n) => (
          <p key={n} className="mt-2 text-xs text-muted-foreground">
            {n}
          </p>
        ))}
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <MapView
          ariaLabel="Baseline versus revised recommendation"
          evidenceLabel="Evidence changed in this scenario"
          network={overlay.segments}
          routes={routes}
          markers={markers}
          tiles={overlay.tiles}
          fitKey={item.key}
          height={320}
        />
        <RouteComparison scenario={s} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------- what-if builder

const KINDS = [
  { value: "close_segment", label: "Close a road segment", pick: "segment" },
  { value: "resolve_defect", label: "Resolve a defect", pick: "defect" },
  { value: "remove_restriction", label: "Remove a restriction", pick: "restriction" },
  { value: "verify_restriction", label: "Treat a restriction as verified", pick: "restriction" },
  {
    value: "unverify_restriction",
    label: "Treat a restriction as unverified",
    pick: "restriction",
  },
  { value: "set_vehicle_height", label: "Change vehicle height (m)", pick: "number" },
  { value: "set_vehicle_width", label: "Change vehicle width (m)", pick: "number" },
  { value: "set_vehicle_weight", label: "Change vehicle weight (kg)", pick: "number" },
] as const;

function buildPerturbation(kind: string, value: string): Perturbation | null {
  const v = value.trim();
  if (!v) return null;
  const n = Number(v);
  switch (kind) {
    case "close_segment":
      return { type: "close_segment", segmentId: v };
    case "resolve_defect":
      return { type: "resolve_defect", defectId: v };
    case "remove_restriction":
      return { type: "remove_restriction", restrictionId: v };
    case "verify_restriction":
      return { type: "verify_restriction", restrictionId: v };
    case "unverify_restriction":
      return {
        type: "set_evidence_verification",
        targetKind: "restriction",
        targetId: v,
        status: "unverified",
      };
    case "set_vehicle_height":
      return n > 0 ? { type: "set_vehicle_height", heightM: n } : null;
    case "set_vehicle_width":
      return n > 0 ? { type: "set_vehicle_width", widthM: n } : null;
    case "set_vehicle_weight":
      return n > 0 ? { type: "set_vehicle_weight", weightKg: n } : null;
    default:
      return null;
  }
}

const selectCls = "h-9 w-full rounded-md border border-input bg-background px-3 text-sm";

function WhatIf({
  form,
  overlay,
  baselineId,
  onResult,
}: {
  form: RouteInputsValue;
  overlay: Overlay;
  baselineId: string | null;
  onResult: (i: Item[]) => void;
}) {
  const [kind, setKind] = useState<string>("close_segment");
  const [value, setValue] = useState("");
  const spec = KINDS.find((k) => k.value === kind)!;
  const needsVehicle = spec.pick === "number";
  const m = useMutation({
    mutationFn: runScenario,
    onSuccess: (r) => {
      if ((r.data.baselineRecommendation?.routeId ?? null) !== baselineId)
        toast.warning(
          "The baseline recommendation differs from the analysis above — backend evidence may have changed. Re-run the autopsy.",
        );
      onResult(
        r.data.scenarios.map((s) => ({
          scenario: s,
          origin: "custom" as const,
          key: `custom-${Date.now()}-${s.scenarioId}`,
        })),
      );
      toast.success("What-if scenario complete");
    },
  });
  const pert = buildPerturbation(kind, value);
  const disabled = m.isPending || !pert || (needsVehicle && !form.vehicleId);
  const go = () =>
    pert &&
    m.mutate({
      origin: form.origin,
      destination: form.destination,
      ...(form.vehicleId ? { vehicleId: form.vehicleId } : {}),
      perturbations: [pert],
    });
  return (
    <form
      className="max-w-xl space-y-3 rounded border border-border bg-card p-5"
      onSubmit={(e) => {
        e.preventDefault();
        go();
      }}
    >
      <Label htmlFor="kind">Hypothetical change</Label>
      <select
        id="kind"
        className={selectCls}
        value={kind}
        onChange={(e) => {
          setKind(e.target.value);
          setValue("");
        }}
      >
        {KINDS.map((k) => (
          <option key={k.value} value={k.value}>
            {k.label}
          </option>
        ))}
      </select>
      {spec.pick === "number" ? (
        <>
          <Input
            type="number"
            step="any"
            min="0"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={spec.value === "set_vehicle_weight" ? "e.g. 9000" : "e.g. 3.0"}
            aria-label={spec.label}
            className="font-mono"
          />
          {!form.vehicleId && (
            <p className="text-sm text-warning">
              Select a vehicle in step 1 to test vehicle changes.
            </p>
          )}
        </>
      ) : (
        <select
          aria-label={spec.label}
          className={selectCls}
          value={value}
          onChange={(e) => setValue(e.target.value)}
        >
          <option value="">Select…</option>
          {spec.pick === "segment" &&
            overlay.segments?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.id} — {s.name}
              </option>
            ))}
          {spec.pick === "defect" &&
            overlay.defectList
              ?.filter((d) => d.maintenanceStatus !== "resolved")
              .map((d) => (
                <option key={d.id} value={d.id}>
                  {d.id} — {d.defectType.replace(/_/g, " ")} (sev {d.severity},{" "}
                  {d.verificationStatus})
                </option>
              ))}
          {spec.pick === "restriction" &&
            overlay.restrictionList?.map((r) => (
              <option key={r.id} value={r.id}>
                {r.id} — {r.restrictionType}
                {r.limitValue != null ? ` ${r.limitValue} ${r.unit ?? ""}` : ""} on{" "}
                {r.roadSegmentId} ({r.verificationStatus})
              </option>
            ))}
        </select>
      )}
      <Button type="submit" variant="secondary" disabled={disabled}>
        {m.isPending ? "Running…" : "Run what-if"}
      </Button>
      {m.isError && <ErrorState error={m.error} onRetry={go} />}
    </form>
  );
}
