import type { MapMarker, MapRoute, MapRouteKind } from "@/components/app/MapView";
import type { Defect } from "@/lib/api/types/defects";
import type { NetworkSegment } from "@/lib/api/types/network";
import type { Restriction } from "@/lib/api/types/restrictions";
import type { RouteAlternative } from "@/lib/api/types/routes";

/** Defect markers come straight from GET /defects. Resolved defects are omitted (they no longer affect routing). */
export function defectMarkers(defects: Defect[] = []): MapMarker[] {
  return defects
    .filter((d) => d.maintenanceStatus !== "resolved")
    .map((d) => ({
      id: `defect-${d.id}`,
      position: [d.latitude, d.longitude] as [number, number],
      kind: "defect" as const,
      label: `${d.id} · ${d.defectType.replace(/_/g, " ")} (severity ${d.severity})`,
      detail: `${d.verificationStatus} · ${d.maintenanceStatus}${d.roadSegmentId ? ` · ${d.roadSegmentId}` : ""}${d.description ? ` — ${d.description}` : ""}`,
      severity: d.severity,
      verified: d.verificationStatus === "verified",
    }));
}

/** Point halfway along a polyline (by vertex count), used to place segment-level restriction markers. */
export function midpoint(geometry: [number, number][]): [number, number] | null {
  if (geometry.length === 0) return null;
  if (geometry.length === 1) return geometry[0]!;
  const i = Math.floor((geometry.length - 1) / 2);
  const a = geometry[i]!;
  const b = geometry[i + 1] ?? a;
  return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
}

export function restrictionMarkers(
  restrictions: Restriction[] = [],
  segments: NetworkSegment[] = [],
): MapMarker[] {
  const byId = new Map(segments.map((s) => [s.id, s]));
  const out: MapMarker[] = [];
  restrictions.forEach((r, n) => {
    const seg = byId.get(r.roadSegmentId);
    const mid = seg ? midpoint(seg.geometry) : null;
    if (!mid) return;
    // nudge co-located markers apart so overlapping restrictions on one segment stay clickable
    const jitter = (n % 3) * 0.00012;
    out.push({
      id: `restriction-${r.id}`,
      position: [mid[0] + jitter, mid[1] + jitter],
      kind: "restriction",
      label: `${r.id} · ${r.restrictionType}${r.limitValue != null ? ` ${r.limitValue} ${r.unit ?? ""}` : ""} on ${seg?.name ?? r.roadSegmentId}`,
      detail: `${r.verificationStatus}${r.description ? ` — ${r.description}` : ""}`,
      verified: r.verificationStatus === "verified",
    });
  });
  return out;
}

export function routeKind(a: RouteAlternative): MapRouteKind {
  if (a.recommended) return "recommended";
  return a.suitabilityStatus === "unsuitable" ? "rejected" : "alternative";
}

export function alternativesToMapRoutes(
  alts: RouteAlternative[],
  highlightId?: string,
): MapRoute[] {
  return alts.map((a) => ({
    id: a.routeId,
    label: a.label,
    geometry: a.geometry,
    kind: a.routeId === highlightId && !a.recommended ? "revised" : routeKind(a),
  }));
}
