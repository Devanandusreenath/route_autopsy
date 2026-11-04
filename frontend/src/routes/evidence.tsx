import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, Info, ShieldAlert, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Disclaimer,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  SourceTag,
} from "@/components/app/status";
import { MapView, type MapMarker } from "@/components/app/MapView";
import { getDefect } from "@/lib/api/defects.api";
import { analyzeEvidence, confirmEvidence, evidenceStatusQuery } from "@/lib/api/evidence.api";
import {
  ACCEPTED_EVIDENCE_TYPES,
  MAX_EVIDENCE_BYTES,
  type EvidenceConfirmResponse,
  type Observation,
} from "@/lib/api/types/evidence";
import { useOverlayData } from "@/lib/use-overlay-data";

export const Route = createFileRoute("/evidence")({
  head: () => ({
    meta: [
      { title: "Evidence Lab — Route Autopsy" },
      {
        name: "description",
        content:
          "Upload road photos, review AI-suggested candidate observations and confirm what's accurate.",
      },
      { property: "og:title", content: "Evidence Lab — Route Autopsy" },
      {
        property: "og:description",
        content:
          "Upload road photos, review AI-suggested candidate observations and confirm what's accurate.",
      },
    ],
  }),
  component: EvidenceLab,
});

const parseCoord = (s: string, min: number, max: number) => {
  if (s.trim() === "") return undefined;
  const n = Number(s);
  return Number.isFinite(n) && n >= min && n <= max ? n : NaN;
};

