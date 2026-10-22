"""Signed calls from RealHRSoft's backend to the Marketplace integration API.

Uses the same delivery signature as events (``signing.deliveries``), which the
Marketplace accepts on its source endpoints: sync status, reconciliation requests
and company mapping reads.
"""

import json

import requests
from django.conf import settings

from signing import deliveries

BASE = "/api/v1/integrations/realhrsoft"


def call(method: str, path: str, payload: dict | None = None) -> requests.Response:
    body = b"" if payload is None else json.dumps(payload).encode()
    headers = {
        "Accept": "application/json",
        deliveries.HEADER: deliveries.sign(method, path, body),
    }
    if payload is not None:
        headers["Content-Type"] = "application/json"
    return requests.request(
        method,
        settings.MARKETPLACE_URL + path,
        data=body or None,
        headers=headers,
        timeout=settings.SYNC_TIMEOUT,
    )


def sync_status() -> requests.Response:
    return call("GET", f"{BASE}/sync-status")


def reconcile(scope: str = "full", target=None) -> requests.Response:
    payload = {"scope": scope}
    if target:
        payload["target"] = str(target)
    return call("POST", f"{BASE}/reconcile", payload)


def company(uuid) -> requests.Response:
    return call("GET", f"{BASE}/companies/{uuid}")
