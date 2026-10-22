"""RS256 signing keys, one active key per purpose.

Employee tokens and sync deliveries use separate keys (distinct ``kid``) from the
same key system and one published JWKS; the Marketplace tells them apart by
audience. Private keys never leave this backend and are never shown in the admin.
"""

from django.db import models
from django.db.models import Q


class KeyPurpose(models.TextChoices):
    EMPLOYEE = "employee", "Employee tokens"
    SYNC = "sync", "Sync deliveries"


class KeyStatus(models.TextChoices):
    ACTIVE = "active", "Active (signs)"
    RETIRED = "retired", "Retired (verifies during the grace period)"
    REVOKED = "revoked", "Revoked (never verifies)"


class SigningKey(models.Model):
    kid = models.CharField(max_length=64)
    purpose = models.CharField(max_length=20, choices=KeyPurpose.choices)
    status = models.CharField(
        max_length=20, choices=KeyStatus.choices, default=KeyStatus.ACTIVE
    )
    private_pem = models.TextField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    retired_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # An imported key may serve both purposes under one kid (see keys.import_pem).
            models.UniqueConstraint(fields=["kid", "purpose"], name="one_kid_per_purpose"),
            models.UniqueConstraint(
                fields=["purpose"],
                condition=Q(status="active"),
                name="one_active_key_per_purpose",
            )
        ]

    def __str__(self):
        return f"{self.kid} ({self.purpose}, {self.status})"
