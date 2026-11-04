"""Provider adapter for Meta's hosted multimodal models.

Verified against public documentation (Meta developer blog, LiteLLM and promptfoo provider docs, accessed 2026-10-30):
  * Meta's Llama API (api.llama.com) public preview was retired on 6 July 2026.
  * It was superseded by the Meta Model API: base URL https://api.meta.ai/v1,
    OpenAI-compatible POST /chat/completions, `Authorization: Bearer <key>`, key created in the dev.meta.ai dashboard.
  * Images are sent as an `image_url` content part carrying a base64 data URL.
  * Model ids (e.g. `muse-spark-1.1`) change over time, so META_MODEL is mandatory configuration — no id is hard-coded.

This module has NOT been exercised against the live API in this repository (no credential was available);
the request shape is covered by tests against a mocked HTTP layer. See README "Known limitations".

Isolation: the routing engine never imports this module. A different provider only needs another class
implementing `VisionModelClient` plus a branch in `build_client`.
"""
from __future__ import annotations

import base64
import logging
from typing import Any, Callable, Protocol

import requests

from . import config

log = logging.getLogger("routewise.meta")


class ProviderError(Exception):
    """Base class. `status` is the HTTP status this backend should answer with; `public_message` is safe to show clients."""
    status = 502
    public_message = "The vision model provider returned an error."

    def __init__(self, public_message: str | None = None):
        super().__init__(public_message or self.public_message)
        if public_message:
            self.public_message = public_message


class ProviderNotConfigured(ProviderError):
    status = 503
    public_message = "Image analysis is not configured on this server (missing META_API_KEY or META_MODEL)."


class ProviderTimeout(ProviderError):
    status = 504
    public_message = "The vision model provider timed out. Please try again."


class ProviderUnavailable(ProviderError):
    status = 502
    public_message = "The vision model provider is unavailable. Please try again later."


class ProviderAuthError(ProviderError):
    status = 502
    public_message = "The server's vision model credentials were rejected by the provider. Contact the administrator."


class ProviderRateLimited(ProviderError):
    status = 503
    public_message = "The vision model provider is rate limiting requests. Please retry shortly."


class ProviderRequestError(ProviderError):
    status = 502
    public_message = "The vision model provider rejected the request."


class VisionModelClient(Protocol):
    provider: str
    model: str

    def complete_with_image(self, *, system: str, prompt: str, image_bytes: bytes, mime_type: str) -> str: ...


class MetaModelApiClient:
    provider = "meta_model_api"

    def __init__(self, api_key: str, model: str, base_url: str, timeout_s: int, http_post: Callable[..., Any] | None = None):
        if not api_key or not model:
            raise ProviderNotConfigured()
        self._key = api_key
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._timeout = timeout_s
        self._post = http_post or requests.post

    def complete_with_image(self, *, system: str, prompt: str, image_bytes: bytes, mime_type: str) -> str:
        data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": data_url}}]},
            ],
        }
        try:
            resp = self._post(self._url, headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}, json=body, timeout=(5, self._timeout))
        except requests.Timeout as exc:
            log.warning("meta provider timeout (%s)", type(exc).__name__)
            raise ProviderTimeout() from None
        except requests.RequestException as exc:
            log.warning("meta provider connection error (%s)", type(exc).__name__)
            raise ProviderUnavailable() from None
        code = resp.status_code
        if code in (401, 403):
            log.error("meta provider rejected credentials (HTTP %s)", code)
            raise ProviderAuthError()
        if code == 429:
            raise ProviderRateLimited()
        if code >= 500:
            log.warning("meta provider server error (HTTP %s)", code)
            raise ProviderUnavailable()
        if code >= 400:
            log.warning("meta provider request rejected (HTTP %s)", code)
            raise ProviderRequestError()
        try:
            payload = resp.json()
            content = payload["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderRequestError("The vision model provider returned an unexpected response shape.") from None
        if isinstance(content, list):  # some OpenAI-compatible servers return content parts
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        if not isinstance(content, str) or not content.strip():
            raise ProviderRequestError("The vision model provider returned an empty response.")
        return content


def build_client() -> VisionModelClient:
    """Factory driven purely by environment configuration (FastAPI dependency; override in tests)."""
    if config.META_PROVIDER != "meta_model_api":
        raise ProviderNotConfigured(f"Unsupported META_PROVIDER '{config.META_PROVIDER}'. Supported: meta_model_api.")
    return MetaModelApiClient(config.META_API_KEY, config.META_MODEL, config.META_API_BASE_URL, config.META_TIMEOUT_SECONDS)
