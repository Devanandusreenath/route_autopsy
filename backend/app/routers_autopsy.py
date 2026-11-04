from __future__ import annotations

from fastapi import APIRouter, HTTPException

from . import route_autopsy
from .compat import DISCLAIMER, RequestError, build_investigation, resolve_request
from .database import get_all, get_one
from .pilot import NODES, SEGMENTS
from .routing import DEFAULT_MAX_CANDIDATES, DEFAULT_MAX_DEPTH
from .schemas import AutopsyAnalyzeRequest, AutopsyResponse, AutopsyScenarioRequest, RouteInvestigationRequest, RouteInvestigationResponse

router = APIRouter()


def _resolve(req: RouteInvestigationRequest):
    try:
        return resolve_request(req.origin, req.destination, req.vehicleId, lambda vid: get_one("vehicles", vid))
    except RequestError as e:
        raise HTTPException(e.status, e.detail)


@router.post("/routes/investigate", response_model=RouteInvestigationResponse, tags=["routes"],
             summary="Single-route investigation (frontend contract) with alternatives preserved")
def investigate_route(req: RouteInvestigationRequest):
    o, d, vehicle = _resolve(req)
    try:
        return build_investigation(o, d, vehicle, get_all("defects"), get_all("restrictions"), avoid_severe=req.avoidSevereDefects,
                                   prefer_surfaces=req.preferBetterSurfaces, max_alternatives=req.maxAlternatives)
    except RequestError as e:
        raise HTTPException(e.status, e.detail)


def _run(req, perturbations, include_suite):
    o, d, vehicle = _resolve(req)
    try:
        return route_autopsy.analyze(o, d, vehicle, get_all("defects"), get_all("restrictions"), avoid_severe=req.avoidSevereDefects,
                                     prefer_surfaces=req.preferBetterSurfaces, max_alternatives=req.maxAlternatives,
                                     perturbations=perturbations, include_default_suite=include_suite)
    except route_autopsy.ScenarioError as e:
        raise HTTPException(422, str(e))
    except RequestError as e:
        raise HTTPException(e.status, e.detail)


@router.post("/autopsy/analyze", response_model=AutopsyResponse, tags=["autopsy"],
             summary="Baseline + default counterfactual suite + sensitivity (read-only)")
def autopsy_analyze(req: AutopsyAnalyzeRequest):
    return _run(req, req.perturbations, req.includeDefaultSuite)


@router.post("/autopsy/scenario", response_model=AutopsyResponse, tags=["autopsy"],
             summary="Run caller-specified hypothetical scenarios against the same baseline (read-only)")
def autopsy_scenario(req: AutopsyScenarioRequest):
    return _run(req, req.perturbations, False)


@router.get("/autopsy/health", tags=["autopsy"])
def autopsy_health():
    return {"status": "ok", "engine": "routing.compute_routes", "graph": {"nodes": len(NODES), "segments": len(SEGMENTS), "illustrative": True},
            "limits": {"maxDepth": DEFAULT_MAX_DEPTH, "maxCandidates": DEFAULT_MAX_CANDIDATES, "maxScenarios": route_autopsy.MAX_SCENARIOS},
            "perturbationTypes": sorted(route_autopsy.WEIGHTS), "weights": route_autopsy.WEIGHTS, "formula": route_autopsy.FORMULA,
            "persistsHypotheticals": False, "disclaimer": DISCLAIMER}
