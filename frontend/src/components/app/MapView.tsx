import { useEffect, useRef, useState } from "react";
import type * as LeafletNS from "leaflet";
import "leaflet/dist/leaflet.css";
import type { NetworkSegment } from "@/lib/api/types/network";

export type MapRouteKind = "recommended" | "baseline" | "revised" | "alternative" | "rejected";

export interface MapRoute {
  id: string;
  label: string;
  /** [lat, lon][] */
  geometry: number[][];
  kind: MapRouteKind;
}

export type MapMarkerKind = "defect" | "restriction" | "evidence" | "node";

export interface MapMarker {
  id: string;
  position: [number, number];
  kind: MapMarkerKind;
  label: string;
  /** Plain-text popup body (rendered as text, never HTML). */
  detail?: string;
  severity?: number;
  verified?: boolean;
}

/** Hex values mirror the app palette (amber primary, green success, red destructive). */
const ROUTE_STYLE: Record<
  MapRouteKind,
  { color: string; weight: number; dashArray?: string; opacity: number; label: string }
> = {
  recommended: { color: "#f5b100", weight: 6, opacity: 0.95, label: "Recommended" },
  baseline: {
    color: "#f5b100",
    weight: 6,
    dashArray: "10 8",
    opacity: 0.9,
    label: "Baseline recommendation",
  },
  revised: { color: "#38bdf8", weight: 5, opacity: 0.95, label: "Revised recommendation" },
  alternative: { color: "#94a3b8", weight: 4, opacity: 0.8, label: "Alternative" },
  rejected: {
    color: "#ef4444",
    weight: 3,
    dashArray: "2 7",
    opacity: 0.75,
    label: "Rejected (unsuitable)",
  },
};

function markerStyle(m: MapMarker) {
  if (m.kind === "defect") {
    const sev = m.severity ?? 1;
    const color = sev >= 4 ? "#ef4444" : sev >= 2 ? "#f59e0b" : "#facc15";
    return {
      radius: 5 + sev,
      color: "#0b0f14",
      weight: 1.5,
      fillColor: color,
      fillOpacity: m.verified ? 0.95 : 0.45,
      dashArray: m.verified ? undefined : "3 2",
    };
  }
  if (m.kind === "restriction")
    return { radius: 7, color: "#c084fc", weight: 2, fillColor: "#c084fc", fillOpacity: 0.25 };
  if (m.kind === "evidence")
    return { radius: 9, color: "#38bdf8", weight: 3, fillColor: "#38bdf8", fillOpacity: 0.35 };
  return { radius: 4, color: "#e5e7eb", weight: 1, fillColor: "#0b0f14", fillOpacity: 1 };
}

export interface MapViewProps {
  network?: NetworkSegment[] | undefined;
  routes?: MapRoute[] | undefined;
  markers?: MapMarker[] | undefined;
  /** Draw OpenStreetMap tiles. Disable for synthetic/demo schematics. */
  tiles?: boolean | undefined;
  height?: number | undefined;
  /** Change to re-fit the view to the current content. */
  fitKey?: string | undefined;
  onMapClick?: ((lat: number, lon: number) => void) | undefined;
  /** Legend text for highlighted "evidence" markers (default: the uploaded photo location). */
  evidenceLabel?: string | undefined;
  ariaLabel: string;
}

