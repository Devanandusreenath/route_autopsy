import json
import logging

import pytest
import requests

from app import config, meta_model_client as mmc
from app.main import app
from app.routers_evidence import get_vision_client
from tests.conftest import snapshot

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 64
SECRET = "sk-test-SECRET-123"

GOOD = {"imageQuality": "good", "observations": [
    {"observationType": "pothole", "description": "Deep pothole in the left lane.", "severityEstimate": 4, "visualConfidence": 0.93,
     "observedAttributes": {"approxSize": "large"}, "unknownAttributes": ["depth"]},
    {"observationType": "restriction_sign", "description": "A sign that appears to show a height limit.", "visualConfidence": 0.88,
     "observedAttributes": {"signText": "3.5m"}},
]}


class FakeClient:
    provider, model = "meta_model_api", "fake-model"

    def __init__(self, reply=None, exc=None):
        self.reply, self.exc, self.calls = reply, exc, []

    def complete_with_image(self, **kw):
        self.calls.append(kw)
        if self.exc:
            raise self.exc
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)


def use(client_obj):
    app.dependency_overrides[get_vision_client] = lambda: client_obj
    return client_obj


def upload(client, data=JPEG, mime="image/jpeg", **form):
    return client.post("/evidence/analyze", files={"file": ("road.jpg", data, mime)}, data=form)


# ------------------------------------------------------------------ analyze: success

def test_valid_upload_returns_unverified_candidates_with_unknown_location(client):
    fake = use(FakeClient(GOOD))
    r = upload(client, notes="near the bus stop")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["location"]["status"] == "unknown" and j["location"]["latitude"] is None
    assert len(j["observations"]) == 2 and j["evidenceId"].startswith("EV-")
    for o in j["observations"]:
        assert o["verificationStatus"] == "unverified" and o["source"] == "image_upload" and o["modelProvider"] == "meta_model_api"
        assert "exact geographic location" in o["unknownAttributes"] and "road dimensions and vehicle clearance" in o["unknownAttributes"]
    pothole, sign = j["observations"]
    assert pothole["candidateCategory"] == "defect" and pothole["suggestedDefectType"] == "pothole" and pothole["severityEstimate"] == 4
    assert sign["candidateCategory"] == "restriction_candidate" and sign["requiresAuthorizedVerification"] and sign["severityEstimate"] is None
    assert sign["observedAttributes"]["signText"] == "3.5m"
    assert len(fake.calls) == 1 and fake.calls[0]["mime_type"] == "image/jpeg"
    assert "near the bus stop" not in json.dumps(fake.calls[0]["prompt"])  # user notes are not sent to the model


@pytest.mark.parametrize("data,mime", [(JPEG, "image/jpeg"), (PNG, "image/png"), (WEBP, "image/webp")])
def test_all_supported_image_types(client, data, mime):
    use(FakeClient({"observations": []}))
    r = upload(client, data, mime)
    assert r.status_code == 200 and r.json()["observations"] == []


def test_user_supplied_location_is_recorded_as_such(client):
    use(FakeClient(GOOD))
    j = upload(client, latitude="9.99", longitude="76.3").json()
    assert j["location"]["status"] == "user_provided" and j["location"]["latitude"] == 9.99
    assert "exact geographic location" not in j["observations"][0]["unknownAttributes"]


def test_half_a_location_is_rejected(client):
    use(FakeClient(GOOD))
    assert upload(client, latitude="9.99").status_code == 422


# ------------------------------------------------------------------ analyze: upload validation

def test_unsupported_file_type_rejected_before_model_call(client):
    fake = use(FakeClient(GOOD))
    for data, mime in ((b"hello", "text/plain"), (b"%PDF-1.4", "application/pdf"), (b"GIF89a", "image/gif")):
        assert upload(client, data, mime).status_code == 415
    assert fake.calls == []


def test_declared_type_must_match_file_signature(client):
    fake = use(FakeClient(GOOD))
    assert upload(client, b"<html>not an image</html>", "image/jpeg").status_code == 415
    assert upload(client, PNG, "image/jpeg").status_code == 415
    assert fake.calls == []


def test_empty_file_rejected(client):
    use(FakeClient(GOOD))
    assert upload(client, b"", "image/jpeg").status_code == 422