function EvidenceLab() {
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [severity, setSeverity] = useState<Record<string, number>>({});
  const overlay = useOverlayData();
  const status = useQuery(evidenceStatusQuery);

  const previewUrl = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(
    () => () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    },
    [previewUrl],
  );

  const confirm = useMutation({
    mutationFn: confirmEvidence,
    onSuccess: (r) => {
      const made = r.data.results.filter((x) => x.outcome === "defect_created").length;
      if (made > 0)
        toast.success(`${made} defect report${made === 1 ? "" : "s"} created (unverified)`);
      else toast.info("No defect reports were created — see the outcome for each observation");
    },
  });
  const analyze = useMutation({
    mutationFn: analyzeEvidence,
    onSuccess: (r) => {
      setSelected(new Set());
      setSeverity(
        Object.fromEntries(
          r.data.observations
            .filter((o) => o.severityEstimate != null)
            .map((o) => [o.id, o.severityEstimate as number]),
        ),
      );
      confirm.reset();
      if (r.data.location.status === "user_provided") {
        setLat(String(r.data.location.latitude ?? ""));
        setLon(String(r.data.location.longitude ?? ""));
      }
      toast.success(
        r.data.observations.length
          ? `${r.data.observations.length} candidate observation(s) — all unverified`
          : "No observations detected in this image",
      );
    },
  });

  const la = parseCoord(lat, -90, 90);
  const lo = parseCoord(lon, -180, 180);
  const coordsInvalid =
    Number.isNaN(la) || Number.isNaN(lo) || (la === undefined) !== (lo === undefined);
  const hasLocation = la !== undefined && lo !== undefined && !coordsInvalid;
  const configured = status.data?.data.configured ?? true;
  const data = analyze.data?.data;
  const lockedLocation = data?.location.status === "user_provided";

  const onFile = (f: File | null) => {
    setFileError(null);
    if (f && !ACCEPTED_EVIDENCE_TYPES.includes(f.type)) {
      setFile(null);
      setFileError("Unsupported file type. Upload a JPEG, PNG or WebP image.");
      return;
    }
    if (f && f.size > MAX_EVIDENCE_BYTES) {
      setFile(null);
      setFileError("That image is larger than 10 MB.");
      return;
    }
    setFile(f);
  };

  const doAnalyze = () =>
    file &&
    !coordsInvalid &&
    analyze.mutate({
      file,
      ...(notes ? { notes } : {}),
      ...(hasLocation ? { latitude: la!, longitude: lo! } : {}),
    });
  const selectedDefects =
    data?.observations.filter((o) => selected.has(o.id) && o.candidateCategory === "defect") ?? [];
  const missingSeverity = selectedDefects.filter((o) => !severity[o.id]);
  const needLocation = selectedDefects.length > 0 && !hasLocation;
  const doConfirm = () =>
    data &&
    confirm.mutate({
      evidenceId: data.evidenceId,
      confirmedObservationIds: [...selected],
      ...(hasLocation ? { latitude: la!, longitude: lo! } : {}),
      severityOverrides: Object.fromEntries(
        selectedDefects.filter((o) => severity[o.id]).map((o) => [o.id, severity[o.id]!]),
      ),
      ...(notes ? { notes } : {}),
    });

  const markers: MapMarker[] = hasLocation
    ? [
        {
          id: "photo",
          position: [la!, lo!],
          kind: "evidence",
          label: "Photo location",
          detail: lockedLocation ? "Supplied at upload" : "Set by you",
        },
      ]
    : [];

  return (
    <>
      <PageHeader
        code="03 / EVIDENCE"
        title="Evidence Lab"
        desc="Upload a road photo. An AI vision model suggests candidate observations. None are verified — review them, add location and severity, and confirm only what you agree with."
      />
      <StatusBanner
        configured={configured}
        loading={status.isPending}
        message={status.data?.data.message}
        model={status.data?.data.model}
        error={status.isError ? status.error : null}
      />

      <div className="grid gap-8 lg:grid-cols-[360px_1fr]">
        <form
          className="space-y-4 self-start rounded border border-border bg-card p-5"
          onSubmit={(e) => {
            e.preventDefault();
            doAnalyze();
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="file">Road photo (JPEG, PNG, WebP · max 10 MB)</Label>
            <Input
              id="file"
              type="file"
              accept={ACCEPTED_EVIDENCE_TYPES.join(",")}
              onChange={(e) => onFile(e.target.files?.[0] ?? null)}
            />
            {fileError && (
              <p role="alert" className="text-sm text-destructive">
                {fileError}
              </p>
            )}
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5">
              <Label htmlFor="lat">Latitude</Label>
              <Input
                id="lat"
                value={lat}
                disabled={lockedLocation}
                onChange={(e) => setLat(e.target.value)}
                placeholder="optional"
                className="font-mono"
                inputMode="decimal"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="lon">Longitude</Label>
              <Input
                id="lon"
                value={lon}
                disabled={lockedLocation}
                onChange={(e) => setLon(e.target.value)}
                placeholder="optional"
                className="font-mono"
                inputMode="decimal"
              />
            </div>
          </div>
          {coordsInvalid && (
            <p role="alert" className="text-sm text-destructive">
              Enter both latitude (−90…90) and longitude (−180…180), or neither.
            </p>
          )}
          <p className="text-xs text-muted-foreground">
            The AI model never infers location. Click the map below to set it, or type coordinates.
            A defect report needs a location.
          </p>
          <MapView
            ariaLabel="Click to set the photo location"
            network={overlay.segments}
            markers={markers}
            tiles={overlay.tiles}
            height={220}
            fitKey={String(hasLocation)}
            onMapClick={
              lockedLocation
                ? undefined
                : (a, b) => {
                    setLat(a.toFixed(5));
                    setLon(b.toFixed(5));
                  }
            }
          />
          <div className="space-y-1.5">
            <Label htmlFor="notes">
              Notes (optional — stored with the report, not sent to the model)
            </Label>
            <Textarea
              id="notes"
              rows={3}
              maxLength={3000}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>
          <Button
            type="submit"
            className="w-full"
            disabled={!file || coordsInvalid || analyze.isPending || !configured}
          >
            {analyze.isPending ? "Analyzing…" : "Analyze photo"}
          </Button>
          {!configured && !status.isPending && (
            <p className="text-xs text-muted-foreground">
              Analysis is disabled until the server is configured.
            </p>
          )}
        </form>

        <section className="space-y-4" aria-live="polite">
          {analyze.isPending ? (
            <LoadingState label="Sending the photo to the vision model and validating its answer…" />
          ) : analyze.isError ? (
            <ErrorState error={analyze.error} onRetry={doAnalyze} />
          ) : data ? (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-mono text-sm">
                  Evidence {data.evidenceId} · {data.modelProvider}/{data.model}
                </p>
                <SourceTag source={analyze.data!.source} />
              </div>
              <div className="grid gap-4 sm:grid-cols-[220px_1fr]">
                {previewUrl && (
                  <figure className="self-start overflow-hidden rounded border border-border bg-card">
                    <img
                      src={previewUrl}
                      alt="The photo you uploaded"
                      className="max-h-64 w-full object-contain"
                      data-testid="evidence-preview"
                    />
                    <figcaption className="label-mono p-2">
                      Your original photo (kept in this browser only)
                    </figcaption>
                  </figure>
                )}
                <div className="space-y-1 text-sm">
                  <p className="flex items-center gap-2 font-medium">
                    <Sparkles className="size-4 text-primary" /> AI candidates — not verified facts
                  </p>
                  <p className="text-muted-foreground">
                    Visual confidence is how clearly the model says it can see something. It is{" "}
                    <strong>not</strong> verification and says nothing about whether it is real,
                    legal or current.
                  </p>
                  <p className="label-mono normal-case" data-testid="location-line">
                    Location:{" "}
                    {data.location.status === "user_provided"
                      ? `${data.location.latitude}, ${data.location.longitude} — supplied by you at upload`
                      : hasLocation
                        ? `${lat}, ${lon} — set by you on the map (sent when you confirm)`
                        : "unknown (set it on the map to create a report)"}
                  </p>
                  {data.imageQuality && (
                    <p className="label-mono normal-case">Image quality: {data.imageQuality}</p>
                  )}
                  {data.duplicateOf && (
                    <p className="text-warning">
                      This exact image was already analyzed ({data.duplicateOf}); it won't count as
                      independent corroboration.
                    </p>
                  )}
                  {data.warnings
                    .filter((w) => !w.includes("already analyzed"))
                    .map((w) => (
                      <p key={w} className="text-warning">
                        {w}
                      </p>
                    ))}
                </div>
              </div>

              {data.observations.length === 0 ? (
                <EmptyState>
                  The model reported no road observations in this image. Nothing to confirm.
                </EmptyState>
              ) : (
                <ul className="space-y-2">
                  {data.observations.map((o) => (
                    <ObservationCard
                      key={o.id}
                      o={o}
                      checked={selected.has(o.id)}
                      severity={severity[o.id]}
                      disabled={confirm.isPending || confirm.isSuccess}
                      onToggle={(c) =>
                        setSelected((prev) => {
                          const n = new Set(prev);
                          if (c) n.add(o.id);
                          else n.delete(o.id);
                          return n;
                        })
                      }
                      onSeverity={(v) => setSeverity((p) => ({ ...p, [o.id]: v }))}
                    />
                  ))}
                </ul>
              )}

              {selected.size > 0 && (
                <div className="space-y-2 rounded border border-border bg-card p-4">
                  {needLocation && (
                    <p role="alert" className="text-sm text-warning">
                      Set a location (map click or coordinates) before confirming a defect report.
                    </p>
                  )}
                  {missingSeverity.length > 0 && (
                    <p role="alert" className="text-sm text-warning">
                      Choose a severity (1–5) for: {missingSeverity.map((o) => o.id).join(", ")}.
                    </p>
                  )}
                  <Button
                    onClick={doConfirm}
                    disabled={
                      confirm.isPending ||
                      confirm.isSuccess ||
                      needLocation ||
                      missingSeverity.length > 0 ||
                      coordsInvalid
                    }
                  >
                    {confirm.isPending
                      ? "Creating reports…"
                      : `Confirm ${selected.size} observation${selected.size === 1 ? "" : "s"} as unverified report${selected.size === 1 ? "" : "s"}`}
                  </Button>
                  <p className="text-xs text-muted-foreground">
                    Confirming says “this matches what I see”. It creates an{" "}
                    <strong>unverified</strong> report; it does not verify anything.
                  </p>
                </div>
              )}
              {confirm.isError && <ErrorState error={confirm.error} onRetry={doConfirm} />}
              {confirm.data && <ConfirmResults data={confirm.data.data} />}
              <Disclaimer>{data.disclaimer}</Disclaimer>
            </>
          ) : (
            <EmptyState>
              Upload a photo and press “Analyze photo”. Your image is shown here next to the model's
              structured observations.
            </EmptyState>
          )}
        </section>
      </div>
    </>
  );
}

function StatusBanner({
  configured,
  loading,
  message,
  model,
  error,
}: {
  configured: boolean;
  loading: boolean;
  message: string | undefined;
  model: string | null | undefined;
  error: unknown;
}) {
  if (loading) return null;
  if (error)
    return (
      <p
        role="status"
        className="mb-6 rounded border border-warning/40 bg-warning/10 p-3 text-sm text-warning"
      >
        Couldn't check whether image analysis is configured. You can still try uploading.
      </p>
    );
  return configured ? (
    <p
      role="status"
      className="mb-6 flex items-center gap-2 rounded border border-success/40 bg-success/5 p-3 text-sm"
    >
      <Info className="size-4 text-success" /> {message}
      {model ? <span className="label-mono ml-2 normal-case">model: {model}</span> : null}
    </p>
  ) : (
    <p
      role="alert"
      className="mb-6 flex items-center gap-2 rounded border border-warning/40 bg-warning/10 p-3 text-sm text-warning"
    >
      <ShieldAlert className="size-4" /> {message}
    </p>
  );
}

function ObservationCard({
  o,
  checked,
  severity,
  disabled,
  onToggle,
  onSeverity,
}: {
  o: Observation;
  checked: boolean;
  severity: number | undefined;
  disabled: boolean;
  onToggle: (c: boolean) => void;
  onSeverity: (v: number) => void;
}) {
  const isDefect = o.candidateCategory === "defect";
  return (
    <li className="rounded border border-border bg-card p-4" data-testid={`obs-${o.id}`}>
      <label className={`flex items-start gap-3 ${isDefect && !disabled ? "cursor-pointer" : ""}`}>
        <input
          type="checkbox"
          className="mt-1 accent-primary"
          disabled={!isDefect || disabled}
          checked={checked}
          onChange={(e) => onToggle(e.target.checked)}
          aria-label={`Confirm ${o.observationType.replace(/_/g, " ")}`}
        />
        <span className="flex-1 space-y-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{o.observationType.replace(/_/g, " ")}</span>
            <span className="label-mono rounded border border-warning/40 px-2 py-0.5 !text-warning">
              AI candidate · unverified
            </span>
            <span className="label-mono">
              visual confidence {(o.visualConfidence * 100).toFixed(0)}% (not verification)
            </span>
          </span>
          <span className="block text-sm text-muted-foreground">{o.description}</span>
          {Object.keys(o.observedAttributes).length > 0 && (
            <span className="label-mono block normal-case">
              observed:{" "}
              {Object.entries(o.observedAttributes)
                .map(([k, v]) => `${k}=${String(v)}`)
                .join("; ")}
            </span>
          )}
          {o.unknownAttributes.length > 0 && (
            <span className="label-mono block normal-case">
              unknown: {o.unknownAttributes.join("; ")}
            </span>
          )}
          {o.discardedModelFields.length > 0 && (
            <span className="label-mono block normal-case">
              backend discarded model-supplied: {o.discardedModelFields.join(", ")}
            </span>
          )}
          {!isDefect && (
            <span className="flex items-start gap-1 text-xs text-warning">
              <ShieldAlert className="mt-0.5 size-3 shrink-0" /> A{" "}
              {o.candidateCategory === "closure_candidate" ? "closure" : "restriction"} candidate.
              It can't be confirmed here and never changes routing; it needs an authorized
              verification workflow.
            </span>
          )}
        </span>
      </label>
      {isDefect && checked && (
        <div className="mt-3 flex flex-wrap items-center gap-2 pl-7">
          <Label htmlFor={`sev-${o.id}`} className="text-xs">
            Severity
            {o.severityEstimate != null
              ? ` (model suggested ${o.severityEstimate})`
              : " (required — none suggested)"}
          </Label>
          <select
            id={`sev-${o.id}`}
            className="h-8 rounded-md border border-input bg-background px-2 text-sm"
            value={severity ?? ""}
            onChange={(e) => onSeverity(Number(e.target.value))}
          >
            <option value="">Select…</option>
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                {n} — {["minor", "low", "moderate", "high", "severe"][n - 1]}
              </option>
            ))}
          </select>
        </div>
      )}
    </li>
  );
}

