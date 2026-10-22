"""The employee's RealHRSoft pages.

``/`` is the plain home with a proxy tester; ``/marketplace/...`` mounts the Marketplace
employee screens (the Vue package, built from ``frontend/``). Both share the company
the employee acts for, kept in the RealHRSoft session.
"""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from directory.models import Employee
from portal import assets

SESSION_COMPANY = "company_uuid"
MOUNT = "/marketplace"


def _employee(request):
    return (
        Employee.objects.select_related("client")
        .filter(user=request.user)
        .first()
    )


def _companies_and_selection(request, employee):
    """The employee's current companies and the selected one (kept valid)."""
    companies = list(employee.current_companies()) if employee else []
    selected = request.session.get(SESSION_COMPANY)
    if selected not in {str(company.uuid) for company in companies}:
        selected = str(companies[0].uuid) if companies else None
        request.session[SESSION_COMPANY] = selected
    return companies, selected


@login_required
def home(request):
    employee = _employee(request)
    companies, selected = _companies_and_selection(request, employee)
    return render(
        request,
        "portal/home.html",
        {"employee": employee, "companies": companies, "selected": selected},
    )


@login_required
def marketplace(request, rest=""):
    employee = _employee(request)
    if employee is None:
        return redirect("portal-home")
    companies, selected = _companies_and_selection(request, employee)
    context = {
        "employee": employee.display_name,
        "client": str(employee.client) if employee.client else None,
        "companies": [{"id": str(c.uuid), "name": c.name} for c in companies],
        "selected": selected,
        "csrfToken": get_token(request),
        "urls": {
            "home": reverse("portal-home"),
            "logout": reverse("logout"),
            "selectCompany": reverse("portal-select-company"),
            "proxy": "/api/marketplace",
            "mount": MOUNT,
        },
    }
    return render(
        request,
        "portal/marketplace.html",
        {"app_context": context, "assets": assets.entry()},
    )


@login_required
@require_POST
def select_company(request):
    employee = _employee(request)
    company = request.POST.get("company") or None
    allowed = (
        {str(uuid) for uuid in employee.current_companies().values_list("uuid", flat=True)}
        if employee
        else set()
    )
    if company is not None and company not in allowed:
        return HttpResponseBadRequest("Not one of your current companies.")
    request.session[SESSION_COMPANY] = company
    if "application/json" in request.headers.get("Accept", ""):
        return HttpResponse(status=204)
    return redirect("portal-home")