def test_oversized_file_rejected(client, monkeypatch):
    fake = use(FakeClient(GOOD))
    monkeypatch.setattr(config, "EVIDENCE_MAX_UPLOAD_BYTES", 2048)
    r = upload(client, JPEG + b"\x00" * 5000)
    assert r.status_code == 413 and fake.calls == []
    assert upload(client, JPEG + b"\x00" * 100).status_code == 200


def test_missing_file_field_is_422(client):
    use(FakeClient(GOOD))
    assert client.post("/evidence/analyze", data={"notes": "x"}).status_code == 422


# ------------------------------------------------------------------ model response handling

@pytest.mark.parametrize("reply", ["not json at all", "{}", '{"observations": "nope"}', json.dumps({"observations": [{"observationType": "pothole"}]})])
def test_invalid_model_response_is_502(client, reply):
    use(FakeClient(reply))
    r = upload(client)
    assert r.status_code == 502 and "could not be validated" in r.json()["detail"]


def test_fenced_json_is_accepted(client):
    use(FakeClient("```json\n" + json.dumps(GOOD) + "\n```"))
    assert upload(client).status_code == 200


def test_partially_invalid_observations_are_skipped_with_warning(client):
    reply = {"observations": [GOOD["observations"][0], {"observationType": "pothole", "description": "x", "visualConfidence": 7}]}
    use(FakeClient(reply))
    j = upload(client).json()
    assert len(j["observations"]) == 1 and any("visualConfidence" in w for w in j["warnings"])


def test_model_cannot_assign_verification_coordinates_or_clearance(client):
    evil = {"observations": [{"observationType": "restriction_sign", "description": "Sign.", "visualConfidence": 0.99, "verificationStatus": "verified",
                              "verified": True, "latitude": 9.9, "longitude": 76.2, "candidateCategory": "defect", "id": "hacked",
                              "observedAttributes": {"clearanceM": 3.1, "gpsFix": "9.9,76.2", "signText": "3.5m", "roadWidthM": 7},
                              "customField": {"keep": "me"}}], "topLevelExtra": "kept"}
    use(FakeClient(evil))
    j = upload(client).json()
    o = j["observations"][0]
    assert o["verificationStatus"] == "unverified" and o["candidateCategory"] == "restriction_candidate" and o["id"] == "obs-1"
    assert o["observedAttributes"] == {"signText": "3.5m"}
    assert set(o["discardedModelFields"]) >= {"latitude", "longitude", "verificationStatus", "verified", "candidateCategory", "id",
                                              "observedAttributes.clearanceM", "observedAttributes.gpsFix", "observedAttributes.roadWidthM"}
    assert o["modelExtras"] == {"customField": {"keep": "me"}} and j["modelExtras"] == {"topLevelExtra": "kept"}  # unknown fields preserved, never trusted
    assert j["location"]["status"] == "unknown"


def test_high_visual_confidence_is_not_verification(client):
    use(FakeClient({"observations": [{"observationType": "pothole", "description": "Pothole", "severityEstimate": 5, "visualConfidence": 1.0}]}))
    o = upload(client).json()["observations"][0]
    assert o["visualConfidence"] == 1.0 and o["verificationStatus"] == "unverified"


def test_unknown_observation_type_becomes_other_and_keeps_original(client):
    use(FakeClient({"observations": [{"observationType": "alien_crater", "description": "Odd.", "visualConfidence": 0.4}]}))
    o = upload(client).json()["observations"][0]
    assert o["observationType"] == "other" and o["candidateCategory"] == "unknown" and o["modelExtras"]["originalObservationType"] == "alien_crater"


# ------------------------------------------------------------------ provider failure handling

@pytest.mark.parametrize("exc,code", [(mmc.ProviderUnavailable(), 502), (mmc.ProviderTimeout(), 504), (mmc.ProviderAuthError(), 502),
                                      (mmc.ProviderRateLimited(), 503), (mmc.ProviderRequestError(), 502)])
def test_provider_errors_map_to_http_status(client, exc, code):
    use(FakeClient(exc=exc))
    r = upload(client)
    assert r.status_code == code and r.json()["detail"] == exc.public_message
    assert snapshot()["evidence_analyses"] == []  # nothing stored on failure


def test_unconfigured_provider_is_503_without_leaking_config(client):
    assert not config.META_API_KEY and not config.META_MODEL
    r = upload(client)
    assert r.status_code == 503 and "not configured" in r.json()["detail"]


