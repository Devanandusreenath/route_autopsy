from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from itertools import islice
from typing import Any

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import CORS_ORIGINS, SERPAPI_API_KEY, SERPAPI_TIMEOUT_SECONDS
from .database import get_all, get_one, init_db, put_json, connect
from .pilot import NODES, SEGMENTS, SEGMENT_BY_ID, NODE_BY_ID, haversine, segment_length, point_on_segment, nearest_segment
from .schemas import VehicleDisplay, VehicleProfile, VehicleLookupQuery, NewDefectInput, DefectStatusUpdate, RouteRequest, InspectionInput, RepairInput
from .seed import seed_database
from .compat import to_display_vehicle
from .defects import create_defect_record
from .routing import (SURFACE_SPEED, SURFACE_KEYS, STATUS_RANK, CATEGORY_LABEL, RESTRICTION_LABEL, enumerate_paths, oriented_geometry,
                      applies, vehicle_value, evaluate_path, format_duration, route_explanation, compute_routes)
from .routers_autopsy import router as autopsy_router
from .routers_evidence import router as evidence_router
from .routers_vehicles import router as vehicles_router

app = FastAPI(
    title="RouteWise AI API",
    description=(
        "Vehicle-aware routing and road-defect intelligence API. "
        "The included Kochi road graph, restrictions, and seeded defects are illustrative demo data, not surveyed road conditions."
    ),
    version="0.2.0",
)
app.add_middleware(
       CORSMiddleware,
       allow_origins=CORS_ORIGINS,
       allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$",
       allow_credentials=False,
       allow_methods=["*"],
       allow_headers=["*"],
   )

@app.on_event("startup")
def startup():
    init_db()
    seed_database()

@app.get("/")
def root():
    return {"name":"RouteWise AI API","version":"0.2.0","docs":"/docs","demoData":True}

@app.get("/health")
@app.get("/api/health")
def health():
    return {"status":"ok","service":"routewise-api","vehicleLookup":"serpapi" if SERPAPI_API_KEY else "local-catalogue-only","demoRoadNetwork":True}

@app.get("/api/meta")
def meta():
    return {"demoMode":True,"pilotArea":"Kochi, Kerala","warning":"Seeded road geometry, restrictions and defects are illustrative demonstration data, not surveyed or live conditions.","nodes":NODES,"segments":SEGMENTS}

# --------------------------- Vehicles ---------------------------

@app.get("/vehicles", response_model=list[VehicleDisplay])
def list_vehicles():
    items=sorted(get_all("vehicles"), key=lambda x: (x.get("make", ""), x.get("model", ""), x.get("year") or 0))
    return [to_display_vehicle(v) for v in items]  # additive: original profile fields are all retained

@app.get("/vehicles/{vehicle_id}", response_model=VehicleDisplay)
def get_vehicle(vehicle_id: str):
    item=get_one("vehicles",vehicle_id)
    if not item: raise HTTPException(404,"Vehicle profile not found")
    return to_display_vehicle(item)

@app.put("/vehicles")
def save_vehicle(vehicle: VehicleProfile):
    data=vehicle.model_dump()
    data["updatedAt"]=datetime.now(timezone.utc).isoformat()
    put_json("vehicles",data["id"],data)
    return data

@app.delete("/vehicles/{vehicle_id}")
def delete_vehicle(vehicle_id: str):
    from .database import delete_one
    if not get_one("vehicles",vehicle_id): raise HTTPException(404,"Vehicle profile not found")
    delete_one("vehicles",vehicle_id)
    return {"id":vehicle_id,"deleted":True}

