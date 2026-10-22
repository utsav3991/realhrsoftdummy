import json

import pytest

from directory.models import Client
from directory.services import end_foreign_employments
from sync import outbox
from sync.models import OutboxEvent

pytestmark = pytest.mark.django_db


def test_publish_bumps_revision_only_when_the_snapshot_changes(acme):
    client = acme["client"]
    first = outbox.publish(client)
    assert first.aggregate_revision == 1
    assert outbox.publish(client) is None
    client.organization = "Acme Holdings"
    client.save()
    second = outbox.publish(client)
    client.refresh_from_db()
    assert (second.aggregate_revision, client.revision) == (2, 2)
    assert client.published["organization"] == "Acme Holdings"


def test_event_body_matches_the_marketplace_envelope(acme):
    event = outbox.publish(acme["retail"])
    body = json.loads(event.body)
    assert body == {
        "event_id": str(event.event_id),
        "schema_version": 1,
        "event_type": "company.snapshot",
        "aggregate_type": "company",
        "aggregate_uuid": str(acme["retail"].uuid),
        "aggregate_revision": 1,
        "occurred_at": body["occurred_at"],
        "data": {
            "client_uuid": str(acme["client"].uuid),
            "name": "Acme Retail",
            "active": True,
        },
    }
    assert body["occurred_at"].endswith("Z")


def test_employee_snapshot_lists_current_companies_sorted(make_employee, acme):
    employee = make_employee()
    event = outbox.publish(employee)
    data = json.loads(event.body)["data"]
    expected = sorted([str(acme["retail"].uuid), str(acme["foods"].uuid)])
    assert data == {
        "active": True,
        "display_name": "Ram",
        "email": "ram@acme.example",
        "partner_uuid": str(acme["client"].uuid),
        "company_uuids": expected,
    }


def test_client_switch_ends_employments_elsewhere(make_employee, acme):
    employee = make_employee()
    outbox.publish(employee)
    other = Client.objects.create(
        organization="Beta Group", first_name="B", last_name="C", email="b@beta.example"
    )
    employee.client = other
    employee.save()
    assert end_foreign_employments(employee) == 2
    event = outbox.publish(employee)
    data = json.loads(event.body)["data"]
    assert data["partner_uuid"] == str(other.uuid)
    assert data["company_uuids"] == []
    assert employee.employments.filter(ended_on__isnull=True).count() == 0


def test_deactivation_is_published_as_a_tombstone(acme):
    company = acme["foods"]
    outbox.publish(company)
    company.active = False
    company.save()
    outbox.publish(company)
    latest = OutboxEvent.objects.filter(aggregate_uuid=company.uuid).last()
    assert json.loads(latest.body)["data"]["active"] is False


def test_inactive_employee_publishes_no_companies(make_employee):
    employee = make_employee(active=False)
    data = json.loads(outbox.publish(employee).body)["data"]
    assert data["active"] is False
    assert data["company_uuids"] == []
    assert employee.employments.filter(ended_on__isnull=True).count() == 2
