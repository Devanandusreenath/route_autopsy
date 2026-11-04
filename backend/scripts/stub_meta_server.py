"""LOCAL STUB of an OpenAI-compatible chat-completions server. THIS IS NOT META AND DOES NO IMAGE ANALYSIS.

Purpose: exercise the backend's real HTTP client path (auth header, data-URL image payload, timeouts, error
mapping, response parsing) when no Meta credential is available, e.g. in CI or an offline demo.
Every observation it returns is canned and labelled "[STUB]". Never present its output as AI findings.

Run:   python scripts/stub_meta_server.py --port 9100
Point the backend at it:
       META_API_BASE_URL=http://127.0.0.1:9100/v1  META_API_KEY=stub-key  META_MODEL=stub-not-meta-model
Behaviour switch (env STUB_MODE): ok | no_observations | restriction_only | invalid_json | server_error | unauthorized | slow
"""
import argparse
import base64
import json
import os
import time

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="STUB (not Meta)")
EXPECTED_KEY = os.getenv("STUB_META_KEY", "stub-key")
LAST_REQUEST: dict = {}
STATE = {"mode": os.getenv("STUB_MODE", "ok")}


def canned(mode: str, size: int, mime: str) -> str:
    note = f"[STUB — no vision model ran; received {size} bytes of {mime}]"
    pothole = {"observationType": "pothole", "description": f"{note} Canned pothole candidate.", "severityEstimate": 4, "visualConfidence": 0.5,
               "observedAttributes": {"stub": True}, "unknownAttributes": ["depth"]}
    sign = {"observationType": "restriction_sign", "description": f"{note} Canned restriction-sign candidate.", "visualConfidence": 0.5,
            "observedAttributes": {"stub": True}}
    water = {"observationType": "standing_water", "description": f"{note} Canned standing-water candidate (no severity).", "visualConfidence": 0.4,
             "observedAttributes": {"stub": True}}
    if mode == "no_observations":
        obs = []
    elif mode == "restriction_only":
        obs = [sign]
    else:
        obs = [pothole, water, sign]
    return json.dumps({"imageQuality": "STUB (not assessed)", "observations": obs})


@app.post("/stub/mode/{mode}")
def set_mode(mode: str):
    """Switch behaviour at runtime (used by the test-suite and demo scripts)."""
    STATE["mode"] = mode
    return {"mode": mode}


@app.get("/stub/last-request")
def last_request():
    """Inspect what the backend sent (image bytes are NOT included, only their size and type)."""
    return LAST_REQUEST


@app.post("/v1/chat/completions")
async def chat(request: Request, authorization: str | None = Header(default=None)):
    mode = STATE["mode"]
    if mode == "unauthorized" or authorization != f"Bearer {EXPECTED_KEY}":
        raise HTTPException(401, "bad key")
    if mode == "server_error":
        raise HTTPException(500, "stub failure")
    if mode == "slow":
        time.sleep(float(os.getenv("STUB_DELAY_SECONDS", "3")))
    body = await request.json()
    parts = body["messages"][-1]["content"]
    img = next(p for p in parts if p.get("type") == "image_url")["image_url"]["url"]
    header, b64 = img.split(",", 1)
    mime = header[5:].split(";")[0]
    raw = base64.b64decode(b64)
    LAST_REQUEST.clear()
    LAST_REQUEST.update({"model": body.get("model"), "mime": mime, "imageBytes": len(raw), "hasSystemMessage": body["messages"][0]["role"] == "system",
                         "authorized": True})
    content = "this is not json" if mode == "invalid_json" else canned(mode, len(raw), mime)
    return JSONResponse({"id": "stub", "object": "chat.completion", "model": body.get("model"),
                         "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}]})


if __name__ == "__main__":
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9100)
    args = ap.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
