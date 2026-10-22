"""The backend proxy between the employee's browser and the Marketplace.

The browser calls ``/api/marketplace/<path>`` with its RealHRSoft session cookie;
this view checks the employee, signs a fresh 60-second token and forwards the call
to ``{MARKETPLACE_URL}/api/v1/<path>``. No Marketplace token ever reaches the
browser. Rules (employee package README §2):

- only ``marketplace/*`` and ``me/notifications*`` are forwarded;
- forwarded request headers: X-Company-ID, X-Request-ID, Idempotency-Key,
  Content-Type, Accept; the browser's cookies and Authorization are dropped;
- the response comes back unchanged (status, body, Content-Type);
- on 409 AUTHORIZATION_CONTEXT_CHANGED the token predated the employee's revision:
  sign a new one and retry once (the Marketplace executed nothing).

Bodies are never logged: voucher credentials are bearer secrets.
"""

import logging
from uuid import UUID

import requests
from django.conf import settings
from django.http import HttpResponse, JsonResponse

from directory.models import Employee
from signing import tokens

logger = logging.getLogger(__name__)

ALLOWED_PREFIXES = ("marketplace/", "me/notifications")
FORWARDED_REQUEST_HEADERS = (
    "X-Company-ID",
    "X-Request-ID",
    "Idempotency-Key",
    "Content-Type",
    "Accept",
)
RETURNED_HEADERS = ("Content-Type", "Cache-Control", "Retry-After", "Content-Disposition")
COMPANY_HEADER = "X-Company-ID"


def problem(status: int, code: str, detail: str) -> JsonResponse:
    return JsonResponse(
        {"type": "about:blank", "status": status, "code": code, "detail": detail},
        status=status,
        content_type="application/problem+json",
    )


def _company(request) -> UUID | None:
    value = request.headers.get(COMPANY_HEADER)
    return UUID(value) if value else None


def _forward(request, path: str, token: str) -> requests.Response:
    headers = {
        name: request.headers[name]
        for name in FORWARDED_REQUEST_HEADERS
        if name in request.headers
    }
    headers["Authorization"] = f"Bearer {token}"
    url = f"{settings.MARKETPLACE_URL}/api/v1/{path}"
    if query := request.META.get("QUERY_STRING"):
        url += f"?{query}"
    return requests.request(
        request.method,
        url,
        data=request.body or None,
        headers=headers,
        timeout=settings.PROXY_TIMEOUT,
        allow_redirects=False,
    )


def _context_changed(response: requests.Response) -> bool:
    if response.status_code != 409:
        return False
    try:
        return response.json().get("code") == "AUTHORIZATION_CONTEXT_CHANGED"
    except ValueError, AttributeError:
        return False


def proxy(request, path: str):
    if not request.user.is_authenticated:
        return problem(401, "NOT_AUTHENTICATED", "Sign in to RealHRSoft first.")
    if not path.startswith(ALLOWED_PREFIXES) or ".." in path:
        return problem(404, "NOT_FOUND", "Not a Marketplace employee path.")
    employee = Employee.objects.select_related("client", "user").filter(
        user=request.user
    ).first()
    if employee is None:
        return problem(403, "NOT_AN_EMPLOYEE", "This login is not an employee.")
    try:
        company = _company(request)
    except ValueError:
        return problem(400, "INVALID_REQUEST", f"{COMPANY_HEADER} must be a UUID.")
    try:
        response = None
        for _ in range(2):
            issued = tokens.issue(employee, company)
            response = _forward(request, path, issued.token)
            if not _context_changed(response):
                break
            logger.info("Token r%s was stale; signing again", issued.revision)
    except tokens.NotAuthorized as reason:
        logger.info("No token for employee %s: %s", employee.uuid, reason)
        return problem(
            403,
            "EMPLOYEE_NOT_AUTHORIZED",
            "RealHRSoft does not authorize this employee for the selected company.",
        )
    except requests.RequestException as error:
        logger.warning("Marketplace unreachable: %s", type(error).__name__)
        return problem(502, "MARKETPLACE_UNAVAILABLE", "The Marketplace did not answer.")
    logger.info("%s /%s -> %s", request.method, path, response.status_code)
    proxied = HttpResponse(response.content, status=response.status_code)
    for name in RETURNED_HEADERS:
        if name in response.headers:
            proxied[name] = response.headers[name]
    return proxied