def test_upload_validation_runs_before_configuration_check(client):
    """Junk input gets a 4xx even when the provider is unconfigured; it never learns the server's config state."""
    assert not config.META_API_KEY
    assert upload(client, b"hello", "text/plain").status_code == 415
    assert upload(client, b"<html>", "image/jpeg").status_code == 415
    assert upload(client, b"", "image/jpeg").status_code == 422


def test_unsupported_provider_name_is_503(client, monkeypatch):
    monkeypatch.setattr(config, "META_PROVIDER", "llama_api_legacy")
    r = upload(client)
    assert r.status_code == 503 and "Unsupported META_PROVIDER" in r.json()["detail"]


# ------------------------------------------------------------------ Meta HTTP client (mocked transport)

class Resp:
    def __init__(self, code=200, body=None):
        self.status_code, self._b = code, body

    def json(self):
        if self._b is None:
            raise ValueError("no json")
        return self._b


def meta(post):
    return mmc.MetaModelApiClient(SECRET, "muse-test", "https://api.meta.ai/v1/", 30, http_post=post)


def test_meta_request_shape_matches_documented_openai_compatible_format():
    seen = {}

    def post(url, headers, json, timeout):
        seen.update(url=url, headers=headers, body=json, timeout=timeout)
        return Resp(200, {"choices": [{"message": {"content": "{\"observations\": []}"}}]})

    out = meta(post).complete_with_image(system="sys", prompt="p", image_bytes=JPEG, mime_type="image/jpeg")
    assert out == '{"observations": []}'
    assert seen["url"] == "https://api.meta.ai/v1/chat/completions"
    assert seen["headers"]["Authorization"] == f"Bearer {SECRET}"
    assert seen["body"]["model"] == "muse-test"
    parts = seen["body"]["messages"][1]["content"]
    assert parts[0] == {"type": "text", "text": "p"} and parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert seen["timeout"] == (5, 30)


@pytest.mark.parametrize("code,exc", [(401, mmc.ProviderAuthError), (403, mmc.ProviderAuthError), (429, mmc.ProviderRateLimited),
                                      (500, mmc.ProviderUnavailable), (503, mmc.ProviderUnavailable), (400, mmc.ProviderRequestError)])
def test_meta_http_status_mapping(code, exc):
    with pytest.raises(exc):
        meta(lambda *a, **k: Resp(code, {"error": SECRET})).complete_with_image(system="s", prompt="p", image_bytes=JPEG, mime_type="image/jpeg")


def test_meta_transport_errors_and_bad_shapes():
    def boom(exc):
        def f(*a, **k):
            raise exc
        return f
    c = lambda post: meta(post).complete_with_image(system="s", prompt="p", image_bytes=JPEG, mime_type="image/jpeg")  # noqa: E731
    with pytest.raises(mmc.ProviderTimeout):
        c(boom(requests.Timeout("slow")))
    with pytest.raises(mmc.ProviderUnavailable):
        c(boom(requests.ConnectionError("down")))
    with pytest.raises(mmc.ProviderRequestError):
        c(lambda *a, **k: Resp(200, {"unexpected": 1}))
    with pytest.raises(mmc.ProviderRequestError):
        c(lambda *a, **k: Resp(200, None))
    with pytest.raises(mmc.ProviderRequestError):
        c(lambda *a, **k: Resp(200, {"choices": [{"message": {"content": "  "}}]}))
    assert c(lambda *a, **k: Resp(200, {"choices": [{"message": {"content": [{"type": "text", "text": "hi"}]}}]})) == "hi"


def test_meta_client_requires_key_and_model():
    with pytest.raises(mmc.ProviderNotConfigured):
        mmc.MetaModelApiClient("", "m", "https://x", 5)
    with pytest.raises(mmc.ProviderNotConfigured):
        mmc.MetaModelApiClient("k", "", "https://x", 5)


def test_credentials_never_appear_in_responses_logs_or_openapi(client, caplog, monkeypatch):
    monkeypatch.setattr(config, "META_API_KEY", SECRET)
    monkeypatch.setattr(config, "META_MODEL", "muse-test")
    monkeypatch.setattr(mmc.requests, "post", lambda *a, **k: Resp(401, {"error": f"bad key {SECRET}"}))
    with caplog.at_level(logging.DEBUG):
        r = upload(client)
    assert r.status_code == 502
    assert SECRET not in r.text and SECRET not in caplog.text
    assert SECRET not in json.dumps(app.openapi()) and SECRET not in client.get("/health").text and SECRET not in client.get("/api/meta").text