@app.post("/vehicles/lookup")
def lookup_vehicles(query: VehicleLookupQuery):
    q=query.model_dump()
    all_profiles=get_all("vehicles")
    # The frontend mock catalogue is represented in the database seed. Filter only supplied values.
    def matches(v):
        for field in ("make","model","variant"):
            val=(q.get(field) or "").strip().lower()
            if val and val not in str(v.get(field) or "").lower(): return False
        if q.get("year") and v.get("year") != q["year"]: return False
        if q.get("category") and v.get("category") != q["category"]: return False
        return True
    local=[v for v in all_profiles if matches(v)]
    if local:
        return local[:20]
    if not SERPAPI_API_KEY:
        return []
    # SerpApi is used only to discover candidate sources. Search snippets are not parsed into specifications.
    terms=" ".join(x for x in [q.get("make"),q.get("model"),str(q.get("year") or ""),q.get("variant"),"official vehicle specifications"] if x)
    try:
        resp=requests.get("https://serpapi.com/search.json",params={"engine":"google","q":terms,"api_key":SERPAPI_API_KEY,"num":5,"gl":"in","hl":"en"},timeout=(5,SERPAPI_TIMEOUT_SECONDS))
        resp.raise_for_status()
        payload=resp.json()
        if payload.get("error"): raise RuntimeError(payload["error"])
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        raise HTTPException(502,f"Vehicle source lookup failed: {exc}") from exc
    results=[]
    for item in payload.get("organic_results",[])[:5]:
        link=item.get("link")
        if not link or not link.startswith(("https://","http://")): continue
        title=str(item.get("title") or "Vehicle specification source")
        results.append({
            "id":"lookup-"+uuid.uuid4().hex[:10],"make":q.get("make") or "Unknown","model":q.get("model") or title[:100],
            "year":q.get("year"),"variant":q.get("variant") or "","category":q.get("category") or "other",
            "lengthM":None,"widthM":None,"heightM":None,"grossVehicleWeightKg":None,"currentLoadedWeightKg":None,
            "specStatus":{"lengthM":"unknown","widthM":"unknown","heightM":"unknown","grossVehicleWeightKg":"unknown","currentLoadedWeightKg":"unknown"},
            "verificationStatus":"unknown","sources":[link],"isIllustrative":False,"updatedAt":datetime.now(timezone.utc).isoformat(),"lastVerifiedAt":None,
            "sourceTitle":title,"sourceSnippet":item.get("snippet","")
        })
    return results

# --------------------------- Defects ---------------------------

@app.get("/defects")
def list_defects(
    status: str | None = None,
    severity_min: int | None = Query(default=None, ge=1, le=5),
    defect_type: str | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
):
    items=get_all("defects")
    if status: items=[d for d in items if d.get("maintenanceStatus")==status]
    if severity_min is not None: items=[d for d in items if d.get("severity",0)>=severity_min]
    if defect_type: items=[d for d in items if d.get("defectType")==defect_type]
    items.sort(key=lambda d:d.get("reportedAt", ""), reverse=True)
    return items[:limit]

@app.post("/defects", status_code=201)
def create_defect(data: NewDefectInput):
    return create_defect_record(data)

@app.get("/defects/{defect_id}")
def get_defect(defect_id: str):
    item=get_one("defects",defect_id)
    if not item: raise HTTPException(404,"Defect report not found")
    return item

@app.patch("/defects/{defect_id}/status")
def update_defect_status(defect_id: str, update: DefectStatusUpdate):
    item=get_one("defects",defect_id)
    if not item: raise HTTPException(404,"Defect report not found")
    item["maintenanceStatus"]=update.status
    item["statusUpdatedAt"]=datetime.now(timezone.utc).isoformat()
    put_json("defects",defect_id,item)
    return {"id":defect_id,"status":update.status}

@app.post("/defects/{defect_id}/confirm")
def confirm_defect(defect_id: str):
    item=get_one("defects",defect_id)
    if not item: raise HTTPException(404,"Defect report not found")
    item["verificationStatus"]="verified"
    item["verifiedAt"]=datetime.now(timezone.utc).isoformat()
    put_json("defects",defect_id,item)
    return item

@app.post("/defects/{defect_id}/resolve")
def resolve_defect(defect_id: str):
    item=get_one("defects",defect_id)
    if not item: raise HTTPException(404,"Defect report not found")
    item["maintenanceStatus"]="resolved"
    item["resolvedAt"]=datetime.now(timezone.utc).isoformat()
    put_json("defects",defect_id,item)
    return item

# --------------------------- Restrictions and road graph ---------------------------

@app.get("/restrictions")
def list_restrictions():
    return get_all("restrictions")

@app.get("/roads/nearby")
def nearby_roads(lat: float=Query(ge=-90,le=90), lon: float=Query(ge=-180,le=180), radius_m: int=Query(default=1000,ge=50,le=10000)):
    found=[]
    for seg in SEGMENTS:
        distance=min(haversine([lat,lon],p) for p in seg["geometry"])
        if distance<=radius_m: found.append({**seg,"distanceMeters":round(distance)})
    return sorted(found,key=lambda x:x["distanceMeters"])

@app.get("/roads/{segment_id}")
def get_road(segment_id: str):
    segment=SEGMENT_BY_ID.get(segment_id)
    if not segment: raise HTTPException(404,"Road segment not found in the pilot dataset")
    return {**segment,"restrictions":[r for r in get_all("restrictions") if r.get("roadSegmentId")==segment_id],"defects":[d for d in get_all("defects") if d.get("roadSegmentId")==segment_id]}

# --------------------------- Routing ---------------------------

# The routing engine now lives in routing.py (pure functions). Names above are re-exported for compatibility.

