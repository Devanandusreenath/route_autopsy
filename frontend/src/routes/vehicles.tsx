import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { HelpCircle, Truck } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  SourceTag,
} from "@/components/app/status";
import { VehicleRestrictionsPanel } from "@/components/app/VehicleRestrictionsPanel";
import { vehiclesQuery } from "@/lib/api/vehicles.api";

export const Route = createFileRoute("/vehicles")({
  head: () => ({
    meta: [
      { title: "Vehicle Profiles — Route Autopsy" },
      {
        name: "description",
        content:
          "Browse the vehicle profiles used to investigate routes and see which restrictions apply.",
      },
      { property: "og:title", content: "Vehicle Profiles — Route Autopsy" },
      {
        property: "og:description",
        content:
          "Browse the vehicle profiles used to investigate routes and see which restrictions apply.",
      },
    ],
  }),
  component: Vehicles,
});

const fmt = (v: number | null | undefined, unit: string) =>
  v == null ? "unknown" : `${v} ${unit}`;

function Vehicles() {
  const q = useQuery(vehiclesQuery);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const toggle = (id: string) =>
    setOpen((p) => {
      const n = new Set(p);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  return (
    <>
      <PageHeader
        code="04 / FLEET"
        title="Vehicle Profiles"
        desc="Dimensions and weights drive restriction checks. Unknown values stay unknown — they are never guessed, and never assumed to fit."
      />
      {q.isPending ? (
        <LoadingState label="Loading vehicles…" />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <div className="space-y-4">
          <SourceTag source={q.data.source} />
          {q.data.data.length === 0 ? (
            <EmptyState>No vehicle profiles found.</EmptyState>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {q.data.data.map((v) => (
                <article
                  key={v.id}
                  className="rounded border border-border bg-card p-5"
                  data-testid={`vehicle-${v.id}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <Truck className="size-5 text-primary" />
                      <h2 className="mt-3 font-medium">{v.name}</h2>
                      <p className="text-sm text-muted-foreground">{v.type}</p>
                    </div>
                    <span className="label-mono">{v.id}</span>
                  </div>
                  <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-xs">
                    {[
                      ["length", fmt(v.lengthM, "m"), v.lengthM],
                      ["width", fmt(v.widthM, "m"), v.widthM],
                      ["height", fmt(v.heightM, "m"), v.heightM],
                      ["gross weight", fmt(v.grossVehicleWeightKg, "kg"), v.grossVehicleWeightKg],
                      [
                        "loaded weight",
                        fmt(v.currentLoadedWeightKg, "kg"),
                        v.currentLoadedWeightKg,
                      ],
                    ].map(([k, text, raw]) => (
                      <div key={String(k)} className="contents">
                        <dt className="text-muted-foreground">{k}</dt>
                        <dd className={raw == null ? "text-warning" : ""}>{text}</dd>
                      </div>
                    ))}
                  </dl>
                  {v.unknownSpecs.length > 0 && (
                    <p className="mt-3 flex items-start gap-2 text-xs text-warning">
                      <HelpCircle className="mt-0.5 size-3.5 shrink-0" /> Unknown:{" "}
                      {v.unknownSpecs.join(", ")} — restrictions needing these can't be confirmed.
                    </p>
                  )}
                  <p className="label-mono mt-3">
                    specs: {v.verificationStatus}
                    {v.isIllustrative ? " · illustrative" : ""}
                  </p>
                  {v.notes && <p className="mt-1 text-xs text-muted-foreground">{v.notes}</p>}
                  <div className="mt-4 border-t border-border pt-3">
                    <Button
                      size="sm"
                      variant="outline"
                      aria-expanded={open.has(v.id)}
                      onClick={() => toggle(v.id)}
                    >
                      {open.has(v.id) ? "Hide restriction check" : "Check restrictions"}
                    </Button>
                    {open.has(v.id) && (
                      <div className="mt-3">
                        <VehicleRestrictionsPanel vehicleId={v.id} defaultOpen />
                      </div>
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>
      )}
    </>
  );
}
