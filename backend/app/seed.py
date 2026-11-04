from datetime import datetime, timezone, timedelta
from .database import get_all, put_json
from .pilot import point_on_segment

NOW = datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc)

def _spec(status="estimated", overrides=None):
    d={"lengthM":status,"widthM":status,"heightM":status,"grossVehicleWeightKg":status,"currentLoadedWeightKg":"unknown"}
    d.update(overrides or {})
    return d

def vehicle(id,make,model,year,variant,category,length,width,height,gvw,loaded=None,verification="estimated",spec_overrides=None):
    return {"id":id,"make":make,"model":model,"year":year,"variant":variant,"category":category,"lengthM":length,"widthM":width,"heightM":height,"grossVehicleWeightKg":gvw,"currentLoadedWeightKg":loaded,"specStatus":_spec(overrides=spec_overrides),"verificationStatus":verification,"sources":[],"isIllustrative":True,"updatedAt":NOW.isoformat(),"lastVerifiedAt":None}

VEHICLES = [
    vehicle("veh-swift","Maruti Suzuki","Swift",2023,"VXi","small_car",3.86,1.74,1.53,1355),
    vehicle("veh-ecomet","Ashok Leyland","Ecomet",2022,"1615 HE","heavy_truck",8.6,2.5,3.3,16200,14000,spec_overrides={"currentLoadedWeightKg":"user_confirmed"}),
    vehicle("veh-bus","Ashok Leyland","Viking",2021,"City bus","bus",11,2.6,None,16200,spec_overrides={"heightM":"unknown"}),
    vehicle("cat-creta","Hyundai","Creta",2024,"SX","suv",4.33,1.79,1.64,1800),
    vehicle("cat-ace","Tata","Ace Gold",2022,"Petrol CX","lcv",3.8,1.5,1.85,1840),
    vehicle("cat-traveller","Force","Traveller",2023,"26-seater","van",6.5,2.0,None,None,verification="unknown",spec_overrides={"heightM":"unknown","grossVehicleWeightKg":"unknown"}),
    vehicle("cat-activa","Honda","Activa",2024,"6G","motorcycle",1.83,.7,1.16,260),
]

RESTRICTIONS = [
 {"id":"R1","roadSegmentId":"S1","restrictionType":"weight","limitValue":10,"unit":"t","appliesTo":"all","description":"Old bridge load limit (demo record)","source":"Demo dataset — illustrative","verificationStatus":"verified","lastVerifiedAt":"2026-08-14T00:00:00Z"},
 {"id":"R2","roadSegmentId":"S12","restrictionType":"height","limitValue":3.2,"unit":"m","appliesTo":"all","description":"Railway underpass clearance (demo record)","source":"Demo dataset — illustrative","verificationStatus":"verified","lastVerifiedAt":"2026-07-02T00:00:00Z"},
 {"id":"R3","roadSegmentId":"S12","restrictionType":"width","limitValue":2.3,"unit":"m","appliesTo":"all","description":"Narrow carriageway at underpass (demo record)","source":"Demo dataset — illustrative","verificationStatus":"verified","lastVerifiedAt":"2026-07-02T00:00:00Z"},
 {"id":"R4","roadSegmentId":"S16","restrictionType":"access","limitValue":None,"unit":None,"appliesTo":["heavy_truck"],"description":"Reported heavy-vehicle entry ban 08:00–20:00 (unconfirmed)","source":"Community report — unverified","verificationStatus":"unverified","lastVerifiedAt":None},
 {"id":"R5","roadSegmentId":"S2","restrictionType":"length","limitValue":10,"unit":"m","appliesTo":"all","description":"Tight turn near port gate, vehicles over 10 m (unconfirmed)","source":"Community report — unverified","verificationStatus":"unverified","lastVerifiedAt":None},
 {"id":"R6","roadSegmentId":"S15","restrictionType":"weight","limitValue":20,"unit":"t","appliesTo":"all","description":"Culvert load limit (demo record)","source":"Demo dataset — illustrative","verificationStatus":"verified","lastVerifiedAt":"2026-06-20T00:00:00Z"},
 {"id":"R7","roadSegmentId":"S14","restrictionType":"closure","limitValue":None,"unit":None,"appliesTo":"all","description":"Partial closure for drain works, one lane open (demo record)","source":"Demo dataset — illustrative","verificationStatus":"unverified","lastVerifiedAt":None},
]

D_SEEDS = [
 ("D1","S10",.4,"pothole",5,"Deep pothole across left lane, ~40 cm wide. Two-wheelers swerving.","2026-10-07T07:30:00Z","verified","open",9),
 ("D2","S10",.7,"pothole",4,"Cluster of potholes near bus stop.","2026-10-05T10:10:00Z","verified","under_review",6),
 ("D3","S12",.5,"waterlogging",4,"Underpass floods after heavy rain; depth unknown.","2026-10-08T16:00:00Z","unverified","open",3),
 ("D4","S5",.3,"cracked_road",2,"Longitudinal cracks along median.","2026-09-29T09:00:00Z","verified","open",2),
 ("D5","S8",.55,"damaged_surface",3,"Patchwork surface breaking up near metro pillar.","2026-10-03T13:20:00Z","verified","inspected",4),
 ("D6","S13",.5,"pothole",5,"Severe pothole at junction, vehicles braking hard.","2026-10-08T08:45:00Z","verified","open",11),
 ("D7","S16",.35,"damaged_edge",3,"Road edge eroded, shoulder drop of ~15 cm.","2026-09-25T11:00:00Z","unverified","open",1),
 ("D8","S2",.6,"obstruction",2,"Parked containers narrowing the lane.","2026-10-09T06:00:00Z","unverified","open",1),
 ("D9","S4",.45,"pothole",3,"Pothole filled with gravel temporarily.","2026-09-10T08:00:00Z","verified","resolved",5),
 ("D10","S15",.4,"pothole",4,"Two adjoining potholes, one lane affected.","2026-10-06T17:40:00Z","verified","open",7),
 ("D11","S14",.5,"other",2,"Loose manhole cover (old report, never confirmed).","2026-06-02T12:00:00Z","unverified","open",1),
 ("D12","S6",.3,"damaged_surface",2,"Minor ravelling on service road side.","2026-10-02T09:30:00Z","unverified","open",1),
 ("D13","S1",.5,"clearance_issue",3,"Low overhanging cables reported near bridge approach.","2026-10-04T15:00:00Z","unverified","open",2),
 ("D14","S9",.6,"cracked_road",1,"Hairline cracks, low impact.","2026-09-18T10:00:00Z","verified","resolved",2),
 ("D15","S10",.2,"waterlogging",3,"Water pooling after drizzle near temple road.","2026-10-08T05:20:00Z","unverified","open",2),
]

def seed_database():
    if not get_all("vehicles"):
        for v in VEHICLES: put_json("vehicles",v["id"],v)
    if not get_all("restrictions"):
        for r in RESTRICTIONS: put_json("restrictions",r["id"],r)
    if not get_all("defects"):
        for did,sid,t,dtype,severity,description,observed,verified,status,count in D_SEEDS:
            lat,lon=point_on_segment(sid,t)
            observed_dt=datetime.fromisoformat(observed.replace("Z","+00:00"))
            reported=(observed_dt+timedelta(minutes=45)).isoformat().replace("+00:00","Z")
            d={"id":did,"latitude":lat,"longitude":lon,"roadSegmentId":sid,"defectType":dtype,"severity":severity,"description":description,"photoUrl":None,"observedAt":observed,"reportedAt":reported,"verificationStatus":verified,"maintenanceStatus":status,"independentReportCount":count}
            put_json("defects",did,d)
