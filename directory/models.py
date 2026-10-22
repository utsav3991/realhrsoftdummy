"""RealHRSoft's directory: the only source of truth for clients, companies and staff.

Every aggregate the Marketplace synchronizes (client, company, employee) carries:

- ``uuid``: the immutable RealHRSoft UUID the Marketplace keys on;
- ``revision``: bumped each time its published snapshot changes (never otherwise);
- ``published``: the snapshot data sent at that revision. The snapshot API serves
  exactly this, so an event and a reconciliation read of the same revision always
  carry the same data (the Marketplace quarantines a mismatch).

Records are never deleted: ``active`` false is the tombstone the Marketplace needs.
"""

from uuid import uuid4

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

E164 = RegexValidator(r"^\+[1-9]\d{6,14}$", "Use E.164, e.g. +9779812345678.")


class Aggregate(models.Model):
    uuid = models.UUIDField(default=uuid4, unique=True, editable=False)
    active = models.BooleanField(default=True)
    revision = models.PositiveBigIntegerField(default=0, editable=False)
    published = models.JSONField(null=True, blank=True, editable=False)
    published_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Client(Aggregate):
    """A RealHRSoft customer group (called "partner" in RealHRSoft)."""

    organization = models.CharField(max_length=200, help_text="Group name.")
    first_name = models.CharField(max_length=100, help_text="Contact person.")
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(help_text="Contact email; the Marketplace invites it.")
    country = models.CharField(max_length=2, blank=True, help_text="ISO alpha-2.")
    contact = models.CharField(max_length=16, blank=True, validators=[E164])

    class Meta:
        ordering = ["organization"]

    def __str__(self):
        return self.organization


class Company(Aggregate):
    """One company of a client. It never moves to another client."""

    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="companies")
    name = models.CharField(max_length=200)

    class Meta:
        ordering = ["client__organization", "name"]
        verbose_name_plural = "companies"

    def __str__(self):
        return f"{self.name} ({self.client})"


class Employee(Aggregate):
    """A person employed under at most one client, in any of its companies.

    ``user`` is their RealHRSoft login; the Marketplace never sees it.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="employee"
    )
    display_name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    client = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="employees",
        help_text="The employee's active client; employments elsewhere end on save.",
    )

    class Meta:
        ordering = ["display_name"]

    def __str__(self):
        return self.display_name

    def current_companies(self):
        """Companies of the active client this employee currently works for."""
        if self.client_id is None:
            return Company.objects.none()
        return Company.objects.filter(
            client_id=self.client_id,
            employments__employee=self,
            employments__ended_on__isnull=True,
        ).distinct()


class ClientUser(models.Model):
    """A client's HR staff member: signs in to RealHRSoft to manage that client's
    companies and employees (and nothing else). Never synchronized; the client's
    contact person, whom the Marketplace invites as client admin, is usually one."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="client_user"
    )
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="users")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["client__organization", "user__username"]

    def __str__(self):
        return f"{self.user.get_username()} ({self.client})"


class Employment(models.Model):
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="employments"
    )
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="employments"
    )
    started_on = models.DateField(default=timezone.localdate)
    ended_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-started_on"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "company"],
                condition=Q(ended_on__isnull=True),
                name="one_current_employment_per_company",
            )
        ]

    def __str__(self):
        return f"{self.employee} at {self.company}"
