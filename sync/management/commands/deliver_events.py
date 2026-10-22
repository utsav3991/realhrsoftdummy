"""Deliver pending outbox events to the Marketplace.

    manage.py deliver_events            # deliver what is due, once
    manage.py deliver_events --loop     # keep delivering (retries included)
    manage.py deliver_events --retry    # requeue undelivered events now, then deliver
"""

import time

from django.core.management.base import BaseCommand

from sync import outbox
from sync.models import OutboxEvent


class Command(BaseCommand):
    help = "Deliver pending snapshot events to the Marketplace."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Run until stopped.")
        parser.add_argument(
            "--retry",
            action="store_true",
            help="First requeue pending and failed events, skipping their backoff.",
        )
        parser.add_argument(
            "--interval", type=float, default=2.0, help="Seconds between polls."
        )

    def handle(self, *args, **options):
        if options["retry"]:
            count = outbox.retry(OutboxEvent.objects.all())
            self.stdout.write(f"{count} event(s) requeued.")
        while True:
            sent = outbox.deliver_due()
            if sent or not options["loop"]:
                self.stdout.write(f"{sent} delivery attempt(s).")
            if not options["loop"]:
                return
            time.sleep(options["interval"])
