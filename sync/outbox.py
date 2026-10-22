"""Publish directory changes and deliver them to the Marketplace.

``publish`` bumps the aggregate's revision and writes its event in one transaction,
only when the snapshot data actually changed. Delivery runs after commit (a
background thread when ``SYNC_DELIVER_ON_COMMIT``) and from
``manage.py deliver_events``, which also retries.

Marketplace answers and what we do:

- 202: received (its receipt says whether it applied); delivered.
- 409 / 422: the event itself is wrong (conflicting event_id, invalid data); failed,
  for an operator to look at. Retrying the same bytes cannot help.
- 401, 429, 5xx, network errors: retried with backoff (401 is usually clock skew, a
  key the Marketplace has not fetched yet, or configuration); failed after
  ``SYNC_MAX_ATTEMPTS``.
"""

import json
import logging
import threading
from datetime import timedelta

import requests
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from signing import deliveries
from sync import snapshots
from sync.models import DeliveryStatus, OutboxEvent

logger = logging.getLogger(__name__)

PERMANENT = {409, 422}
BACKOFF_CAP = 3600


def _envelope_body(event: OutboxEvent, data: dict) -> str:
    envelope = {
        "event_id": str(event.event_id),
        "schema_version": snapshots.SCHEMA_VERSION,
        "event_type": event.event_type,
        "aggregate_type": event.aggregate_type,
        "aggregate_uuid": str(event.aggregate_uuid),
        "aggregate_revision": event.aggregate_revision,
        "occurred_at": event.occurred_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "data": data,
    }
    return json.dumps(envelope, sort_keys=True, separators=(",", ":"))


def publish(obj) -> OutboxEvent | None:
    """Announce the record's current state; ``None`` when nothing changed."""
    kind = snapshots.aggregate_type(obj)
    model = snapshots.MODELS[kind]
    with transaction.atomic():
        locked = model.objects.select_for_update().get(pk=obj.pk)
        data = snapshots.build(locked)
        if locked.revision and data == locked.published:
            return None
        now = timezone.now()
        locked.revision += 1
        locked.published, locked.published_at = data, now
        locked.save(update_fields=["revision", "published", "published_at"])
        event = OutboxEvent(
            event_type=snapshots.EVENT_TYPES[kind],
            aggregate_type=kind,
            aggregate_uuid=locked.uuid,
            aggregate_revision=locked.revision,
            occurred_at=now,
        )
        event.body = _envelope_body(event, data)
        event.save()
        if settings.SYNC_DELIVER_ON_COMMIT:
            transaction.on_commit(kick)
    obj.revision, obj.published, obj.published_at = locked.revision, data, now
    return event


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(5 * 2 ** max(attempts - 1, 0), BACKOFF_CAP))


def _record(event: OutboxEvent, *, status_code=None, error="", receipt=None) -> None:
    event.attempts += 1
    event.last_http_status = status_code
    event.last_error = error[:2000]
    if status_code == 202:
        event.status, event.receipt = DeliveryStatus.DELIVERED, receipt
        event.delivered_at = timezone.now()
    elif status_code in PERMANENT or event.attempts >= settings.SYNC_MAX_ATTEMPTS:
        event.status = DeliveryStatus.FAILED
        event.receipt = receipt
    else:
        event.next_attempt_at = timezone.now() + _backoff(event.attempts)
    event.save()


def send(event: OutboxEvent) -> None:
    """One delivery attempt; records the outcome on the event."""
    body = event.body.encode()
    signature = deliveries.sign(
        "POST", settings.SYNC_EVENTS_PATH, body, event_id=event.event_id
    )
    try:
        response = requests.post(
            settings.MARKETPLACE_URL + settings.SYNC_EVENTS_PATH,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                deliveries.HEADER: signature,
            },
            timeout=settings.SYNC_TIMEOUT,
        )
    except requests.RequestException as error:
        _record(event, error=f"{type(error).__name__}: {error}")
        logger.warning("Event %s not delivered: %s", event.event_id, error)
        return
    try:
        answer = response.json()
    except ValueError:
        answer = None
    error = "" if response.status_code == 202 else response.text
    _record(event, status_code=response.status_code, error=error, receipt=answer)
    logger.info(
        "Event %s (%s r%s) -> %s",
        event.event_id,
        event.event_type,
        event.aggregate_revision,
        response.status_code,
    )


def deliver_due(limit: int = 50) -> int:
    """Attempt every pending event that is due, oldest first; returns how many."""
    sent = 0
    while sent < limit:
        with transaction.atomic():
            event = (
                OutboxEvent.objects.select_for_update(skip_locked=True)
                .filter(
                    status=DeliveryStatus.PENDING, next_attempt_at__lte=timezone.now()
                )
                .order_by("created_at", "id")
                .first()
            )
            if event is None:
                break
            send(event)
        sent += 1
    return sent


_lock = threading.Lock()


def kick() -> None:
    """Deliver due events in a background thread (one at a time per process)."""

    def run():
        if not _lock.acquire(blocking=False):
            return
        try:
            deliver_due()
        except Exception:
            logger.exception("Background delivery failed")
        finally:
            _lock.release()
            connection.close()  # this thread's own connection

    threading.Thread(target=run, name="outbox-delivery", daemon=True).start()


def retry(events) -> int:
    """Put failed or pending events back in line now (admin action)."""
    return events.exclude(status=DeliveryStatus.DELIVERED).update(
        status=DeliveryStatus.PENDING, next_attempt_at=timezone.now()
    )
