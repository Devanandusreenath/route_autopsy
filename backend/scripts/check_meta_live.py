"""One-command check of the REAL Meta vision integration. Run it when you have a credential.

    export META_API_KEY=...            # or put it in backend/.env
    export META_MODEL=<an image-capable model id from Meta's current model list>
    python scripts/check_meta_live.py path/to/road_photo.jpg

It runs the same code path as POST /evidence/analyze (upload validation -> provider call -> strict parsing) and prints the
validated candidate observations. The API key is never printed. Exit codes: 0 ok, 2 bad input/config, 3 provider error, 4 invalid model output.
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config, vision_evidence  # noqa: E402
from app.meta_model_client import ProviderError, build_client  # noqa: E402


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    path = argv[1]
    try:
        data = open(path, "rb").read()
    except OSError as e:
        print(f"cannot read {path}: {e.strerror}")
        return 2
    ext = os.path.splitext(path)[1].lower()
    declared = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(ext, "")
    try:
        mime = vision_evidence.validate_upload(declared, data, config.EVIDENCE_MAX_UPLOAD_BYTES)
    except vision_evidence.UploadError as e:
        print(f"image rejected: {e.message}")
        return 2
    try:
        client = build_client()
    except ProviderError as e:
        print(f"not configured: {e.public_message}")
        return 2
    print(f"provider={client.provider} model={client.model} base_url={config.META_API_BASE_URL} image={mime} {len(data)} bytes")
    try:
        parsed = vision_evidence.analyze_image(client, data, mime, observed_at=datetime.now(timezone.utc).isoformat(), location_known=False)
    except ProviderError as e:
        print(f"PROVIDER ERROR ({e.__class__.__name__}, would be HTTP {e.status}): {e.public_message}")
        return 3
    except vision_evidence.InvalidModelResponse as e:
        print(f"INVALID MODEL OUTPUT: {e.detail or e.public_message}")
        return 4
    print(f"OK: {len(parsed['observations'])} candidate observation(s); imageQuality={parsed['imageQuality']!r}; warnings={parsed['warnings']}")
    print(json.dumps(parsed["observations"], indent=2))
    assert all(o["verificationStatus"] == "unverified" for o in parsed["observations"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
