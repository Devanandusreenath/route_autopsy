import { ArrowRight } from "lucide-react";
import { SuitabilityBadge } from "@/components/app/status";
import type { ScenarioResult } from "@/lib/api/types/autopsy";
import type { Suitability } from "@/lib/api/types/routes";

const fmt = (v: number | null | undefined, unit = "", digits = 1) =>
  v == null ? "—" : `${Number(v.toFixed(digits))}${unit}`;
const delta = (
  a: number | null | undefined,
  b: number | null | undefined,
  unit = "",
  digits = 1,
) => {
  if (a == null || b == null) return "—";
  const d = Number((b - a).toFixed(digits));
  return d === 0 ? "no change" : `${d > 0 ? "+" : ""}${d}${unit}`;
};

function Row({
  label,
  before,
  after,
  change,
  tone,
}: {
  label: string;
  before: React.ReactNode;
  after: React.ReactNode;
  change: string;
  tone?: "good" | "bad" | undefined;
}) {
  return (
    <tr className="border-t border-border">
      <th scope="row" className="py-2 pr-3 text-left font-normal text-muted-foreground">
        {label}
      </th>
      <td className="py-2 pr-3 font-mono">{before}</td>
      <td className="py-2 pr-3 font-mono">{after}</td>
      <td
        className={`py-2 font-mono text-xs ${tone === "bad" ? "text-destructive" : tone === "good" ? "text-success" : "text-muted-foreground"}`}
      >
        {change}
      </td>
    </tr>
  );
}

const Status = ({ s }: { s: Suitability | null }) =>
  s ? <SuitabilityBadge status={s} /> : <span className="text-muted-foreground">none</span>;

/** Detailed before/after view for one scenario, using only fields the backend returned. */
export function RouteComparison({ scenario }: { scenario: ScenarioResult }) {
  const c = scenario.comparison;
  if (!c)
    return (
      <p className="text-sm text-muted-foreground">No comparison available for this scenario.</p>
    );
  const stable = !scenario.changed;
  const worse = (a: number | null, b: number | null) =>
    a == null || b == null || a === b ? undefined : b > a ? "bad" : "good";
  return (
    <div className="space-y-4" data-testid="route-comparison">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="label-mono">
          {stable ? "Recommendation stable" : "Recommendation changed"}
        </span>
        <span className="font-mono text-xs text-muted-foreground">{c.routeIdBefore ?? "none"}</span>
        <ArrowRight className="size-3.5 text-muted-foreground" aria-label="becomes" />
        <span className="font-mono text-xs text-muted-foreground">{c.routeIdAfter ?? "none"}</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="label-mono text-left">
              <th className="pb-2 pr-3 font-normal">Metric</th>
              <th className="pb-2 pr-3 font-normal">Baseline</th>
              <th className="pb-2 pr-3 font-normal">
                {stable ? "Same route, hypothetical evidence" : "Revised recommendation"}
              </th>
              <th className="pb-2 font-normal">Change</th>
            </tr>
          </thead>
          <tbody>
            <Row
              label="Suitability"
              before={<Status s={c.suitabilityBefore} />}
              after={<Status s={c.suitabilityAfter} />}
              change={
                c.suitabilityBefore === c.suitabilityAfter
                  ? "no change"
                  : `${c.suitabilityBefore ?? "none"} → ${c.suitabilityAfter ?? "none"}`
              }
            />
            <Row
              label="Duration"
              before={fmt(c.durationMinBefore, " min")}
              after={fmt(c.durationMinAfter, " min")}
              change={delta(c.durationMinBefore, c.durationMinAfter, " min")}
              tone={worse(c.durationMinBefore, c.durationMinAfter)}
            />
            <Row
              label="Distance"
              before={fmt(c.distanceKmBefore, " km", 2)}
              after={fmt(c.distanceKmAfter, " km", 2)}
              change={delta(c.distanceKmBefore, c.distanceKmAfter, " km", 2)}
              tone={worse(c.distanceKmBefore, c.distanceKmAfter)}
            />
            <Row
              label="Severe defects on route"
              before={fmt(c.severeHazardsBefore, "", 0)}
              after={fmt(c.severeHazardsAfter, "", 0)}
              change={delta(c.severeHazardsBefore, c.severeHazardsAfter, "", 0)}
              tone={worse(c.severeHazardsBefore, c.severeHazardsAfter)}
            />
            <Row
              label="Ranking score (lower is better)"
              before={fmt(c.scoreSecondsBefore, " s", 0)}
              after={fmt(c.scoreSecondsAfter, " s", 0)}
              change={delta(c.scoreSecondsBefore, c.scoreSecondsAfter, " s", 0)}
              tone={worse(c.scoreSecondsBefore, c.scoreSecondsAfter)}
            />
            <Row
              label="Lead over runner-up"
              before={fmt(c.baselineMarginSeconds, " s", 0)}
              after={fmt(c.revisedMarginSeconds, " s", 0)}
              change={delta(c.baselineMarginSeconds, c.revisedMarginSeconds, " s", 0)}
            />
          </tbody>
        </table>
      </div>

      <div className="grid gap-3 sm:grid-cols-3 text-sm">
        <SegmentList
          title="Segments dropped"
          ids={c.segmentsRemoved}
          tone="text-destructive line-through"
        />
        <SegmentList title="Segments added" ids={c.segmentsAdded} tone="text-success" />
        <SegmentList title="Segments kept" ids={c.segmentsShared} tone="text-muted-foreground" />
      </div>

      <div>
        <p className="label-mono mb-1">Variables changed in this scenario</p>
        {scenario.changedVariables.length === 0 ? (
          <p className="text-sm text-muted-foreground">None — the input already had this value.</p>
        ) : (
          <ul className="space-y-1">
            {scenario.changedVariables.map((v) => (
              <li key={v.variable} className="font-mono text-xs">
                {v.variable}: <span className="text-muted-foreground">{String(v.from ?? "—")}</span>{" "}
                → <span className="text-primary">{String(v.to ?? "—")}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {(scenario.changedWarnings.added.length > 0 ||
        scenario.changedWarnings.removed.length > 0) && (
        <div className="grid gap-3 sm:grid-cols-2 text-sm">
          <WarningList
            title="New warnings on the baseline route"
            items={scenario.changedWarnings.added}
            tone="text-destructive"
          />
          <WarningList
            title="Warnings that disappear"
            items={scenario.changedWarnings.removed}
            tone="text-success"
          />
        </div>
      )}
    </div>
  );
}

function SegmentList({ title, ids, tone }: { title: string; ids: string[]; tone: string }) {
  return (
    <div>
      <p className="label-mono mb-1">{title}</p>
      {ids.length === 0 ? (
        <p className="text-muted-foreground">—</p>
      ) : (
        <p className={`font-mono ${tone}`}>{ids.join(", ")}</p>
      )}
    </div>
  );
}

function WarningList({ title, items, tone }: { title: string; items: string[]; tone: string }) {
  return (
    <div>
      <p className="label-mono mb-1">{title}</p>
      {items.length === 0 ? (
        <p className="text-muted-foreground">—</p>
      ) : (
        <ul className={`list-disc space-y-1 pl-4 ${tone}`}>
          {items.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
