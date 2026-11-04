from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from . import config, vision_evidence
from .database import get_all, get_one, put_json
from .defects import create_defect_record
from .meta_model_client import ProviderError, build_client
from .schemas import EvidenceAnalyzeResponse, EvidenceConfirmRequest, EvidenceConfirmResponse, EvidenceStatus, NewDefectInput

router = APIRouter(tags=["evidence"])
log = logging.getLogger("routewise.evidence")

DISCLAIMER = ("Observations are CANDIDATES produced by an AI vision model from a single photo. Visual confidence is not verification. "
              "Nothing here is verified, no location or clearance is inferred, and restrictions can only be verified through an authorized workflow.")


class _LazyVisionClient:
    """Resolves the provider on first use, so upload validation (415/413/422) always runs before
    configuration problems (503) are reported. Provider errors surface inside analyze_image."""

    def __init__(self):
        self._client = None

    def _get(self):
        if self._client is None:
            self._client = build_client()  # may raise ProviderNotConfigured
        return self._client

    @property
    def provider(self):
        return self._get().provider

    @property
    def model(self):
        return self._get().model

    def complete_with_image(self, **kw):
        return self._get().complete_with_image(**kw)


def get_vision_client():
    """FastAPI dependency. Overridden in tests; in production builds the client lazily from environment config."""
    return _LazyVisionClient()


@router.get("/evidence/status", response_model=EvidenceStatus, summary="Is image analysis configured? (never exposes credentials)")
def evidence_status():
    supported = config.META_PROVIDER == "meta_model_api"
    configured = supported and bool(config.META_API_KEY) and bool(config.META_MODEL)
    if not supported:
        msg = f"Unsupported META_PROVIDER '{config.META_PROVIDER}'. Supported: meta_model_api."
    elif configured:
        msg = "Image analysis is configured. Observations are unverified AI candidates."
    else:
        msg = "Image analysis is not configured: set META_API_KEY and META_MODEL on the server."
    return {"configured": configured, "provider": config.META_PROVIDER, "supportedProvider": supported, "model": config.META_MODEL or None,
            "maxUploadBytes": config.EVIDENCE_MAX_UPLOAD_BYTES, "acceptedTypes": sorted(vision_evidence.ALLOWED_MIME), "message": msg}


def _load(evidence_id: str) -> dict:
    rec = get_one("evidence_analyses", evidence_id)
    if not rec:
        raise HTTPException(404, "Evidence analysis not found")
    return rec


def _public(rec: dict) -> dict:
    return {"evidenceId": rec["id"], "createdAt": rec["createdAt"], "modelProvider": rec["modelProvider"], "model": rec["model"], "location": rec["location"],
            "imageQuality": rec.get("imageQuality"), "observations": rec["observations"], "warnings": rec.get("warnings", []),
            "duplicateOf": rec.get("duplicateOf"), "modelExtras": rec.get("modelExtras", {}), "disclaimer": DISCLAIMER}


@router.post("/evidence/analyze", response_model=EvidenceAnalyzeResponse, summary="Analyze a road photo into candidate (unverified) observations")
def evidence_analyze(
    file: UploadFile = File(...),
    notes: str | None = Form(default=None, max_length=3000),
    latitude: float | None = Form(default=None, ge=-90, le=90),
    longitude: float | None = Form(default=None, ge=-180, le=180),
    client=Depends(get_vision_client),
):
    if (latitude is None) != (longitude is None):
        raise HTTPException(422, "Provide both latitude and longitude, or neither.")
    max_bytes = config.EVIDENCE_MAX_UPLOAD_BYTES
    declared = (file.content_type or "").lower()
    if declared not in vision_evidence.ALLOWED_MIME:  # reject before reading the body
        raise HTTPException(415, "Unsupported file type. Upload a JPEG, PNG or WebP image.")
    data = file.file.read(max_bytes + 1)  # never read more than limit+1 bytes into memory
    try:
        mime = vision_evidence.validate_upload(declared, data, max_bytes)
    except vision_evidence.UploadError as e:
        raise HTTPException(e.status, e.message)
    now = datetime.now(timezone.utc).isoformat()
    location_known = latitude is not None
    try:
        parsed = vision_evidence.analyze_image(client, data, mime, observed_at=now, location_known=location_known)
    except ProviderError as e:
        raise HTTPException(e.status, e.public_message)
    except vision_evidence.InvalidModelResponse as e:
        log.warning("invalid model response: %s", e.detail)  # detail never contains image or key material
        raise HTTPException(e.status, e.public_message)
    digest = hashlib.sha256(data).hexdigest()
    earlier = [r for r in get_all("evidence_analyses") if r.get("imageSha256") == digest]
    earlier.sort(key=lambda r: r.get("createdAt", ""))
    location = ({"status": "user_provided", "latitude": latitude, "longitude": longitude, "note": "Location was supplied by the uploader, not inferred from the image."}
                if location_known else {"status": "unknown", "latitude": None, "longitude": None, "note": "Location is unknown. The image model does not provide coordinates."})
    rec = {"id": "EV-" + uuid.uuid4().hex[:10].upper(), "createdAt": now, "imageSha256": digest, "imageMime": mime, "imageBytes": len(data),
           "notes": notes, "location": location, "modelProvider": client.provider, "model": client.model, "imageQuality": parsed["imageQuality"],
           "observations": parsed["observations"], "warnings": parsed["warnings"], "modelExtras": parsed["modelExtras"],
           "duplicateOf": earlier[0]["id"] if earlier else None, "confirmations": {}, "restrictionCandidates": {}}
    if rec["duplicateOf"]:
        rec["warnings"].append(f"This exact image was already analyzed as {rec['duplicateOf']}. It will not count as independent corroboration.")
    put_json("evidence_analyses", rec["id"], rec)  # image bytes are never stored; only the hash and model output
    return _public(rec)


