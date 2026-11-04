import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { defectsQuery } from "@/lib/api/defects.api";
import { networkQuery } from "@/lib/api/network.api";
import { restrictionsQuery } from "@/lib/api/restrictions.api";
import { isDemoMode } from "@/lib/api/config";
import { defectMarkers, restrictionMarkers } from "@/lib/map-data";

/** Real network, defect and restriction data (from the backend, or the synthetic provider in demo mode) for map overlays. */
export function useOverlayData() {
  const network = useQuery(networkQuery);
  const defects = useQuery(defectsQuery);
  const restrictions = useQuery(restrictionsQuery);
  const segments = network.data?.data.segments;
  const defectList = defects.data?.data;
  const restrictionList = restrictions.data?.data;
  const defectPins = useMemo(() => defectMarkers(defectList), [defectList]);
  const restrictionPins = useMemo(
    () => restrictionMarkers(restrictionList, segments),
    [restrictionList, segments],
  );
  return {
    network,
    segments,
    defectList,
    restrictionList,
    defectPins,
    restrictionPins,
    overlaysFailed: defects.isError || restrictions.isError,
    tiles: !isDemoMode(),
  };
}
