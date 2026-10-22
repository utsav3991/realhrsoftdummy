"""Key lifecycle and the published key set (runbook: key rotation and compromise).

- ``rotate``: a new active key; the previous one retires and stays in the JWKS for
  ``RETIRED_KEY_GRACE`` so tokens and deliveries already signed still verify.
- ``revoke``: drops a key from the JWKS at once. The Marketplace keeps a fetched
  key set for up to its ``REALHRSOFT_JWKS_LIFESPAN``; for a compromise, it also adds
  the kid to ``REALHRSOFT_REVOKED_KIDS``.
"""

import json
import secrets

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone

from signing.models import KeyPurpose, KeyStatus, SigningKey

ALGORITHM = "RS256"


def _new_kid(purpose: str) -> str:
    return f"{purpose}-{timezone.now():%Y%m%d}-{secrets.token_hex(4)}"


@transaction.atomic
def rotate(purpose: str) -> SigningKey:
    """Create the purpose's new active key and retire the current one."""
    if purpose not in KeyPurpose.values:
        raise ValueError(f"Unknown purpose {purpose}")
    now = timezone.now()
    SigningKey.objects.select_for_update().filter(
        purpose=purpose, status=KeyStatus.ACTIVE
    ).update(status=KeyStatus.RETIRED, retired_at=now)
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return SigningKey.objects.create(
        kid=_new_kid(purpose), purpose=purpose, private_pem=pem
    )


@transaction.atomic
def import_pem(purpose: str, pem: bytes, kid: str) -> SigningKey:
    """Make an existing RSA private key the purpose's active key.

    For a Marketplace that pins a key it already trusts (for example the one
    ``realhrsoft_dev_token keygen`` made, kid ``realhrsoft-dev-1``): importing it for
    both purposes lets this dummy sign tokens and deliveries it accepts unchanged.
    """
    if purpose not in KeyPurpose.values:
        raise ValueError(f"Unknown purpose {purpose}")
    private = serialization.load_pem_private_key(pem, None)
    if not isinstance(private, rsa.RSAPrivateKey):
        raise ValueError("Not an RSA private key")
    normalized = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    now = timezone.now()
    SigningKey.objects.select_for_update().filter(
        purpose=purpose, status=KeyStatus.ACTIVE
    ).exclude(kid=kid).update(status=KeyStatus.RETIRED, retired_at=now)
    key, _ = SigningKey.objects.update_or_create(
        kid=kid,
        purpose=purpose,
        defaults={
            "private_pem": normalized,
            "status": KeyStatus.ACTIVE,
            "retired_at": None,
            "revoked_at": None,
        },
    )
    return key


def ensure(purpose: str) -> SigningKey:
    """The active key, created when the purpose has none yet."""
    key = SigningKey.objects.filter(purpose=purpose, status=KeyStatus.ACTIVE).first()
    return key or rotate(purpose)


@transaction.atomic
def revoke(kid: str) -> list[SigningKey]:
    """Revoke the kid for every purpose it serves."""
    found = list(SigningKey.objects.select_for_update().filter(kid=kid))
    if not found:
        raise SigningKey.DoesNotExist(kid)
    for key in found:
        key.status, key.revoked_at = KeyStatus.REVOKED, timezone.now()
        key.save(update_fields=["status", "revoked_at"])
    return found


def active(purpose: str) -> SigningKey:
    key = SigningKey.objects.filter(purpose=purpose, status=KeyStatus.ACTIVE).first()
    if key is None:
        raise ImproperlyConfigured(
            f"No active {purpose} signing key: run `manage.py signing_keys ensure`."
        )
    return key


def sign(purpose: str, claims: dict) -> str:
    key = active(purpose)
    return jwt.encode(
        claims, key.private_pem, algorithm=ALGORITHM, headers={"kid": key.kid}
    )


def published() -> list[SigningKey]:
    """Keys that verify now: active ones and retired ones still in grace."""
    cutoff = timezone.now() - settings.RETIRED_KEY_GRACE
    return [
        key
        for key in SigningKey.objects.exclude(status=KeyStatus.REVOKED)
        if key.status == KeyStatus.ACTIVE or (key.retired_at and key.retired_at > cutoff)
    ]


def public_jwk(key: SigningKey) -> dict:
    private = serialization.load_pem_private_key(key.private_pem.encode(), None)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    return {**public, "kid": key.kid, "alg": ALGORITHM, "use": "sig"}


def jwks() -> dict:
    # A key imported for both purposes is published once.
    unique = {key.kid: key for key in published()}
    return {"keys": [public_jwk(key) for key in unique.values()]}
