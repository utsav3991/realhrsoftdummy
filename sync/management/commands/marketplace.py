"""Talk to the Marketplace as RealHRSoft's backend (signed requests).

    manage.py marketplace status                          # sync health
    manage.py marketplace reconcile                       # full repair read
    manage.py marketplace reconcile --scope employee --target <uuid>
    manage.py marketplace company <company uuid>          # how it was mapped
    manage.py marketplace env                             # Marketplace .env lines
"""

import json

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from sync import marketplace

SCOPES = ("full", "partner", "company", "employee")


class Command(BaseCommand):
    help = "Signed calls to the Marketplace integration API."

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)
        sub.add_parser("status", help="Receipt counts, lag and problems.")
        reconcile = sub.add_parser("reconcile", help="Ask for a repair read.")
        reconcile.add_argument("--scope", choices=SCOPES, default="full")
        reconcile.add_argument("--target", help="RealHRSoft UUID (not for full).")
        company = sub.add_parser("company", help="A synchronized company's mapping.")
        company.add_argument("uuid")
        sub.add_parser("env", help="Print the Marketplace .env lines for this dummy.")

    def handle(self, *args, **options):
        action = options["action"]
        if action == "env":
            return self._env()
        if action == "reconcile" and (options["scope"] == "full") == bool(
            options["target"]
        ):
            raise CommandError("--target is required for one record, and only then.")
        try:
            if action == "status":
                response = marketplace.sync_status()
            elif action == "reconcile":
                response = marketplace.reconcile(options["scope"], options["target"])
            else:
                response = marketplace.company(options["uuid"])
        except requests.RequestException as error:
            raise CommandError(
                f"Marketplace unreachable at {settings.MARKETPLACE_URL}: {error}"
            ) from None
        self.stdout.write(f"HTTP {response.status_code}")
        try:
            self.stdout.write(json.dumps(response.json(), indent=2))
        except ValueError:
            self.stdout.write(response.text[:2000])
        if response.status_code == 401:
            self.stderr.write(
                "401: the Marketplace does not trust this dummy's keys yet; see "
                "`manage.py marketplace env`."
            )

    def _env(self):
        issuer = settings.ISSUER.rstrip("/")
        token = settings.SNAPSHOT_API_TOKEN or "<set SNAPSHOT_API_TOKEN in this .env>"
        self.stdout.write(
            "# realhrsoft-marketplace-rest-api/.env (then restart web, worker, beat)\n"
            "# Remove or empty REALHRSOFT_JWKS: a pinned key set wins over the URL.\n"
            f"REALHRSOFT_ISSUER={settings.ISSUER}\n"
            "REALHRSOFT_JWKS=\n"
            f"REALHRSOFT_JWKS_URL={issuer}{reverse('jwks')}\n"
            f"REALHRSOFT_API_URL={issuer}/api/marketplace-sync/v1\n"
            f"REALHRSOFT_API_TOKEN={token}"
        )
