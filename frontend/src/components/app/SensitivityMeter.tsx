import type { AutopsyResponse } from "@/lib/api/types/autopsy";

/** Shows the backend's sensitivity score and spells out exactly what it does and does not mean. */
export function SensitivityMeter({ sensitivity }: { sensitivity: AutopsyResponse["sensitivity"] }) {
  const s = sensitivity;
  const score = s.sensitivityScore;
  const pct = score === null ? 0 : Math.round(score * 100);
  const band =
    score === null
      ? "n/a"
      : score === 0
        ? "robust to every tested change"
        : score < 0.25
          ? "mostly stable"
          : score < 0.5
            ? "moderately sensitive"
            : "highly sensitive";
  return (
    <section
      aria-labelledby="sens-h"
      className="space-y-3 rounded border border-border bg-card p-5"
      data-testid="sensitivity"
    >
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 id="sens-h" className="label-mono">
            Sensitivity score
          </h3>
          <p className="font-mono text-4xl text-primary" data-testid="sensitivity-score">
            {score === null ? "n/a" : score.toFixed(2)}
          </p>
        </div>
        <p className="text-sm text-muted-foreground">{band}</p>
      </div>
      <div
        className="h-2 w-full overflow-hidden rounded bg-secondary"
        role="img"
        aria-label={
          score === null ? "No score" : `${pct}% of tested weight changes the recommendation`
        }
      >
        <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
      </div>
      <p className="text-sm">
        <strong>{s.scenariosChanged}</strong> of <strong>{s.scenariosTested}</strong> tested
        hypothetical changes would alter the recommended route
        {s.scenariosSkipped > 0
          ? ` (${s.scenariosSkipped} skipped because the input already had that value)`
          : ""}
        . Weighted: {s.changedWeight} of {s.totalWeight}.
      </p>
      <p
        className="rounded border border-warning/40 bg-warning/10 p-2 text-sm text-warning"
        data-testid="sensitivity-caveat"
      >
        {s.interpretation}
      </p>
      <details className="text-sm">
        <summary className="cursor-pointer text-primary">What does this score mean?</summary>
        <div className="mt-2 space-y-2 text-muted-foreground">
          <p>
            It measures how <em>fragile the recommendation is</em> to changes in its evidence. Each
            tested change (resolve a defect, verify or remove a restriction, close a road, nudge
            vehicle height/width/weight ±10%) re-runs the same routing engine. Changes that flip the
            recommended route count toward the score; vehicle-spec changes weigh 0.5 because their
            size is arbitrary, evidence changes weigh 1.0.
          </p>
          <p className="font-mono text-xs">{s.formula}</p>
        </div>
      </details>
    </section>
  );
}