@app.post("/routes")
def calculate_routes(req: RouteRequest):
    """Legacy contract (unchanged shape): returns a list of evaluated alternatives.
    The Route Autopsy frontend uses POST /routes/investigate (single-route response + alternatives)."""
    if req.originId not in NODE_BY_ID: raise HTTPException(422,f"Unknown origin node: {req.originId}")
    if req.destinationId not in NODE_BY_ID: raise HTTPException(422,f"Unknown destination node: {req.destinationId}")
    if req.originId==req.destinationId: return []
    result=compute_routes(req.originId,req.destinationId,req.vehicle.model_dump() if req.vehicle else None,get_all("defects"),get_all("restrictions"),
                          avoid_severe=req.avoidSevereDefects,prefer_surfaces=req.preferBetterSurfaces)
    return result["routes"]

app.include_router(autopsy_router)
app.include_router(evidence_router)
app.include_router(vehicles_router)

# --------------------------- Maintenance analytics ---------------------------

def priority(defect, now=None):
    if defect.get("maintenanceStatus")=="resolved": return 0
    now=now or datetime.now(timezone.utc)
    try: reported=datetime.fromisoformat(defect.get("reportedAt","").replace("Z","+00:00"))
    except Exception: reported=now
    if reported.tzinfo is None: reported=reported.replace(tzinfo=timezone.utc)
    age=max(0,(now-reported).total_seconds()/86400)
    score=defect.get("severity",1)*13+min(defect.get("independentReportCount",1),8)*3.5
    if defect.get("verificationStatus")=="verified": score+=8
    if defect.get("maintenanceStatus")=="open": score+=min(age/3,8)
    if defect.get("maintenanceStatus")=="inspected": score-=10
    return max(0,min(100,round(score)))

def summary(defects):
    return {"total":len(defects),"open":sum(d.get("maintenanceStatus")=="open" for d in defects),"verified":sum(d.get("verificationStatus")=="verified" for d in defects),"underInspection":sum(d.get("maintenanceStatus")=="under_review" for d in defects),"resolved":sum(d.get("maintenanceStatus")=="resolved" for d in defects),"highPriority":sum(priority(d)>=70 for d in defects)}

@app.get("/maintenance/summary")
def maintenance_summary(): return summary(get_all("defects"))

@app.get("/admin/defects")
def admin_defects(status: str | None=None, severity_min: int | None=Query(default=None,ge=1,le=5)):
    items=get_all("defects")
    if status: items=[d for d in items if d.get("maintenanceStatus")==status]
    if severity_min is not None: items=[d for d in items if d.get("severity",0)>=severity_min]
    return sorted(items,key=lambda d:priority(d),reverse=True)

@app.get("/admin/priority-segments")
def priority_segments():
    defects=get_all("defects"); rows=[]
    for seg in SEGMENTS:
        linked=[d for d in defects if d.get("roadSegmentId")==seg["id"] and d.get("maintenanceStatus")!="resolved"]
        if not linked: continue
        rows.append({"roadSegment":seg,"defectCount":len(linked),"maxSeverity":max(d["severity"] for d in linked),"independentReports":sum(d.get("independentReportCount",1) for d in linked),"priority":round(sum(priority(d) for d in linked)/len(linked)),"openDefects":sum(d.get("maintenanceStatus")=="open" for d in linked)})
    return sorted(rows,key=lambda r:r["priority"],reverse=True)

@app.post("/admin/inspections",status_code=201)
def create_inspection(data: InspectionInput):
    defect=get_one("defects",data.defectId)
    if not defect: raise HTTPException(404,"Defect report not found")
    payload={"id":uuid.uuid4().hex,"defectId":data.defectId,"inspectorId":data.inspectorId,"observedCondition":data.observedCondition,"notes":data.notes,"inspectedAt":data.inspectedAt or datetime.now(timezone.utc).isoformat()}
    with connect() as c: c.execute("INSERT INTO inspections(payload) VALUES(?)",(json.dumps(payload),))
    defect["maintenanceStatus"]="inspected"; put_json("defects",data.defectId,defect)
    return payload

@app.post("/admin/repairs",status_code=201)
def create_repair(data: RepairInput):
    defect=get_one("defects",data.defectId)
    if not defect: raise HTTPException(404,"Defect report not found")
    payload={"id":uuid.uuid4().hex,**data.model_dump()}
    with connect() as c: c.execute("INSERT INTO repairs(payload) VALUES(?)",(json.dumps(payload),))
    # Only mark resolved when an explicit completedAt is supplied; never infer repair from age.
    if data.completedAt:
        defect["maintenanceStatus"]="resolved"; defect["resolvedAt"]=data.completedAt; put_json("defects",data.defectId,defect)
    return payload
