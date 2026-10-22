"""Employee tokens, with the issuance-time authorization check (Phase 0 gate).

Before signing, RealHRSoft re-reads the employee's current state: an inactive or
disabled login, a missing or inactive client, or a company the employee does not
currently work for gets no token. The token asserts the published revision, so it
always matches the snapshot the Marketplace received (or is about to receive).
"""

import time
from dataclasses import dataclass
from uuid import UUID, uuid4

from django.conf import settings

from directory.models import Employee
from signing import keys
from signing.models import KeyPurpose
from sync import outbox

EMPLOYEE_SCOPE = "marketplace.employee"


class NotAuthorized(Exception):
    """RealHRSoft will not vouch for this employee (or company) right now."""


@dataclass(frozen=True)
class IssuedToken:
    token: str
    token_id: str
    revision: int
    company_uuids: tuple[str, ...]


def issue(employee: Employee, company_uuid: UUID | None = None) -> IssuedToken:
    """Sign a token for the employee, or raise ``NotAuthorized``."""
    # Publishes first if the directory changed without an event (normally a no-op),
    # so the asserted revision always describes the current state.
    outbox.publish(employee)
    employee.refresh_from_db()
    snapshot = employee.published or {}
    if not employee.user.is_active or not snapshot.get("active"):
        raise NotAuthorized("employee is not active")
    if employee.client is None or not employee.client.active:
        raise NotAuthorized("employee has no active client")
    companies = tuple(snapshot.get("company_uuids", ()))
    if company_uuid is not None and str(company_uuid) not in companies:
        raise NotAuthorized("employee does not work for that company")
    now = int(time.time())
    token_id = str(uuid4())
    claims = {
        "iss": settings.ISSUER,
        "aud": settings.MARKETPLACE_AUDIENCE,
        "sub": str(employee.uuid),
        "scope": EMPLOYEE_SCOPE,
        "jti": token_id,
        "iat": now,
        "nbf": now,
        "exp": now + int(settings.EMPLOYEE_TOKEN_LIFETIME.total_seconds()),
        "partner_uuid": snapshot["partner_uuid"],
        "company_uuids": list(companies),
        "authorization_revision": employee.revision,
    }
    return IssuedToken(
        token=keys.sign(KeyPurpose.EMPLOYEE, claims),
        token_id=token_id,
        revision=employee.revision,
        company_uuids=companies,
    )