export function MapView({
  network,
  routes = [],
  markers = [],
  tiles = true,
  height = 380,
  fitKey,
  onMapClick,
  evidenceLabel = "Your photo location",
  ariaLabel,
}: MapViewProps) {
  const el = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<LeafletNS.Map | null>(null);
  const layerRef = useRef<LeafletNS.LayerGroup | null>(null);
  const leafletRef = useRef<typeof LeafletNS | null>(null);
  const clickRef = useRef(onMapClick);
  clickRef.current = onMapClick;
  const [ready, setReady] = useState(false);
  const [tilesFailed, setTilesFailed] = useState(false);
  const lastFit = useRef<string | undefined>(undefined);

  // Create the map once (client only).
  useEffect(() => {
    let cancelled = false;
    let map: LeafletNS.Map | null = null;
    void import("leaflet").then((mod) => {
      const L =
        (mod as { default?: typeof LeafletNS }).default ?? (mod as unknown as typeof LeafletNS);
      if (cancelled || !el.current) return;
      leafletRef.current = L;
      map = L.map(el.current, {
        zoomControl: true,
        attributionControl: true,
        preferCanvas: false,
      }).setView([0, 0], 2);
      if (tiles) {
        let loaded = 0;
        let errored = 0;
        const layer = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
          attribution:
            '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        });
        layer.on("tileload", () => (loaded += 1));
        layer.on("tileerror", () => {
          errored += 1;
          if (loaded === 0 && errored >= 3) setTilesFailed(true);
        });
        layer.addTo(map);
      }
      layerRef.current = L.layerGroup().addTo(map);
      map.on("click", (e: LeafletNS.LeafletMouseEvent) =>
        clickRef.current?.(e.latlng.lat, e.latlng.lng),
      );
      mapRef.current = map;
      setReady(true);
    });
    return () => {
      cancelled = true;
      map?.remove();
      mapRef.current = null;
      layerRef.current = null;
    };
  }, [tiles]);

  // Redraw overlays whenever data changes.
  useEffect(() => {
    const L = leafletRef.current;
    const map = mapRef.current;
    const group = layerRef.current;
    if (!ready || !L || !map || !group) return;
    group.clearLayers();
    const bounds: [number, number][] = [];
    for (const s of network ?? []) {
      L.polyline(s.geometry as [number, number][], {
        color: "#64748b",
        weight: 2,
        opacity: 0.45,
        interactive: false,
        className: "network-line",
      }).addTo(group);
      if (!routes.length) bounds.push(...(s.geometry as [number, number][]));
    }
    // draw widest/least important first so the recommended route ends up on top
    const order: MapRouteKind[] = ["rejected", "alternative", "baseline", "revised", "recommended"];
    for (const kind of order) {
      for (const r of routes.filter((x) => x.kind === kind)) {
        const st = ROUTE_STYLE[kind];
        const line = L.polyline(r.geometry as [number, number][], {
          color: st.color,
          weight: st.weight,
          opacity: st.opacity,
          ...(st.dashArray ? { dashArray: st.dashArray } : {}),
          className: `route-line route-${kind}`,
        }).addTo(group);
        line.bindTooltip(`${r.label} · ${st.label}`, { sticky: true });
        bounds.push(...(r.geometry as [number, number][]));
      }
    }
    for (const m of markers) {
      const c = L.circleMarker(m.position, {
        ...markerStyle(m),
        className: `map-marker marker-${m.kind}`,
      }).addTo(group);
      const pop = document.createElement("div");
      const strong = document.createElement("strong");
      strong.textContent = m.label;
      pop.appendChild(strong);
      if (m.detail) {
        const p = document.createElement("div");
        p.textContent = m.detail; // text only: never inject HTML from data
        pop.appendChild(p);
      }
      c.bindPopup(pop);
      if (m.kind === "evidence" || routes.length === 0) bounds.push(m.position);
    }
    if (bounds.length && lastFit.current !== (fitKey ?? "") + bounds.length) {
      lastFit.current = (fitKey ?? "") + bounds.length;
      map.fitBounds(bounds, { padding: [28, 28], maxZoom: 16 });
    }
  }, [ready, network, routes, markers, fitKey]);

  const kindsShown = [...new Set(routes.map((r) => r.kind))];
  const markerKinds = [...new Set(markers.map((m) => m.kind))].filter((k) => k !== "node");
  return (
    <div className="space-y-2">
      <div className="relative overflow-hidden rounded border border-border">
        <div
          ref={el}
          role="application"
          aria-label={ariaLabel}
          data-testid="route-map"
          data-ready={ready}
          style={{ height }}
          className="route-map w-full bg-card"
        />
        {tilesFailed && (
          <p
            role="status"
            className="absolute right-2 top-2 z-[500] max-w-[70%] rounded border border-warning/40 bg-background/90 px-2 py-1 text-xs text-warning"
          >
            Basemap tiles unavailable (offline?) — showing the road network only.
          </p>
        )}
        {!tiles && (
          <p className="absolute right-2 top-2 z-[500] rounded border border-warning/40 bg-background/90 px-2 py-1 text-xs text-warning">
            Synthetic schematic — no real map.
          </p>
        )}
      </div>
      <ul
        className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground"
        aria-label="Map legend"
      >
        {kindsShown.map((k) => (
          <li key={k} className="flex items-center gap-1.5">
            <svg width="26" height="8" aria-hidden>
              <line
                x1="1"
                y1="4"
                x2="25"
                y2="4"
                stroke={ROUTE_STYLE[k].color}
                strokeWidth="3"
                strokeDasharray={ROUTE_STYLE[k].dashArray ?? ""}
              />
            </svg>
            {ROUTE_STYLE[k].label}
          </li>
        ))}
        {markerKinds.includes("defect") && (
          <li className="flex items-center gap-1.5">
            <span className="inline-block size-3 rounded-full border border-dashed border-foreground/50 bg-warning/50" />{" "}
            Defect (solid = verified, dashed = unverified; size = severity)
          </li>
        )}
        {markerKinds.includes("restriction") && (
          <li className="flex items-center gap-1.5">
            <span className="inline-block size-3 rounded-full border-2 border-[#c084fc] bg-[#c084fc]/25" />{" "}
            Restriction
          </li>
        )}
        {markerKinds.includes("evidence") && (
          <li className="flex items-center gap-1.5">
            <span className="inline-block size-3 rounded-full border-2 border-[#38bdf8] bg-[#38bdf8]/35" />{" "}
            {evidenceLabel}
          </li>
        )}
      </ul>
    </div>
  );
}
