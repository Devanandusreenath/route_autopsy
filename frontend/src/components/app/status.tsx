import { AlertTriangle, FlaskConical, Loader2, RotateCw, Server } from "lucide-react";
import { Button } from "@/components/ui/button";
import { apiConfig } from "@/lib/api/config";
import { toApiError } from "@/lib/api/errors";
import type { DataSource } from "@/lib/api/types/common";

export function ModeIndicator() {
  if (apiConfig.mode === "demo")
    return (
      <div className="flex items-center gap-2 rounded border border-warning/40 bg-warning/10 px-3 py-1.5 font-mono text-xs text-warning">
        <FlaskConical className="size-3.5" /> DEMO MODE · synthetic data
      </div>
    );
  return (
    <div
      className={`flex items-center gap-2 rounded border px-3 py-1.5 font-mono text-xs ${
        apiConfig.misconfigured
          ? "border-destructive/50 text-destructive"
          : "border-success/40 text-success"
      }`}
    >
      <Server className="size-3.5" />
      {apiConfig.misconfigured ? "BACKEND MODE · no URL set" : `BACKEND · ${apiConfig.baseUrl}`}
    </div>
  );
}

export function SourceTag({ source }: { source: DataSource }) {
  return source === "demo" ? (
    <span className="label-mono rounded border border-warning/40 px-2 py-0.5 !text-warning">
      Synthetic demo data — not AI inference
    </span>
  ) : (
    <span className="label-mono rounded border border-success/40 px-2 py-0.5 !text-success">
      From backend
    </span>
  );
}

export function LoadingState({ label = "Working…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground" role="status">
      <Loader2 className="size-4 animate-spin" /> {label}
    </div>
  );
}

export function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">
      {children}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const e = toApiError(error);
  return (
    <div
      role="alert"
      className="rounded border border-destructive/50 bg-destructive/10 p-4 text-sm"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
        <div className="flex-1 space-y-1">
          <p className="font-medium text-foreground">{e.message}</p>
          <p className="label-mono">
            {e.category}
            {e.status ? ` · HTTP ${e.status}` : ""}
          </p>
          {e.fieldErrors && (
            <ul className="list-disc pl-4 text-muted-foreground">
              {e.fieldErrors.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          )}
        </div>
        {onRetry && e.retryable && (
          <Button size="sm" variant="outline" onClick={onRetry}>
            <RotateCw /> Retry
          </Button>
        )}
      </div>
    </div>
  );
}

export function PageHeader({ code, title, desc }: { code: string; title: string; desc: string }) {
  return (
    <header className="mb-8 border-b border-border pb-6">
      <p className="label-mono">{code}</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-2 max-w-2xl text-muted-foreground">{desc}</p>
    </header>
  );
}

export const riskClass = {
  low: "text-success border-success/40",
  medium: "text-warning border-warning/40",
  high: "text-destructive border-destructive/50",
} as const;

const suitabilityClass = {
  suitable: "text-success border-success/40",
  warning: "text-warning border-warning/40",
  not_validated: "text-muted-foreground border-border",
  unsuitable: "text-destructive border-destructive/50",
} as const;

export function SuitabilityBadge({ status }: { status: keyof typeof suitabilityClass }) {
  return (
    <span className={`label-mono rounded border px-2 py-0.5 ${suitabilityClass[status]}`}>
      {status.replace("_", " ")}
    </span>
  );
}

export function Disclaimer({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded border border-dashed border-border px-3 py-2 text-xs text-muted-foreground">
      {children}
    </p>
  );
}
