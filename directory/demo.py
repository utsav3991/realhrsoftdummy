"""Local demo directory: two client groups, their companies, HR users and employees.

Every seeder creates what is missing (it never overwrites later edits), then
publishes each record, which is a no-op when its snapshot did not change. Run them
in dependency order (clients, companies, employees) so the Marketplace receives
parents first. All demo logins use ``PASSWORD``.
"""

from dataclasses import dataclass, field

from django.contrib.auth import get_user_model
from django.db import transaction

from directory.models import Client, Company, Employee, Employment
from directory.services import make_client_user
from sync import outbox

PASSWORD = "demo-pass-123"
ADMIN_USERNAME = "admin"


@dataclass(frozen=True)
class Person:
    username: str
    first_name: str
    last_name: str
    middle_name: str = ""

    @property
    def display_name(self) -> str:
        return " ".join(p for p in (self.first_name, self.middle_name, self.last_name) if p)


@dataclass(frozen=True)
class DemoEmployee:
    person: Person
    companies: tuple[str, ...]
    active: bool = True
    note: str = ""


@dataclass(frozen=True)
class DemoClient:
    organization: str
    domain: str
    country: str
    contact: str
    # The first HR user is the client's contact person (the Marketplace invites them).
    hr_users: tuple[Person, ...]
    companies: tuple[str, ...]
    employees: tuple[DemoEmployee, ...] = field(default=())


CLIENTS = (
    DemoClient(
        organization="Acme Group",
        domain="acme.example",
        country="NP",
        contact="+9779812345678",
        hr_users=(Person("gita", "Gita", "Sharma"),),
        companies=("Acme Retail", "Acme Foods", "Acme Logistics"),
        employees=(
            DemoEmployee(
                Person("ram", "Ram", "Thapa"),
                ("Acme Retail", "Acme Foods"),
                note="two companies",
            ),
            DemoEmployee(Person("sita", "Sita", "Rai"), ("Acme Retail",)),
            DemoEmployee(Person("maya", "Maya", "Shrestha"), ("Acme Logistics",)),
            DemoEmployee(
                Person("bikash", "Bikash", "Karki"), (), note="no current company"
            ),
            DemoEmployee(
                Person("hari", "Hari", "Gurung"),
                ("Acme Foods",),
                active=False,
                note="former employee: no tokens",
            ),
        ),
    ),
    DemoClient(
        organization="Himalaya Holdings",
        domain="himalaya.example",
        country="NP",
        contact="+9779801234567",
        hr_users=(
            Person("anil", "Anil", "Joshi", middle_name="Kumar"),
            Person("rita", "Rita", "Magar"),
        ),
        companies=("Himalaya Hydro", "Himalaya Tours"),
        employees=(
            DemoEmployee(Person("pema", "Pema", "Sherpa"), ("Himalaya Hydro",)),
            DemoEmployee(Person("suman", "Suman", "Adhikari"), ("Himalaya Tours",)),
            DemoEmployee(
                Person("nima", "Nima", "Lama"),
                ("Himalaya Hydro", "Himalaya Tours"),
                note="two companies",
            ),
        ),
    ),
)


class MissingDependency(Exception):
    """A seeder ran before the one it depends on."""


def _user(person: Person, domain: str, **flags):
    User = get_user_model()
    user, created = User.objects.get_or_create(
        username=person.username,
        defaults={
            "first_name": person.first_name,
            "last_name": person.last_name,
            "email": f"{person.username}@{domain}",
            **flags,
        },
    )
    if created:
        user.set_password(PASSWORD)
        user.save(update_fields=["password"])
    return user


def _client(demo: DemoClient) -> Client:
    client = Client.objects.filter(organization=demo.organization).first()
    if client is None:
        raise MissingDependency(f"{demo.organization} is missing: seed clients first.")
    return client


def seed_admin():
    """The superuser who runs the whole directory."""
    User = get_user_model()
    if User.objects.filter(username=ADMIN_USERNAME).exists():
        return None
    return User.objects.create_superuser(
        ADMIN_USERNAME, "admin@realhrsoft.example", PASSWORD
    )


@transaction.atomic
def seed_clients() -> list:
    """Clients and their HR users; returns the published events."""
    events = []
    for demo in CLIENTS:
        contact = demo.hr_users[0]
        client, _ = Client.objects.get_or_create(
            organization=demo.organization,
            defaults={
                "first_name": contact.first_name,
                "middle_name": contact.middle_name,
                "last_name": contact.last_name,
                "email": f"{contact.username}@{demo.domain}",
                "country": demo.country,
                "contact": demo.contact,
            },
        )
        for person in demo.hr_users:
            make_client_user(_user(person, demo.domain), client)
        events.append(outbox.publish(client))
    return [event for event in events if event]


@transaction.atomic
def seed_companies() -> list:
    """Each client's companies; returns the published events."""
    events = []
    for demo in CLIENTS:
        client = _client(demo)
        for name in demo.companies:
            company, _ = Company.objects.get_or_create(client=client, name=name)
            events.append(outbox.publish(company))
    return [event for event in events if event]


@transaction.atomic
def seed_employees() -> list:
    """Employee logins, employees and their current employments."""
    events = []
    for demo in CLIENTS:
        client = _client(demo)
        companies = {c.name: c for c in client.companies.all()}
        missing = set().union(*(e.companies for e in demo.employees)) - set(companies)
        if missing:
            raise MissingDependency(
                f"{', '.join(sorted(missing))} missing: seed companies first."
            )
        for demo_employee in demo.employees:
            person = demo_employee.person
            user = _user(person, demo.domain)
            employee, created = Employee.objects.get_or_create(
                user=user,
                defaults={
                    "display_name": person.display_name,
                    "email": user.email,
                    "client": client,
                    "active": demo_employee.active,
                },
            )
            if created:
                for name in demo_employee.companies:
                    Employment.objects.create(employee=employee, company=companies[name])
            events.append(outbox.publish(employee))
    return [event for event in events if event]


def describe() -> list[str]:
    """Logins and RealHRSoft UUIDs of the seeded directory, for people to read."""
    lines = [f"Password for every demo login: {PASSWORD}", ""]
    if get_user_model().objects.filter(username=ADMIN_USERNAME).exists():
        lines.append(f"Superuser: {ADMIN_USERNAME}  (/admin/)")
    notes = {
        e.person.username: e.note for demo in CLIENTS for e in demo.employees if e.note
    }
    for client in Client.objects.prefetch_related("companies", "users__user"):
        lines += ["", f"{client.organization}  client {client.uuid}  r{client.revision}"]
        for link in client.users.all():
            contact = "  (contact person)" if link.user.email == client.email else ""
            lines.append(f"  HR user   {link.user.username:8} /admin/{contact}")
        for company in client.companies.all():
            lines.append(f"  company   {company.name:16} {company.uuid}  r{company.revision}")
        for employee in client.employees.select_related("user"):
            username = employee.user.username
            companies = ", ".join(c.name for c in employee.current_companies()) or "-"
            state = "" if employee.active else "  INACTIVE"
            note = f"  [{notes[username]}]" if username in notes else ""
            lines.append(
                f"  employee  {username:8} {employee.uuid}  {companies}{state}{note}"
            )
    return lines
