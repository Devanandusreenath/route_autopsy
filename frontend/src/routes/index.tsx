import { createFileRoute } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Disclaimer,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  SourceTag,
  SuitabilityBadge,
  riskClass,
} from "@/components/app/status";
import { MapView } from "@/components/app/MapView";
import { RouteInputs, type RouteInputsValue } from "@/components/app/RouteInputs";
import { VehicleRestrictionsPanel } from "@/components/app/VehicleRestrictionsPanel";
import { investigateRoute } from "@/lib/api/routes.api";
import { alternativesToMapRoutes } from "@/lib/map-data";
import { useOverlayData } from "@/lib/use-overlay-data";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Route Investigation — Route Autopsy" },
      {
        name: "description",
        content:
          "Investigate a route segment by segment, with vehicle-aware suitability and alternatives.",
      },
      { property: "og:title", content: "Route Investigation — Route Autopsy" },
      {
        property: "og:description",
        content:
          "Investigate a route segment by segment, with vehicle-aware suitability and alternatives.",
      },
    ],
  }),
  component: RouteInvestigation,
});

function RouteInvestigation() {
  const [form, setForm] = useState<RouteInputsValue>({
    origin: "",
    destination: "",
    vehicleId: undefined,
  });
  const [selected, setSelected] = useState<string | undefined>();
  const [showDefects, setShowDefects] = useState(true);
  const [showRestrictions, setShowRestrictions] = useState(true);
  const overlay = useOverlayData();
  const m = useMutation({
    mutationFn: investigateRoute,
    onSuccess: (r) => {
      setSelected(undefined);
      toast.success(
        r.data.recommended ? "Route investigated" : "No usable route found for this vehicle",
      );
    },
  });
  const ready = form.origin !== "" && form.destination !== "" && form.origin !== form.destination;
  const data = m.data?.data;
  const mapRoutes = useMemo(
    () => (data ? alternativesToMapRoutes(data.alternatives, selected) : []),
    [data, selected],
  );
  const markers = useMemo(
    () => [
      ...(showDefects ? overlay.defectPins : []),
      ...(showRestrictions ? overlay.restrictionPins : []),
    ],
    [showDefects, showRestrictions, overlay.defectPins, overlay.restrictionPins],
  );
  const shown = data?.alternatives.find((a) => a.routeId === (selected ?? data.routeId)) ?? null;

  return (
    <>
      <PageHeader
        code="01 / INVESTIGATE"
        title="Route Investigation"
        desc="Pick a route and vehicle to see every evaluated alternative, why each was recommended or rejected, and where the evidence is weak."
      />
      <div className="grid gap-8 lg:grid-cols-[340px_1fr]">
        <div className="space-y-6">
          <form
            className="space-y-4 rounded border border-border bg-card p-5"
            onSubmit={(e) => {
              e.preventDefault();
              if (ready) m.mutate(form);
            }}
          >
            <RouteInputs value={form} onChange={setForm} />
            {form.origin !== "" && form.origin === form.destination && (
              <p className="text-sm text-destructive">Origin and destination must differ.</p>
            )}
            <Button type="submit" className="w-full" disabled={m.isPending || !ready}>
              {m.isPending ? "Investigating…" : "Investigate route"}
            </Button>
          </form>
          {form.vehicleId && (
            <div className="space-y-2 rounded border border-border bg-card p-5">
              <p className="label-mono">Vehicle restrictions</p>
              <VehicleRestrictionsPanel vehicleId={form.vehicleId} />
            </div>
          )}
        </div>

        <section aria-live="polite">
          {m.isPending ? (
            <LoadingState label="Evaluating every candidate route…" />
          ) : m.isError ? (
            <ErrorState error={m.error} onRetry={() => m.mutate(form)} />
          ) : data ? (
            <div className="space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-mono text-sm">
                  {data.origin} → {data.destination}
                </p>
                <SourceTag source={m.data!.source} />
              </div>
              {data.recommendationStatus === "no_usable_route" && (
                <div
                  role="alert"
                  className="rounded border border-destructive/50 bg-destructive/10 p-4 text-sm"
                >
                  No evaluated route is usable for this vehicle. The least-bad option is shown but
                  is <strong>not recommended</strong>.
                </div>
              )}
              <div className="grid grid-cols-3 gap-3">
                <Stat label="Distance" value={`${data.distanceKm} km`} />
                <Stat label="Duration" value={`${data.durationMin} min`} />
                <div className="rounded border border-border bg-card p-4">
                  <p className="label-mono">Suitability</p>
                  <div className="mt-2">
                    <SuitabilityBadge status={data.suitabilityStatus} />
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex flex-wrap gap-4 text-sm">
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      className="accent-primary"
                      checked={showDefects}
                      onChange={(e) => setShowDefects(e.target.checked)}
                    />{" "}
                    Defects ({overlay.defectPins.length})
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      className="accent-primary"
                      checked={showRestrictions}
                      onChange={(e) => setShowRestrictions(e.target.checked)}
                    />{" "}
                    Restrictions ({overlay.restrictionPins.length})
                  </label>
                </div>
                {overlay.overlaysFailed && (
                  <p role="status" className="text-sm text-warning">
                    Some map overlays (defects or restrictions) could not be loaded.
                  </p>
                )}
                <MapView
                  ariaLabel="Map of route alternatives with defects and restrictions"
                  network={overlay.segments}
                  routes={mapRoutes}
                  markers={markers}
                  tiles={overlay.tiles}
                  fitKey={data.routeId + data.alternatives.length}
                />
              </div>

              <p className="text-sm">{data.explanation}</p>
              {data.missingData.length > 0 && (
                <ul className="list-disc pl-5 text-sm text-warning">
                  {data.missingData.map((x) => (
                    <li key={x}>{x}</li>
                  ))}
                </ul>
              )}

              <div>
                <p className="label-mono mb-2">
                  {data.alternatives.length} alternatives shown · {data.search.candidatesEvaluated}{" "}
                  candidates evaluated{data.search.truncated ? " (search truncated)" : ""} — select
                  one to highlight it on the map
                </p>
                <ul className="space-y-2">
                  {data.alternatives.map((a) => {
                    const active = a.routeId === (selected ?? data.routeId);
                    return (
                      <li key={a.routeId}>
                        <button
                          type="button"
                          aria-pressed={active}
                          onClick={() => setSelected(a.routeId)}
                          className={`w-full rounded border p-4 text-left transition-colors ${active ? "border-primary bg-primary/5" : "border-border bg-card hover:border-primary/50"}`}
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <p className="font-medium">
                              {a.label}
                              {a.recommended && (
                                <span className="label-mono ml-2 !text-primary">recommended</span>
                              )}
                              {a.isFastestCandidate && (
                                <span className="label-mono ml-2">fastest candidate</span>
                              )}
                            </p>
                            <div className="flex items-center gap-3">
                              <span className="font-mono text-sm text-muted-foreground">
                                {a.durationMin} min · {a.distanceKm} km
                              </span>
                              <SuitabilityBadge status={a.suitabilityStatus} />
                            </div>
                          </div>
                          <p className="label-mono mt-1">{a.segmentIds.join(" → ")}</p>
                          <p className="mt-2 text-sm text-muted-foreground">{a.explanation}</p>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>

              {shown && (
                <div>
                  <p className="label-mono mb-2">Segments of {shown.label}</p>
                  <ol className="space-y-2">
                    {shown.segments.map((s, i) => (
                      <li
                        key={s.id}
                        className="flex items-center gap-4 rounded border border-border bg-card p-4"
                      >
                        <span className="font-mono text-muted-foreground">
                          {String(i + 1).padStart(2, "0")}
                        </span>
                        <div className="flex-1">
                          <p className="font-medium">{s.name}</p>
                          {s.note && <p className="text-sm text-muted-foreground">{s.note}</p>}
                        </div>
                        <span className="font-mono text-sm text-muted-foreground">
                          {s.distanceKm} km
                        </span>
                        <span
                          className={`label-mono rounded border px-2 py-0.5 ${riskClass[s.riskLevel]}`}
                        >
                          {s.riskLevel}
                        </span>
                      </li>
                    ))}
                  </ol>
                  {shown.rejectionReasons.length > 0 && (
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-destructive">
                      {shown.rejectionReasons.map((r) => (
                        <li key={r}>{r}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              <Disclaimer>{data.disclaimer}</Disclaimer>
            </div>
          ) : (
            <EmptyState>
              Choose an origin, destination and (optionally) a vehicle, then run an investigation.
            </EmptyState>
          )}
        </section>
      </div>
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-border bg-card p-4">
      <p className="label-mono">{label}</p>
      <p className="mt-1 font-mono text-2xl text-primary">{value}</p>
    </div>
  );
}
