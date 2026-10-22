"""Snapshot data, schema v1, exactly as the Marketplace parses it.

Mirrors ``identity_access/services/realhrsoft_snapshots.py`` in the Marketplace:

- partner (the client): organization, first_name, middle_name, last_name, email,
  country, contact, active;
- company: client_uuid, name, active;
- employee: active, display_name, email, partner_uuid (null without a client),
  company_uuids (the complete current set, sorted so equal states compare equal;
  always empty for an inactive employee, which the Marketplace enforces).
"""

from directory.models import Client, Company, Employee

PARTNER, COMPANY, EMPLOYEE = "partner", "company", "employee"
SCHEMA_VERSION = 1
MAX_COMPANIES = 100
EVENT_TYPES = {PARTNER: "partner.snapshot", COMPANY: "company.snapshot", EMPLOYEE: "employee.snapshot"}
MODELS = {PARTNER: Client, COMPANY: Company, EMPLOYEE: Employee}


def aggregate_type(obj) -> str:
    for name, model in MODELS.items():
        if isinstance(obj, model):
            return name
    raise TypeError(f"{type(obj).__name__} is not a synchronized aggregate")


def build(obj) -> dict:
    """The snapshot data for the record's current state."""
    kind = aggregate_type(obj)
    if kind == PARTNER:
        return {
            "organization": obj.organization,
            "first_name": obj.first_name,
            "middle_name": obj.middle_name,
            "last_name": obj.last_name,
            "email": obj.email,
            "country": obj.country,
            "contact": obj.contact,
            "active": obj.active,
        }
    if kind == COMPANY:
        return {"client_uuid": str(obj.client.uuid), "name": obj.name, "active": obj.active}
    # The Marketplace requires an empty set unless the employee is active under a client
    # (an inactive employee's employment rows stay here as history).
    companies = (
        sorted(str(uuid) for uuid in obj.current_companies().values_list("uuid", flat=True))
        if obj.active and obj.client_id
        else []
    )
    if len(companies) > MAX_COMPANIES:
        raise ValueError(f"An employee may hold at most {MAX_COMPANIES} companies")
    return {
        "active": obj.active,
        "display_name": obj.display_name,
        "email": obj.email,
        "partner_uuid": str(obj.client.uuid) if obj.client_id else None,
        "company_uuids": companies,
    }
