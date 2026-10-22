"""Our tokens and signatures pass the Marketplace's verification rules.

The decode options mirror the Marketplace's ``employee_tokens.verify`` and
``delivery_signatures.verify``.
"""

import hashlib
import time
from datetime import timedelta

import jwt
import pytest
from django.utils import timezone

from signing import deliveries, keys, tokens
from signing.models import KeyPurpose, SigningKey
from tests.conftest import marketplace_key, marketplace_keys

pytestmark = pytest.mark.django_db

TOKEN_REQUIRED = ["iss", "aud", "sub", "scope", "jti", "iat", "nbf", "exp"]


def verify_token(token):
    claims = jwt.decode(
        token,
        key=marketplace_key(token),
        algorithms=["RS256"],
        audience="realhrsoft-marketplace",
        issuer="http://realhrsoft.test",
        leeway=15,
        options={"require": TOKEN_REQUIRED},
    )
    assert claims["exp"] - claims["iat"] <= 60
    return claims


def test_employee_token_carries_the_published_context(signing_keys, make_employee, acme):
    employee = make_employee()
    issued = tokens.issue(employee, acme["retail"].uuid)
    claims = verify_token(issued.token)
    employee.refresh_from_db()
    assert claims["sub"] == str(employee.uuid)
    assert claims["scope"] == "marketplace.employee"
    assert claims["partner_uuid"] == str(acme["client"].uuid)
    assert claims["company_uuids"] == employee.published["company_uuids"]
    assert claims["authorization_revision"] == employee.revision == 1
    header = jwt.get_unverified_header(issued.token)
    assert header["kid"] == signing_keys[KeyPurpose.EMPLOYEE].kid


def test_issuing_publishes_an_unannounced_change_first(signing_keys, make_employee):
    employee = make_employee()
    tokens.issue(employee)
    employee.display_name = "Ram Thapa"
    employee.save()
    claims = verify_token(tokens.issue(employee).token)
    assert claims["authorization_revision"] == 2


@pytest.mark.parametrize(
    "change",
    ["inactive", "disabled_login", "no_client", "inactive_client", "foreign_company"],
)
def test_issuance_check_refuses(change, signing_keys, make_employee, acme):
    employee = make_employee(companies=("retail",))
    company = None
    if change == "inactive":
        employee.active = False
        employee.save()
    elif change == "disabled_login":
        employee.user.is_active = False
        employee.user.save()
    elif change == "no_client":
        employee.client = None
        employee.save()
    elif change == "inactive_client":
        acme["client"].active = False
        acme["client"].save()
    else:
        company = acme["foods"].uuid
    with pytest.raises(tokens.NotAuthorized):
        tokens.issue(employee, company)


def test_employee_key_is_not_a_sync_key(signing_keys, make_employee):
    token = tokens.issue(make_employee()).token
    with pytest.raises(jwt.InvalidAudienceError):
        jwt.decode(
            token,
            key=marketplace_key(token),
            algorithms=["RS256"],
            audience="realhrsoft-marketplace-sync",
        )


def test_delivery_signature_binds_the_request(signing_keys):
    body = b'{"event_id":"x"}'
    signature = deliveries.sign(
        "post", "/api/v1/integrations/realhrsoft/events", body, event_id="abc"
    )
    claims = jwt.decode(
        signature,
        key=marketplace_key(signature),
        algorithms=["RS256"],
        audience="realhrsoft-marketplace-sync",
        issuer="http://realhrsoft.test",
        options={
            "require": ["iss", "aud", "iat", "method", "path", "body_sha256"],
            "verify_iat": False,
        },
    )
    assert abs(time.time() - claims["iat"]) <= 300
    assert claims["method"] == "POST"
    assert claims["path"] == "/api/v1/integrations/realhrsoft/events"
    assert claims["body_sha256"] == hashlib.sha256(body).hexdigest()
    assert claims["event_id"] == "abc"
    assert jwt.get_unverified_header(signature)["kid"] == signing_keys["sync"].kid


def test_delivery_signature_includes_the_marketplace_prefix(signing_keys, settings):
    settings.MARKETPLACE_URL = "http://marketplace.test/backend/"
    signature = deliveries.sign("GET", "/api/v1/integrations/realhrsoft/sync-status")
    claims = jwt.decode(signature, options={"verify_signature": False})
    assert claims["path"] == "/backend/api/v1/integrations/realhrsoft/sync-status"


def test_rotation_keeps_the_retired_key_during_grace(signing_keys, settings):
    old = signing_keys[KeyPurpose.EMPLOYEE]
    new = keys.rotate(KeyPurpose.EMPLOYEE)
    kids = {key.key_id for key in marketplace_keys().keys}
    assert {old.kid, new.kid} <= kids
    SigningKey.objects.filter(pk=old.pk).update(
        retired_at=timezone.now() - settings.RETIRED_KEY_GRACE - timedelta(seconds=1)
    )
    assert old.kid not in {key.key_id for key in marketplace_keys().keys}


def test_revoked_key_leaves_the_jwks_at_once(signing_keys):
    kid = signing_keys[KeyPurpose.SYNC].kid
    keys.revoke(kid)
    assert kid not in {key.key_id for key in marketplace_keys().keys}


def test_jwks_endpoint(client, signing_keys):
    response = client.get("/.well-known/jwks.json")
    assert response.status_code == 200
    published = response.json()["keys"]
    assert {key["kid"] for key in published} == {k.kid for k in signing_keys.values()}
    assert all(key["alg"] == "RS256" and "d" not in key for key in published)


def test_imported_key_signs_both_channels_under_its_kid(db, tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    keys.ensure(KeyPurpose.SYNC)
    for purpose in KeyPurpose.values:
        keys.import_pem(purpose, pem, "realhrsoft-dev-1")
    signature = deliveries.sign("GET", "/x")
    assert jwt.get_unverified_header(signature)["kid"] == "realhrsoft-dev-1"
    jwt.decode(
        signature,
        key=private.public_key(),
        algorithms=["RS256"],
        audience="realhrsoft-marketplace-sync",
        options={"verify_iat": False},
    )
    published = [key["kid"] for key in keys.jwks()["keys"]]
    assert published.count("realhrsoft-dev-1") == 1
    # Re-importing is idempotent; revoking covers both purposes.
    keys.import_pem(KeyPurpose.EMPLOYEE, pem, "realhrsoft-dev-1")
    assert len(keys.revoke("realhrsoft-dev-1")) == 2