def test_end_to_end_through_real_client_with_mocked_http(client, monkeypatch):
    monkeypatch.setattr(config, "META_API_KEY", SECRET)
    monkeypatch.setattr(config, "META_MODEL", "muse-test")
    monkeypatch.setattr(mmc.requests, "post", lambda *a, **k: Resp(200, {"choices": [{"message": {"content": json.dumps(GOOD)}}]}))
    j = upload(client).json()
    assert j["model"] == "muse-test" and len(j["observations"]) == 2


# ------------------------------------------------------------------ confirmation workflow

def analyze_ok(client, data=JPEG, reply=GOOD, **form):
    use(FakeClient(reply))
    return upload(client, data, "image/jpeg", **form).json()


def test_confirm_creates_unverified_defect_via_existing_workflow(client):
    ev = analyze_ok(client, latitude="10.0", longitude="76.3")
    n_defects = len(client.get("/defects").json())
    r = client.post("/evidence/confirm", json={"evidenceId": ev["evidenceId"], "confirmedObservationIds": ["obs-1"]})
    assert r.status_code == 200, r.text
    res = r.json()["results"][0]
    assert res["outcome"] == "defect_created" and res["verificationStatus"] == "unverified" and r.json()["status"] == "defects_created"
    d = client.get(f"/defects/{res['defectId']}").json()
    assert d["verificationStatus"] == "unverified" and d["maintenanceStatus"] == "open" and d["independentReportCount"] == 1
    assert d["defectType"] == "pothole" and d["severity"] == 4 and d["isUserSubmitted"] is True
    assert d["evidenceId"] == ev["evidenceId"] and d["evidenceSource"] == "image_upload" and d["userConfirmedObservation"] is True and d["photoUrl"] is None
    assert len(client.get("/defects").json()) == n_defects + 1
    assert d["reportedAt"] and d["observedAt"] == ev["createdAt"]  # provenance timestamps retained
    assert "reporter-confirmed, not verified" in d["description"]


def test_confirmed_evidence_is_distinguishable_from_unverified(client):
    ev = analyze_ok(client, latitude="10.0", longitude="76.3")
    client.post("/evidence/confirm", json={"evidenceId": ev["evidenceId"], "confirmedObservationIds": ["obs-1"]})
    mine = [d for d in client.get("/defects").json() if d.get("evidenceId")]
    seeded = [d for d in client.get("/defects").json() if not d.get("evidenceId")]
    assert len(mine) == 1 and mine[0]["userConfirmedObservation"] and mine[0]["verificationStatus"] == "unverified"
    assert not any(d.get("userConfirmedObservation") for d in seeded)


def test_restriction_candidates_are_never_confirmed_or_persisted(client):
    ev = analyze_ok(client, latitude="10.0", longitude="76.3")
    before = snapshot()
    r = client.post("/evidence/confirm", json={"evidenceId": ev["evidenceId"], "confirmedObservationIds": ["obs-2"]}).json()
    assert r["results"][0]["outcome"] == "restriction_not_confirmed" and r["results"][0]["verificationStatus"] == "unverified" and r["status"] == "no_defects_created"
    after = snapshot()
    assert after["restrictions"] == before["restrictions"] and after["defects"] == before["defects"]
    assert len(client.get("/restrictions").json()) == 7


def test_routing_unchanged_by_unverified_evidence(client):
    body = {"origin": "VYT", "destination": "KKD", "vehicleId": "veh-ecomet"}
    before = client.post("/routes/investigate", json=body).json()["alternatives"]
    ev = analyze_ok(client, latitude="10.0", longitude="76.3", reply={"observations": [{"observationType": "road_closure", "description": "Barrier across road.", "visualConfidence": 0.99}]})
    client.post("/evidence/confirm", json={"evidenceId": ev["evidenceId"], "confirmedObservationIds": ["obs-1"]})
    assert client.post("/routes/investigate", json=body).json()["alternatives"] == before


