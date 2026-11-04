"""Illustrative Kochi pilot graph. Geometries and restrictions are demo data, not surveyed facts."""
from math import sin, pi, radians, asin, sqrt, cos

NODES = [
    {"id":"FKC","name":"Fort Kochi","position":[9.9658,76.2421]},
    {"id":"ERS","name":"Ernakulam South","position":[9.969,76.289]},
    {"id":"MGR","name":"MG Road","position":[9.9816,76.282]},
    {"id":"VYT","name":"Vyttila Hub","position":[9.9667,76.3186]},
    {"id":"PLV","name":"Palarivattom","position":[10.003,76.307]},
    {"id":"EDP","name":"Edappally","position":[10.0261,76.3083]},
    {"id":"KLM","name":"Kalamassery","position":[10.053,76.315]},
    {"id":"ALV","name":"Aluva","position":[10.1076,76.3516]},
    {"id":"KKD","name":"Kakkanad","position":[10.0159,76.3419]},
    {"id":"TPR","name":"Thrippunithura","position":[9.945,76.3467]},
]
SEEDS = [
    ("S1","Thoppumpady Old Bridge Rd","Thoppumpady","FKC","ERS",7,"fair",True,.12),
    ("S2","Willingdon Island Rd","Willingdon Island","FKC","MGR",None,"fair",False,-.15),
    ("S3","Chittoor Rd","Ernakulam South","ERS","MGR",9,"good",True,.1),
    ("S4","Sahodaran Ayyappan Rd","Kadavanthra","ERS","VYT",14,"good",True,-.08),
    ("S5","Banerji–Kaloor Rd","Kaloor","MGR","PLV",10,"fair",True,.1),
    ("S6","NH 66 Bypass (Vyttila–Palarivattom)","Vennala","VYT","PLV",18,"good",True,.05),
    ("S7","NH 66 (Palarivattom–Edappally)","Palarivattom","PLV","EDP",16,"good",True,-.06),
    ("S8","NH 544 (Edappally–Kalamassery)","Kalamassery","EDP","KLM",14,"fair",True,.06),
    ("S9","NH 544 (Kalamassery–Aluva)","Aluva","KLM","ALV",14,"good",True,-.05),
    ("S10","Petta–Thrippunithura Rd","Petta","VYT","TPR",10,"poor",True,.1),
    ("S11","Seaport–Airport Rd (South)","Irumpanam","TPR","KKD",12,"good",True,.08),
    ("S12","Thammanam–Kakkanad Link (rail underpass)","Thammanam","VYT","KKD",5.5,"poor",True,-.12),
    ("S13","Civil Line Rd","Padivattom","PLV","KKD",11,"fair",True,.08),
    ("S14","HMT Rd","HMT Colony","KKD","KLM",None,"unknown",False,-.1),
    ("S15","Edappally–Kakkanad Rd","Vazhakkala","EDP","KKD",9,"fair",True,.1),
    ("S16","Seaport–Airport Rd (North)","Thrikkakara North","KKD","ALV",8,"poor",False,.12),
]
NODE_BY_ID = {n["id"]: n for n in NODES}

def curve(a, b, bend):
    pts=[a]
    dlat=b[0]-a[0]; dlng=b[1]-a[1]
    for i in range(1,6):
        t=i/6; off=sin(pi*t)*bend
        pts.append([a[0]+dlat*t-dlng*off, a[1]+dlng*t+dlat*off])
    pts.append(b)
    return pts

SEGMENTS=[]
for sid,name,area,fr,to,width,surface,complete,bend in SEEDS:
    SEGMENTS.append({"id":sid,"name":name,"area":area,"from":fr,"to":to,"widthM":width,"surface":surface,"restrictionDataComplete":complete,"geometry":curve(NODE_BY_ID[fr]["position"],NODE_BY_ID[to]["position"],bend)})
SEGMENT_BY_ID={s["id"]:s for s in SEGMENTS}

def haversine(a,b):
    r=6371000
    lat1,lat2=radians(a[0]),radians(b[0]); dlat=radians(b[0]-a[0]); dlng=radians(b[1]-a[1])
    h=sin(dlat/2)**2+cos(lat1)*cos(lat2)*sin(dlng/2)**2
    return 2*r*asin(sqrt(h))

def segment_length(segment_id):
    g=SEGMENT_BY_ID[segment_id]["geometry"]
    return sum(haversine(g[i-1],g[i]) for i in range(1,len(g)))*1.2

def point_on_segment(segment_id,t):
    g=SEGMENT_BY_ID[segment_id]["geometry"]
    scaled=t*(len(g)-1); i=min(int(scaled),len(g)-2); f=scaled-i
    return [g[i][0]+(g[i+1][0]-g[i][0])*f,g[i][1]+(g[i+1][1]-g[i][1])*f]

def nearest_segment(lat,lon,max_m=700):
    p=[lat,lon]; best=None
    for s in SEGMENTS:
        d=min(haversine(p,g) for g in s["geometry"])
        if best is None or d<best[1]: best=(s["id"],d)
    return best[0] if best and best[1]<=max_m else None
