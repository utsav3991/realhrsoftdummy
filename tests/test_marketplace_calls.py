import json
from unittest import mock

import jwt
import pytest
from django.core.management import call_command

from sync import marketplace
from tests.conftest import marketplace_key

pytestmark = pytest.mark.django_db


def claims_of(call):
    signature = call.kwargs["headers"]["X-RealHRSoft-Signature"]
    return jwt.decode(
        signature,
        key=marketplace_key(signature),
        algorithms=["RS256"],
        audience="realhrsoft-marketplace-sync",
        options={"verify_iat": False},
    )


def test_sync_status_is_a_signed_get(signing_keys):
    with mock.patch("sync.marketplace.requests.request") as request:
        marketplace.sync_status()
    method, url = request.call_args.args
    assert (method, url) == (
        "GET",
        "http://marketplace.test/api/v1/integrations/realhrsoft/sync-status",
    )
    claims = claims_of(request.call_args)
    assert claims["method"] == "GET"
    assert claims["path"] == "/api/v1/integrations/realhrsoft/sync-status"
    assert "event_id" not in claims


def test_reconcile_signs_its_body(signing_keys):
    with mock.patch("sync.marketplace.requests.request") as request:
        marketplace.reconcile("employee", "2b7e1c4d-5f6a-4b8c-9d0e-1f2a3b4c5d6e")
    body = request.call_args.kwargs["data"]
    assert json.loads(body) == {
        "scope": "employee",
        "target": "2b7e1c4d-5f6a-4b8c-9d0e-1f2a3b4c5d6e",
    }
    import hashlib

    assert claims_of(request.call_args)["body_sha256"] == hashlib.sha256(body).hexdigest()


def test_env_lines_point_the_marketplace_at_this_dummy(capsys):
    call_command("marketplace", "env")
    out = capsys.readouterr().out
    assert "REALHRSOFT_ISSUER=http://realhrsoft.test" in out
    assert "REALHRSOFT_JWKS=\n" in out
    assert "REALHRSOFT_JWKS_URL=http://realhrsoft.test/.well-known/jwks.json" in out
    assert "REALHRSOFT_API_URL=http://realhrsoft.test/api/marketplace-sync/v1" in out
    assert "REALHRSOFT_API_TOKEN=snapshot-secret" in out