function ConfirmResults({ data }: { data: EvidenceConfirmResponse }) {
  return (
    <div className="space-y-2" data-testid="confirm-results">
      {data.status === "defects_created" ? (
        <p className="flex items-center gap-2 text-sm text-success">
          <CheckCircle2 className="size-4" /> Result: {data.status.replace(/_/g, " ")}
        </p>
      ) : (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Info className="size-4" /> Result: {data.status.replace(/_/g, " ")} — see each
          observation below
        </p>
      )}
      <ul className="space-y-2">
        {data.results.map((r) => (
          <li key={r.observationId} className="rounded border border-border bg-card p-3 text-sm">
            <p>
              <span className="font-mono">{r.observationId}</span> —{" "}
              <strong>{r.outcome.replace(/_/g, " ")}</strong>
            </p>
            <p className="text-muted-foreground">{r.message}</p>
            {r.defectId && <ReportCard id={r.defectId} />}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Re-reads the created report from the backend so the ID and status shown are the stored ones, not an echo. */
function ReportCard({ id }: { id: string }) {
  const q = useQuery({ queryKey: ["defect", id], queryFn: () => getDefect(id), retry: false });
  if (q.isPending) return <p className="label-mono mt-2">Loading report {id}…</p>;
  if (q.isError)
    return (
      <p className="mt-2 text-sm text-warning">
        Report {id} was created but couldn't be re-read right now.
      </p>
    );
  const d = q.data.data;
  return (
    <dl
      className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 rounded border border-primary/30 bg-primary/5 p-3 font-mono text-xs sm:grid-cols-4"
      data-testid="report-card"
    >
      <div>
        <dt className="text-muted-foreground">Report ID</dt>
        <dd className="text-sm text-primary">{d.id}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground">Verification</dt>
        <dd className={d.verificationStatus === "verified" ? "text-success" : "text-warning"}>
          {d.verificationStatus}
        </dd>
      </div>
      <div>
        <dt className="text-muted-foreground">Maintenance</dt>
        <dd>{d.maintenanceStatus}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground">Type / severity</dt>
        <dd>
          {d.defectType.replace(/_/g, " ")} / {d.severity}
        </dd>
      </div>
    </dl>
  );
}
