"""Directory changes that keep the employee invariants RealHRSoft promises.

An employee works under one client at a time: moving them to another client ends
their current employments elsewhere (the Marketplace keeps their history).

Client HR users (``ClientUser``) are staff in the "Client HR" group: the group grants
the admin permissions, and the admin narrows every list and choice to their client.
"""

from django.contrib.auth.models import Group, Permission
from django.db import transaction
from django.utils import timezone

from directory.models import Client, ClientUser, Employee

CLIENT_HR_GROUP = "Client HR"
CLIENT_HR_PERMISSIONS = {
    "client": ("view", "change"),
    "company": ("view", "add", "change"),
    "employee": ("view", "add", "change"),
    "employment": ("view", "add", "change"),
}


@transaction.atomic
def end_foreign_employments(employee: Employee) -> int:
    """End current employments outside the employee's client; returns how many."""
    current = employee.employments.filter(ended_on__isnull=True)
    if employee.client_id is not None:
        current = current.exclude(company__client_id=employee.client_id)
    return current.update(ended_on=timezone.localdate())


def ensure_client_hr_group() -> Group:
    """The "Client HR" group with exactly its directory permissions."""
    group, _ = Group.objects.get_or_create(name=CLIENT_HR_GROUP)
    codenames = [
        f"{action}_{model}"
        for model, actions in CLIENT_HR_PERMISSIONS.items()
        for action in actions
    ]
    group.permissions.set(
        Permission.objects.filter(
            content_type__app_label="directory", codename__in=codenames
        )
    )
    return group


def client_of(user) -> Client | None:
    """The client a client HR user works for; ``None`` for anyone else."""
    if not user.is_authenticated:
        return None
    link = ClientUser.objects.select_related("client").filter(user=user).first()
    return link.client if link else None


@transaction.atomic
def make_client_user(user, client: Client) -> ClientUser:
    """Give the user client HR access to the client (staff, in the group)."""
    link, _ = ClientUser.objects.update_or_create(user=user, defaults={"client": client})
    if not user.is_staff:
        user.is_staff = True
        user.save(update_fields=["is_staff"])
    user.groups.add(ensure_client_hr_group())
    return link
