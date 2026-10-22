import json

import pytest

from sync import outbox

pytestmark = pytest.mark.django_db

AUTH = {"HTTP_AUTHORIZATION": "Bearer snapshot-secret"}
BASE = "/api/marketplace-sync/v1"


def test_requires_the_bearer_token(client):
    assert client.get(f"{BASE}/partners").status_code == 401
    wrong = {"HTTP_AUTHORIZATION": "Bearer nope"}
    assert client.get(f"{BASE}/partners", **wrong).status_code == 401


def test_disabled_without_a_configured_token(client, settings):
    settings.SNAPSHOT_API_TOKEN = ""
    assert client.get(f"{BASE}/partners", **AUTH).status_code == 401


def test_item_equals_the_event_of_the_same_revision(client, acme):
    event = outbox.publish(acme["retail"])
    response = client.get(f"{BASE}/companies/{acme['retail'].uuid}", **AUTH)
    assert response.status_code == 200
    assert response.json() == {
        "aggregate_uuid": str(acme["retail"].uuid),
        "aggregate_revision": 1,
        "data": json.loads(event.body)["data"],
    }


def test_unpublished_and_unknown_records_are_404(client, acme):
    assert client.get(f"{BASE}/companies/{acme['retail'].uuid}", **AUTH).status_code == 404
    assert client.get(f"{BASE}/unknown", **AUTH).status_code == 404


def test_pages_with_a_cursor_and_keeps_tombstones(client, make_employee):
    employees = [make_employee(f"user{i}") for i in range(3)]
    for employee in employees:
        outbox.publish(employee)
    employees[1].active = False
    employees[1].save()
    outbox.publish(employees[1])

    seen, cursor = [], ""
    while True:
        response = client.get(f"{BASE}/employees", {"limit": 2, "cursor": cursor}, **AUTH)
        body = response.json()
        seen += body["items"]
        if not body["next_cursor"]:
            break
        cursor = body["next_cursor"]
    assert [item["aggregate_uuid"] for item in seen] == [str(e.uuid) for e in employees]
    assert seen[1]["data"]["active"] is False
    assert seen[1]["aggregate_revision"] == 2


def test_rejects_a_bad_cursor(client, acme):
    response = client.get(f"{BASE}/partners", {"cursor": "!!"}, **AUTH)
    assert response.status_code == 400
