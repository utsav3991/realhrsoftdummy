"""Outbox of snapshot events for the Marketplace.

An event is written in the same transaction as the revision it announces, so a
committed change is never lost. ``body`` is frozen at creation: every retry sends
the same bytes and event_id (the Marketplace rejects a reused event_id with a
different body) under a fresh signature.
"""

from uuid import uuid4

from django.db import models
from django.utils import timezone


class DeliveryStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    DELIVERED = "delivered", "Delivered"
    FAILED = "failed", "Failed"


class OutboxEvent(models.Model):
    event_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    event_type = models.CharField(max_length=40)
    aggregate_type = models.CharField(max_length=20)
    aggregate_uuid = models.UUIDField()
    aggregate_revision = models.PositiveBigIntegerField()
    occurred_at = models.DateTimeField(default=timezone.now)
    body = models.TextField(help_text="The exact JSON envelope sent on every attempt.")
    status = models.CharField(
        max_length=20, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING
    )
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    last_http_status = models.PositiveIntegerField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    receipt = models.JSONField(null=True, blank=True, help_text="Marketplace receipt.")
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["status", "next_attempt_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["aggregate_type", "aggregate_uuid", "aggregate_revision"],
                name="one_event_per_revision",
            )
        ]

    def __str__(self):
        return f"{self.event_type} {self.aggregate_uuid} r{self.aggregate_revision}"
