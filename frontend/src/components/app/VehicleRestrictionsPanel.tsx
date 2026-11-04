import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, HelpCircle } from "lucide-react";
import { ErrorState, LoadingState } from "@/components/app/status";
import { restrictionCheckQuery } from "@/lib/api/vehicles.api";
import type { RestrictionOutcome } from "@/lib/api/types/vehicles";

const outcomeMeta: Record<RestrictionOutcome, { label: string; cls: string }> = {
  blocks: { label: "blocks (verified)", cls: "text-destructive border-destructive/50" },
  may_block: { label: "may block (unverified)", cls: "text-warning border-warning/40" },
  unknown_spec: { label: "cannot confirm — spec unknown", cls: "text-warning border-warning/40" },
  fits: { label: "fits", cls: "text-success border-success/40" },
  not_applicable: { label: "not applicable", cls: "text-muted-foreground border-border" },
};

/** Every known restriction checked against one vehicle by the backend (same logic as route evaluation). */
export function VehicleRestrictionsPanel({
  vehicleId,
  defaultOpen = false,
}: {
  vehicleId: string;
  defaultOpen?: boolean;
}) {
  const q = useQuery(restrictionCheckQuery(vehicleId));
  if (q.isPending) return <LoadingState label="Checking restrictions…" />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const c = q.data.data;
  return (
    <div className="space-y-3" data-testid="restriction-panel">
      {c.unknownSpecs.length > 0 && (
        <p className="flex items-start gap-2 rounded border border-warning/40 bg-warning/10 p-3 text-sm text-warning">
          <HelpCircle className="mt-0.5 size-4 shrink-0" />
          <span>
            Unknown specifications: <strong>{c.unknownSpecs.join(", ")}</strong>. Unknown values are
            never assumed to fit — restrictions that need them show as “cannot confirm”.
          </span>
        </p>
      )}
      <ul className="flex flex-wrap gap-2" aria-label="Restriction summary">
        {(Object.keys(outcomeMeta) as RestrictionOutcome[])
          .filter((k) => (c.summary[k] ?? 0) > 0)
          .map((k) => (
            <li key={k} className={`label-mono rounded border px-2 py-0.5 ${outcomeMeta[k].cls}`}>
              {c.summary[k]} {outcomeMeta[k].label}
            </li>
          ))}
      </ul>
      <details open={defaultOpen}>
        <summary className="cursor-pointer text-sm text-primary">
          All {c.items.length} restrictions for {c.vehicleName}
        </summary>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="label-mono text-left">
                <th className="pb-2 pr-3 font-normal">Restriction</th>
                <th className="pb-2 pr-3 font-normal">Where</th>
                <th className="pb-2 pr-3 font-normal">Limit</th>
                <th className="pb-2 pr-3 font-normal">Vehicle</th>
                <th className="pb-2 font-normal">Result</th>
              </tr>
            </thead>
            <tbody>
              {c.items.map((i) => (
                <tr key={i.restrictionId} className="border-t border-border align-top">
                  <td className="py-2 pr-3">
                    <span className="font-mono">{i.restrictionId}</span> {i.restrictionType}
                    <span className="block text-xs text-muted-foreground">
                      {i.verificationStatus}
                    </span>
                  </td>
                  <td className="py-2 pr-3">{i.segmentName}</td>
                  <td className="py-2 pr-3 font-mono">
                    {i.limitValue != null ? `${i.limitValue} ${i.unit ?? ""}` : "—"}
                  </td>
                  <td className="py-2 pr-3 font-mono">
                    {i.vehicleValue != null
                      ? `${i.vehicleValue.toFixed(2)} ${i.unit ?? ""}`
                      : "unknown"}
                  </td>
                  <td className="py-2">
                    <span
                      className={`label-mono inline-flex items-center gap-1 rounded border px-2 py-0.5 ${outcomeMeta[i.outcome].cls}`}
                    >
                      {i.outcome === "blocks" && <AlertTriangle className="size-3" />}
                      {outcomeMeta[i.outcome].label}
                    </span>
                    <span className="mt-1 block text-xs text-muted-foreground">{i.message}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
