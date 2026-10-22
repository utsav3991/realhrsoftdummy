import json

import pytest
from django.contrib.auth import get_user_model

from directory import demo
from directory.models import Client, ClientUser, Company, Employee
from directory.services import CLIENT_HR_GROUP
from sync.models import OutboxEvent

pytestmark = pytest.mark.django_db


def seed_all():
    demo.seed_admin()
    return demo.seed_clients() + demo.seed_companies() + demo.seed_employees()


def test_seeds_the_whole_directory_in_dependency_order():
    events = seed_all()
    assert Client.objects.count() == 2
    assert Company.objects.count() == 5
    assert Employee.objects.count() == 8
    kinds = [event.aggregate_type for event in events]
    assert kinds == ["partner"] * 2 + ["company"] * 5 + ["employee"] * 8


def test_client_contact_is_its_first_hr_user():
    demo.seed_clients()
    himalaya = Client.objects.get(organization="Himalaya Holdings")
    assert (himalaya.first_name, himalaya.middle_name, himalaya.last_name) == (
        "Anil",
        "Kumar",
        "Joshi",
    )
    assert himalaya.email == "anil@himalaya.example"
    assert set(himalaya.users.values_list("user__username", flat=True)) == {
        "anil",
        "rita",
    }


def test_hr_users_are_staff_in_the_client_hr_group():
    demo.seed_clients()
    gita = get_user_model().objects.get(username="gita")
    assert gita.is_staff and not gita.is_superuser
    assert gita.groups.filter(name=CLIENT_HR_GROUP).exists()
    assert gita.check_password(demo.PASSWORD)
    assert ClientUser.objects.get(user=gita).client.organization == "Acme Group"


def test_employees_hold_their_companies():
    seed_all()
    ram = Employee.objects.get(user__username="ram")
    assert sorted(c.name for c in ram.current_companies()) == ["Acme Foods", "Acme Retail"]
    data = ram.published
    assert data["partner_uuid"] == str(ram.client.uuid)
    assert len(data["company_uuids"]) == 2
    hari = Employee.objects.get(user__username="hari").published
    assert (hari["active"], hari["company_uuids"]) == (False, [])
    assert Employee.objects.get(user__username="bikash").published["company_uuids"] == []


def test_rerunning_publishes_nothing_new():
    seed_all()
    count = OutboxEvent.objects.count()
    assert seed_all() == []
    assert OutboxEvent.objects.count() == count


def test_seeders_refuse_to_run_out_of_order():
    with pytest.raises(demo.MissingDependency):
        demo.seed_companies()
    demo.seed_clients()
    with pytest.raises(demo.MissingDependency):
        demo.seed_employees()


def test_describe_lists_logins_and_uuids():
    seed_all()
    text = "\n".join(demo.describe())
    ram = Employee.objects.get(user__username="ram")
    assert str(ram.uuid) in text
    assert "gita" in text and "(contact person)" in text
    assert "INACTIVE" in text
    json.dumps(text)  # plain text only
