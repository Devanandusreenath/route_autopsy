import { useQuery } from "@tanstack/react-query";
import { Label } from "@/components/ui/label";
import { networkQuery } from "@/lib/api/network.api";
import { vehiclesQuery } from "@/lib/api/vehicles.api";

export interface RouteInputsValue {
  origin: string;
  destination: string;
  vehicleId?: string | undefined;
}

const selectCls = "h-9 w-full rounded-md border border-input bg-background px-3 text-sm";

/** Origin/destination come from the backend's road graph (node ids), vehicles from GET /vehicles. */
export function RouteInputs({
  value,
  onChange,
}: {
  value: RouteInputsValue;
  onChange: (v: RouteInputsValue) => void;
}) {
  const network = useQuery(networkQuery);
  const vehicles = useQuery(vehiclesQuery);
  const nodes = network.data?.data.nodes ?? [];
  const nodeSelect = (id: string, label: string, key: "origin" | "destination") => (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <select
        id={id}
        className={selectCls}
        value={value[key]}
        disabled={!network.isSuccess}
        onChange={(e) => onChange({ ...value, [key]: e.target.value })}
      >
        <option value="">
          {network.isPending ? "Loading…" : network.isError ? "Locations unavailable" : "Select…"}
        </option>
        {nodes.map((n) => (
          <option key={n.id} value={n.id}>
            {n.name} ({n.id})
          </option>
        ))}
      </select>
    </div>
  );
  return (
    <>
      {nodeSelect("origin", "Origin", "origin")}
      {nodeSelect("dest", "Destination", "destination")}
      <div className="space-y-1.5">
        <Label htmlFor="veh">Vehicle (optional)</Label>
        <select
          id="veh"
          className={selectCls}
          value={value.vehicleId ?? ""}
          onChange={(e) => onChange({ ...value, vehicleId: e.target.value || undefined })}
          disabled={!vehicles.isSuccess}
        >
          <option value="">
            {vehicles.isPending
              ? "Loading…"
              : vehicles.isError
                ? "Vehicles unavailable"
                : "No vehicle (restrictions not checked)"}
          </option>
          {vehicles.data?.data.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
            </option>
          ))}
        </select>
      </div>
    </>
  );
}
