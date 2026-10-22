from unittest import mock

import jwt
import pytest

pytestmark = pytest.mark.django_db


def marketplace(status=200, body=b'{"items": []}', content_type="application/json"):
    response = mock.Mock(status_code=status, content=body)
    response.headers = {"Content-Type": content_type}
    response.json.side_effect = lambda: __import__("json").loads(body)
    return response


@pytest.fixture
def ram(client, signing_keys, make_employee):
    employee = make_employee()
    client.force_login(employee.user)
    return employee


def test_requires_a_realhrsoft_session(client):
    response = client.get("/api/marketplace/marketplace/offers")
    assert response.status_code == 401
    assert response.json()["code"] == "NOT_AUTHENTICATED"


def test_refuses_paths_outside_the_employee_api(client, ram):
    assert client.get("/api/marketplace/admin/users").status_code == 404
    assert client.get("/api/marketplace/marketplace/../admin").status_code == 404


def test_forwards_with_a_fresh_token_and_only_allowed_headers(client, ram, acme):
    company = str(acme["retail"].uuid)
    with mock.patch("portal.proxy.requests.request", return_value=marketplace()) as call:
        response = client.get(
            "/api/marketplace/marketplace/offers?page=2&q=tea",
            HTTP_X_COMPANY_ID=company,
            HTTP_X_REQUEST_ID="req-1",
        )
    assert response.status_code == 200
    assert response.json() == {"items": []}
    method, url = call.call_args.args
    headers = call.call_args.kwargs["headers"]
    assert (method, url) == (
        "GET",
        "http://marketplace.test/api/v1/marketplace/offers?page=2&q=tea",
    )
    assert headers["X-Company-ID"] == company
    assert headers["X-Request-ID"] == "req-1"
    assert "Cookie" not in headers
    token = headers["Authorization"].removeprefix("Bearer ")
    claims = jwt.decode(token, options={"verify_signature": False})
    assert claims["sub"] == str(ram.uuid)
    assert company in claims["company_uuids"]


def test_foreign_company_is_refused_without_calling_the_marketplace(
    client, ram, acme, make_employee
):
    other = make_employee("sita", companies=("retail",))
    client.force_login(other.user)
    with mock.patch("portal.proxy.requests.request") as call:
        response = client.get(
            "/api/marketplace/marketplace/offers",
            HTTP_X_COMPANY_ID=str(acme["foods"].uuid),
        )
    assert response.status_code == 403
    assert response.json()["code"] == "EMPLOYEE_NOT_AUTHORIZED"
    call.assert_not_called()


def test_retries_once_when_the_token_predates_the_revision(client, ram):
    stale = marketplace(409, b'{"code": "AUTHORIZATION_CONTEXT_CHANGED"}')
    with mock.patch(
        "portal.proxy.requests.request", side_effect=[stale, marketplace()]
    ) as call:
        response = client.get("/api/marketplace/me/notifications")
    assert response.status_code == 200
    assert call.call_count == 2


def test_passes_marketplace_problems_through_unchanged(client, ram):
    body = b'{"code": "AUTHORIZATION_SYNC_PENDING", "status": 409}'
    pending = marketplace(409, body, "application/problem+json")
    with mock.patch("portal.proxy.requests.request", return_value=pending):
        response = client.get("/api/marketplace/marketplace/offers")
    assert response.status_code == 409
    assert response.content == body
    assert response["Content-Type"] == "application/problem+json"
