"""Client HR users see and change only their own client's directory."""

import pytest
from django.contrib.auth import get_user_model

from directory import demo
from directory.models import Client, Company, Employee

pytestmark = pytest.mark.django_db


@pytest.fixture
def seeded():
    demo.seed_admin()
    demo.seed_clients()
    demo.seed_companies()
    demo.seed_employees()


def login(client, username):
    client.force_login(get_user_model().objects.get(username=username))


def test_hr_user_lists_only_their_client(client, seeded):
    login(client, "gita")
    page = client.get("/admin/directory/employee/").content.decode()
    assert "Ram Thapa" in page
    assert "Pema Sherpa" not in page
    page = client.get("/admin/directory/company/").content.decode()
    assert "Acme Retail" in page and "Himalaya Hydro" not in page


def test_hr_user_cannot_open_another_clients_records(client, seeded):
    login(client, "gita")
    pema = Employee.objects.get(user__username="pema")
    hydro = Company.objects.get(name="Himalaya Hydro")
    himalaya = Client.objects.get(organization="Himalaya Holdings")
    for url in (
        f"/admin/directory/employee/{pema.pk}/change/",
        f"/admin/directory/company/{hydro.pk}/change/",
        f"/admin/directory/client/{himalaya.pk}/change/",
    ):
        response = client.get(url)
        assert response.status_code == 302  # admin redirects "does not exist"


def test_hr_user_cannot_see_keys_outbox_or_client_users(client, seeded):
    login(client, "gita")
    for url in (
        "/admin/signing/signingkey/",
        "/admin/sync/outboxevent/",
        "/admin/directory/clientuser/",
    ):
        assert client.get(url).status_code == 403


def test_hr_user_adds_an_employee_with_a_login_in_their_client(client, seeded):
    login(client, "gita")
    acme = Client.objects.get(organization="Acme Group")
    retail = Company.objects.get(name="Acme Retail")
    response = client.post(
        "/admin/directory/employee/add/",
        {
            "username": "kiran",
            "password": "Kiran-pass-4821",
            "display_name": "Kiran Bista",
            "email": "kiran@acme.example",
            "client": acme.pk,
            "active": "on",
            "employments-TOTAL_FORMS": "1",
            "employments-INITIAL_FORMS": "0",
            "employments-0-company": retail.pk,
            "employments-0-started_on": "2026-10-01",
        },
    )
    assert response.status_code == 302, response.content.decode()[:2000]
    kiran = Employee.objects.get(user__username="kiran")
    assert kiran.user.check_password("Kiran-pass-4821")
    assert kiran.revision == 1
    assert kiran.published["company_uuids"] == [str(retail.uuid)]


def test_hr_user_cannot_place_an_employee_in_another_client(client, seeded):
    login(client, "gita")
    himalaya = Client.objects.get(organization="Himalaya Holdings")
    response = client.post(
        "/admin/directory/employee/add/",
        {
            "username": "intruder",
            "password": "Intruder-pass-4821",
            "display_name": "Intruder",
            "client": himalaya.pk,
            "employments-TOTAL_FORMS": "0",
            "employments-INITIAL_FORMS": "0",
        },
    )
    assert response.status_code == 200  # form redisplayed with an error
    assert not Employee.objects.filter(user__username="intruder").exists()


def test_hr_user_cannot_deactivate_their_client(client, seeded):
    login(client, "gita")
    acme = Client.objects.get(organization="Acme Group")
    page = client.get("/admin/directory/client/").content.decode()
    assert "Deactivate" not in page
    form = client.get(f"/admin/directory/client/{acme.pk}/change/").content.decode()
    assert 'name="active"' not in form


def test_superuser_sees_everything(client, seeded):
    login(client, "admin")
    page = client.get("/admin/directory/employee/").content.decode()
    assert "Ram Thapa" in page and "Pema Sherpa" in page