def test_confirm_needs_location_then_accepts_it(client):
    ev = analyze_ok(client)
    r = client.post("/evidence/confirm", json={"evidenceId": ev["evidenceId"], "confirmedObservationIds": ["obs-1"]}).json()
    assert r["results"][0]["outcome"] == "needs_location" and len(client.get("/defects").json()) == 15
    r2 = client.post("/evidence/confirm", json={"evidenceId": ev["evidenceId"], "confirmedObservationIds": ["obs-1"], "latitude": 10.0, "longitude": 76.3}).json()
    assert r2["results"][0]["outcome"] == "defect_created"


def test_confirm_needs_severity_unless_overridden(client):
    reply = {"observations": [{"observationType": "pothole", "description": "Pothole", "visualConfidence": 0.8}]}
    ev = analyze_ok(client, reply=reply, latitude="10.0", longitude="76.3")
    assert client.post("/evidence/confirm", json={"evidenceId": ev["evidenceId"], "confirmedObservationIds": ["obs-1"]}).json()["results"][0]["outcome"] == "needs_severity"
    ok = client.post("/evidence/confirm", json={"evidenceId": ev["evidenceId"], "confirmedObservationIds": ["obs-1"], "severityOverrides": {"obs-1": 2}}).json()
    assert ok["results"][0]["outcome"] == "defect_created"
    assert client.get(f"/defects/{ok['results'][0]['defectId']}").json()["severity"] == 2


def test_confirm_is_idempotent(client):
    ev = analyze_ok(client, latitude="10.0", longitude="76.3")
    body = {"evidenceId": ev["evidenceId"], "confirmedObservationIds": ["obs-1"]}
    first = client.post("/evidence/confirm", json=body).json()["results"][0]
    second = client.post("/evidence/confirm", json=body).json()["results"][0]
    assert second["outcome"] == "already_confirmed" and second["defectId"] == first["defectId"] and len(client.get("/defects").json()) == 16


def test_duplicate_image_is_not_independent_corroboration(client):
    a = analyze_ok(client, latitude="10.0", longitude="76.3")
    b = analyze_ok(client, latitude="10.0", longitude="76.3")
    assert b["duplicateOf"] == a["evidenceId"] and any("independent corroboration" in w for w in b["warnings"])
    d1 = client.post("/evidence/confirm", json={"evidenceId": a["evidenceId"], "confirmedObservationIds": ["obs-1"]}).json()["results"][0]
    d2 = client.post("/evidence/confirm", json={"evidenceId": b["evidenceId"], "confirmedObservationIds": ["obs-1"]}).json()["results"][0]
    assert d2["outcome"] == "duplicate_image_not_counted" and d2["defectId"] == d1["defectId"]
    assert len(client.get("/defects").json()) == 16
    assert client.get(f"/defects/{d1['defectId']}").json()["independentReportCount"] == 1


def test_different_images_are_not_duplicates(client):
    a = analyze_ok(client, JPEG, latitude="10.0", longitude="76.3")
    b = analyze_ok(client, JPEG + b"\x01", latitude="10.0", longitude="76.3")
    assert b["duplicateOf"] is None and a["evidenceId"] != b["evidenceId"]


def test_confirm_error_cases(client):
    assert client.post("/evidence/confirm", json={"evidenceId": "EV-NOPE", "confirmedObservationIds": []}).status_code == 404
    ev = analyze_ok(client)
    r = client.post("/evidence/confirm", json={"evidenceId": ev["evidenceId"], "confirmedObservationIds": ["obs-99"]}).json()
    assert r["results"][0]["outcome"] == "unknown_observation"
    assert client.post("/evidence/confirm", json={"evidenceId": ev["evidenceId"], "confirmedObservationIds": [], "latitude": 10}).status_code == 422
    assert client.post("/evidence/confirm", json={"evidenceId": ev["evidenceId"], "confirmedObservationIds": [], "latitude": 999, "longitude": 1}).status_code == 422


def test_image_bytes_are_never_stored(client):
    ev = analyze_ok(client, JPEG + b"UNIQUEMARKER" * 10, latitude="10.0", longitude="76.3")
    raw = json.dumps(snapshot())
    assert "UNIQUEMARKER" not in raw and "base64" not in raw
    assert client.get(f"/evidence/{ev['evidenceId']}").json()["observations"] == ev["observations"]
    assert client.get("/evidence/EV-NOPE").status_code == 404
