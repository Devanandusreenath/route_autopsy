"""The API contract document and the frontend endpoint map must stay in lock-step with the real backend."""
import os
import re
import subprocess
import sys

import pytest

from app.main import app

ROOT = os.path.dirname(os.path.dirname(__file__))
ENDPOINTS_TS = os.path.join(ROOT, "..", "frontend", "src", "lib", "api", "endpoints.ts")


def test_contract_doc_is_current():
    """docs/API_CONTRACT.md is generated; regenerate it with `python scripts/generate_api_contract.py`."""
    r = subprocess.run([sys.executable, "-W", "ignore", os.path.join(ROOT, "scripts", "generate_api_contract.py"), "--check"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, "docs/API_CONTRACT.md is stale — run: python scripts/generate_api_contract.py"


def _norm(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "{}", path)


def test_generator_consumed_endpoints_exist_in_openapi():
    spec = app.openapi()
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import generate_api_contract as g  # noqa: PLC0415

    for (method, path) in g.CONSUMED:
        assert path in spec["paths"] and method.lower() in spec["paths"][path], (method, path)


@pytest.mark.skipif(not os.path.exists(ENDPOINTS_TS), reason="frontend not present next to backend")
def test_every_frontend_endpoint_exists_in_backend_openapi():
    src = open(ENDPOINTS_TS).read()
    paths = set()
    for m in re.finditer(r"""(?:"|`)(/[A-Za-z0-9_\-/${}().]*)(?:"|`)""", src):
        raw = m.group(1)
        paths.add(_norm(re.sub(r"\$\{[^}]*\}", "{}", raw)))
    assert len(paths) >= 10, paths
    backend = {_norm(p) for p in app.openapi()["paths"]}
    missing = sorted(p for p in paths if p not in backend)
    assert not missing, f"frontend calls endpoints the backend does not have: {missing}"


@pytest.mark.skipif(not os.path.exists(ENDPOINTS_TS), reason="frontend not present next to backend")
def test_every_consumed_endpoint_is_called_by_the_frontend():
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import generate_api_contract as g  # noqa: PLC0415

    src = open(ENDPOINTS_TS).read()
    frontend = {_norm(re.sub(r"\$\{[^}]*\}", "{}", m.group(1))) for m in re.finditer(r"""(?:"|`)(/[A-Za-z0-9_\-/${}().]*)(?:"|`)""", src)}
    unused = sorted(p for (_m, p) in g.CONSUMED if _norm(p) not in frontend)
    assert not unused, f"documented as frontend-consumed but not in endpoints.ts: {unused}"


def test_doc_covers_the_key_contract_sections():
    doc = open(os.path.join(ROOT, "docs", "API_CONTRACT.md")).read()
    for needle in ("POST", "/routes/investigate", "/autopsy/scenario", "/evidence/confirm", "AutopsyResponse", "ScenarioComparison", "revisedRoute",
                   "Why both `POST /routes` and `POST /routes/investigate` exist"):
        assert needle in doc, needle
