"""Exercise the REAL MetaModelApiClient over REAL HTTP against scripts/stub_meta_server.py.

This proves our request/response handling over the wire. It does NOT prove anything about Meta's service:
the stub is a local stand-in (every observation is labelled [STUB])."""
import os
import socket
import subprocess
import sys
import time

import pytest
import requests

from app import config

ROOT = os.path.dirname(os.path.dirname(__file__))
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200
KEY = "stub-key"


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def stub():
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-W", "ignore", os.path.join(ROOT, "scripts", "stub_meta_server.py"), "--port", str(port)], cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            requests.get(base + "/stub/last-request", timeout=0.5)
            break
        except requests.RequestException:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("stub server did not start")
    yield base
    proc.kill()


@pytest.fixture()
def wired(stub, monkeypatch):
    monkeypatch.setattr(config, "META_API_BASE_URL", stub + "/v1")
    monkeypatch.setattr(config, "META_API_KEY", KEY)
    monkeypatch.setattr(config, "META_MODEL", "stub-not-meta-model")
    monkeypatch.setattr(config, "META_TIMEOUT_SECONDS", 5)
    requests.post(stub + "/stub/mode/ok")
    return stub


def upload(client, data=JPEG):
    return client.post("/evidence/analyze", files={"file": ("r.jpg", data, "image/jpeg")}, data={"latitude": "10.0", "longitude": "76.3"})


def test_full_pipeline_over_real_http(client, wired):
    r = upload(client)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["model"] == "stub-not-meta-model" and len(j["observations"]) == 3
    assert all(o["description"].startswith("[STUB") and o["verificationStatus"] == "unverified" for o in j["observations"])
    seen = requests.get(wired + "/stub/last-request").json()
    assert seen == {"model": "stub-not-meta-model", "mime": "image/jpeg", "imageBytes": len(JPEG), "hasSystemMessage": True, "authorized": True}


def test_confirm_after_real_http_analysis(client, wired):
    ev = upload(client).json()
    r = client.post("/evidence/confirm", json={"evidenceId": ev["evidenceId"], "confirmedObservationIds": ["obs-1", "obs-3"], "severityOverrides": {}}).json()
    assert [x["outcome"] for x in r["results"]] == ["defect_created", "restriction_not_confirmed"]
    assert len(client.get("/restrictions").json()) == 7  # still only the seeded restrictions


def test_status_reports_configured_with_stub(client, wired):
    j = client.get("/evidence/status").json()
    assert j["configured"] is True and j["model"] == "stub-not-meta-model"


@pytest.mark.parametrize("mode,code", [("invalid_json", 502), ("server_error", 502), ("unauthorized", 502)])
def test_failure_modes_map_to_http_errors(client, wired, mode, code):
    requests.post(wired + f"/stub/mode/{mode}")
    r = upload(client)
    assert r.status_code == code and KEY not in r.text
    assert client.get("/defects").status_code == 200


def test_wrong_key_is_an_auth_error_not_a_leak(client, wired, monkeypatch):
    monkeypatch.setattr(config, "META_API_KEY", "wrong-key")
    r = upload(client)
    assert r.status_code == 502 and "credentials were rejected" in r.json()["detail"] and "wrong-key" not in r.text


def test_slow_provider_times_out_with_504(client, wired, monkeypatch):
    monkeypatch.setattr(config, "META_TIMEOUT_SECONDS", 1)
    requests.post(wired + "/stub/mode/slow")
    r = upload(client)
    assert r.status_code == 504


def test_unreachable_provider_is_502(client, monkeypatch):
    monkeypatch.setattr(config, "META_API_BASE_URL", f"http://127.0.0.1:{_free_port()}/v1")
    monkeypatch.setattr(config, "META_API_KEY", KEY)
    monkeypatch.setattr(config, "META_MODEL", "m")
    r = upload(client)
    assert r.status_code == 502 and "unavailable" in r.json()["detail"]


def test_no_observations_is_a_valid_empty_result(client, wired):
    requests.post(wired + "/stub/mode/no_observations")
    j = upload(client).json()
    assert j["observations"] == []
