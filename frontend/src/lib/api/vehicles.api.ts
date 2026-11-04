import { queryOptions } from "@tanstack/react-query";
import { request } from "./client";
import { isDemoMode } from "./config";
import { endpoints } from "./endpoints";
import type { ApiResult } from "./types/common";
import {
  vehicleListResponseSchema,
  vehicleRestrictionCheckSchema,
  type Vehicle,
  type VehicleRestrictionCheck,
} from "./types/vehicles";
import { demoProvider } from "@/lib/demo/provider";

export async function listVehicles(): Promise<ApiResult<Vehicle[]>> {
  if (isDemoMode()) return { data: await demoProvider.listVehicles(), source: "demo" };
  const data = await request({
    method: "GET",
    path: endpoints.vehicles,
    responseSchema: vehicleListResponseSchema,
  });
  return { data, source: "backend" };
}

export const vehiclesQuery = queryOptions({
  queryKey: ["vehicles"],
  queryFn: listVehicles,
  retry: false,
});

export async function getVehicleRestrictionCheck(
  vehicleId: string,
): Promise<ApiResult<VehicleRestrictionCheck>> {
  if (isDemoMode())
    return { data: await demoProvider.vehicleRestrictionCheck(vehicleId), source: "demo" };
  const data = await request({
    method: "GET",
    path: endpoints.vehicleRestrictionCheck(vehicleId),
    responseSchema: vehicleRestrictionCheckSchema,
  });
  return { data, source: "backend" };
}

export const restrictionCheckQuery = (vehicleId: string) =>
  queryOptions({
    queryKey: ["vehicle-restriction-check", vehicleId],
    queryFn: () => getVehicleRestrictionCheck(vehicleId),
    retry: false,
  });