@router.get("/evidence/{evidence_id}", response_model=EvidenceAnalyzeResponse, summary="Retrieve a stored analysis (no image data)")
def evidence_get(evidence_id: str):
    return _public(_load(evidence_id))


@router.post("/evidence/confirm", response_model=EvidenceConfirmResponse,
             summary="User confirms candidate observations; defects go through the existing defect workflow, restrictions are never verified here")
def evidence_confirm(req: EvidenceConfirmRequest):
    rec = _load(req.evidenceId)
    by_id = {o["id"]: o for o in rec["observations"]}
    if req.latitude is not None and req.longitude is not None and rec["location"]["status"] == "unknown":
        rec["location"] = {"status": "user_provided", "latitude": req.latitude, "longitude": req.longitude, "note": "Location was supplied by the user at confirmation, not inferred from the image."}
    elif (req.latitude is None) != (req.longitude is None):
        raise HTTPException(422, "Provide both latitude and longitude, or neither.")
    loc = rec["location"]
    earlier = [r for r in get_all("evidence_analyses") if r.get("imageSha256") == rec.get("imageSha256") and r["id"] != rec["id"] and r.get("createdAt", "") < rec["createdAt"]]
    results = []
    for oid in dict.fromkeys(req.confirmedObservationIds):
        o = by_id.get(oid)
        if o is None:
            results.append({"observationId": oid, "outcome": "unknown_observation", "message": "No such observation in this evidence analysis."})
            continue
        if oid in rec["confirmations"]:
            results.append({"observationId": oid, "outcome": "already_confirmed", "defectId": rec["confirmations"][oid]["defectId"], "verificationStatus": "unverified",
                            "message": "Already confirmed earlier; no new report was created."})
            continue
        cat = o["candidateCategory"]
        if cat in ("restriction_candidate", "closure_candidate"):
            rec["restrictionCandidates"][oid] = {"acknowledgedAt": datetime.now(timezone.utc).isoformat(), "observationType": o["observationType"]}
            results.append({"observationId": oid, "outcome": "restriction_not_confirmed", "verificationStatus": "unverified",
                            "message": "Recorded as an unverified candidate only. Restrictions and closures can be verified only through an authorized verification workflow, which this API does not offer; routing is unaffected."})
            continue
        if cat != "defect":
            results.append({"observationId": oid, "outcome": "not_actionable", "message": "This observation type cannot be turned into a defect report."})
            continue
        prior = next((c for r in earlier for c in r.get("confirmations", {}).values() if c.get("defectType") == o["suggestedDefectType"]), None)
        if prior:
            results.append({"observationId": oid, "outcome": "duplicate_image_not_counted", "defectId": prior["defectId"], "verificationStatus": "unverified",
                            "message": "The same image already produced this defect report. It is not counted as independent corroboration."})
            continue
        if loc["status"] != "user_provided":
            results.append({"observationId": oid, "outcome": "needs_location", "message": "Location is unknown. Provide latitude and longitude to create a defect report."})
            continue
        sev = req.severityOverrides.get(oid, o.get("severityEstimate"))
        if sev is None or not 1 <= sev <= 5:
            results.append({"observationId": oid, "outcome": "needs_severity", "message": "No usable severity. Provide severityOverrides[observationId] between 1 and 5."})
            continue
        text = f"{o['description']} [Candidate from {rec['modelProvider']} image analysis; reporter-confirmed, not verified.]"
        if req.notes or rec.get("notes"):
            text += f" Notes: {req.notes or rec.get('notes')}"
        defect = create_defect_record(
            NewDefectInput(defectType=o["suggestedDefectType"], latitude=loc["latitude"], longitude=loc["longitude"], severity=int(sev), description=text[:3000], photoUrl=None, observedAt=rec["createdAt"]),
            provenance={"evidenceId": rec["id"], "evidenceObservationId": oid, "evidenceSource": "image_upload", "modelProvider": rec["modelProvider"], "model": rec["model"],
                        "visualConfidence": o["visualConfidence"], "userConfirmedObservation": True, "observedAtBasis": "upload_time"})
        rec["confirmations"][oid] = {"defectId": defect["id"], "defectType": o["suggestedDefectType"], "confirmedAt": datetime.now(timezone.utc).isoformat()}
        results.append({"observationId": oid, "outcome": "defect_created", "defectId": defect["id"], "verificationStatus": "unverified",
                        "message": "Defect report created through the existing workflow. It remains unverified until an authorized check."})
    put_json("evidence_analyses", rec["id"], rec)
    created = any(r["outcome"] == "defect_created" for r in results)
    status = "defects_created" if created else "no_defects_created"
    return {"evidenceId": rec["id"], "status": status, "results": results, "disclaimer": DISCLAIMER}
