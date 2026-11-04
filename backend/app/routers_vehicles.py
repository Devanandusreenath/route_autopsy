from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .compat import DISCLAIMER, to_display_vehicle
from .database import get_all, get_one
from .pilot import SEGMENT_BY_ID
from .routing import check_restriction
from .schemas import VehicleRestrictionCheck

router = APIRouter(tags=["vehicles"])


@router.get("/vehicles/{vehicle_id}/restriction-check", response_model=VehicleRestrictionCheck,
            summary="Check every known restriction against one vehicle (same logic as the routing engine)")
def vehicle_restriction_check(vehicle_id: str):
    v = get_one("vehicles", vehicle_id)
    if not v:
        raise HTTPException(404, "Vehicle profile not found")
    disp = to_display_vehicle(v)
    items = []
    for r in sorted(get_all("restrictions"), key=lambda x: x["id"]):
        outcome, val, msg = check_restriction(r, v)
        seg = SEGMENT_BY_ID.get(r["roadSegmentId"], {})
        items.append({"restrictionId": r["id"], "roadSegmentId": r["roadSegmentId"], "segmentName": seg.get("name", r["roadSegmentId"]),
                      "restrictionType": r["restrictionType"], "description": r.get("description", ""), "limitValue": r.get("limitValue"), "unit": r.get("unit"),
                      "verificationStatus": r.get("verificationStatus", "unverified"), "appliesToVehicle": outcome != "not_applicable",
                      "vehicleValue": val, "outcome": outcome, "message": msg})
    summary = {k: sum(1 for i in items if i["outcome"] == k) for k in ("blocks", "may_block", "unknown_spec", "fits", "not_applicable")}
    return {"vehicleId": v["id"], "vehicleName": disp["name"], "unknownSpecs": disp["unknownSpecs"], "summary": summary, "items": items, "disclaimer": DISCLAIMER}
