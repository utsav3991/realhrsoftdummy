"""Shared start-up for the seed scripts: Django setup and synchronous delivery.

Scripts deliver their events themselves before exiting (a background delivery
thread would die with the process), then report what the Marketplace answered.
"""

import logging
import os
import sys
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

HINTS = {
    401: "the Marketplace does not trust our keys yet: run `make marketplace-env` "
    "and put those lines in the Marketplace .env, then restart it",
    503: "the Marketplace switch realhrsoft.sync is off (or it is down); events retry "
    "with `make deliver`",
    None: "the Marketplace is unreachable at MARKETPLACE_URL; events retry with "
    "`make deliver`",
}


def setup() -> None:
    sys.path.insert(0, str(BASE_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    os.environ["SYNC_DELIVER_ON_COMMIT"] = "false"
    import django

    django.setup()
    # The summary below replaces the per-event delivery log.
    logging.getLogger("sync").setLevel(logging.WARNING)


def deliver_and_report(events) -> None:
    """Deliver the events now and summarize the Marketplace's answers."""
    from signing import keys
    from signing.models import KeyPurpose
    from sync import outbox
    from sync.models import DeliveryStatus, OutboxEvent

    for purpose in KeyPurpose.values:
        keys.ensure(purpose)
    if not events:
        print("  Nothing changed: no events.")
        return
    outbox.deliver_due(limit=len(events) + 50)
    sent = OutboxEvent.objects.filter(pk__in=[event.pk for event in events])
    delivered = sent.filter(status=DeliveryStatus.DELIVERED).count()
    print(f"  {len(events)} event(s): {delivered} delivered.")
    problems = Counter(
        sent.exclude(status=DeliveryStatus.DELIVERED).values_list(
            "status", "last_http_status"
        )
    )
    for (status, http), count in problems.items():
        hint = HINTS.get(http, "see Sync > Outbox events in /admin/")
        print(f"  {count} {status} (HTTP {http or '-'}): {hint}")
