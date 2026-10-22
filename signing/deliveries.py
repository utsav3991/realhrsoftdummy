"""Signatures for calls to the Marketplace integration endpoints.

``X-RealHRSoft-Signature`` is a compact RS256 JWS (sync key, sync audience) whose
claims bind the request: method, exact path, SHA-256 of the raw body and, for
events, the event_id. It is valid for ±300 seconds, so each attempt signs afresh.

The signed path is the one the Marketplace receives, so it includes the path of
MARKETPLACE_URL when the Marketplace is served under a prefix (``/backend``).
"""

import hashlib
import time
from urllib.parse import urlsplit

from django.conf import settings

from signing import keys
from signing.models import KeyPurpose

HEADER = "X-RealHRSoft-Signature"


def marketplace_path(path: str) -> str:
    """``path`` as the Marketplace receives it: under MARKETPLACE_URL's own path."""
    return urlsplit(settings.MARKETPLACE_URL).path.rstrip("/") + path


def sign(method: str, path: str, body: bytes = b"", event_id=None) -> str:
    claims = {
        "iss": settings.ISSUER,
        "aud": settings.MARKETPLACE_SYNC_AUDIENCE,
        "iat": int(time.time()),
        "method": method.upper(),
        "path": marketplace_path(path),
        "body_sha256": hashlib.sha256(body).hexdigest(),
    }
    if event_id is not None:
        claims["event_id"] = str(event_id)
    return keys.sign(KeyPurpose.SYNC, claims)
