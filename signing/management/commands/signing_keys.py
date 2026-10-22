"""Manage signing keys.

    manage.py signing_keys ensure            # an active key per purpose (idempotent)
    manage.py signing_keys rotate employee   # or sync
    manage.py signing_keys revoke <kid>
    manage.py signing_keys import --pem ~/.realhrsoft-dev-key.pem --kid realhrsoft-dev-1
    manage.py signing_keys list
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from signing import keys
from signing.models import KeyPurpose, SigningKey


class Command(BaseCommand):
    help = "Create, rotate, revoke or list RS256 signing keys."

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)
        sub.add_parser("ensure", help="Create missing active keys.")
        rotate = sub.add_parser("rotate", help="Replace a purpose's active key.")
        rotate.add_argument("purpose", choices=KeyPurpose.values)
        revoke = sub.add_parser("revoke", help="Remove a key from the JWKS now.")
        revoke.add_argument("kid")
        sub.add_parser("list", help="Show keys and their status.")
        imported = sub.add_parser(
            "import", help="Use an existing RSA private key (PEM) as the active key."
        )
        imported.add_argument("--pem", required=True, help="Private key PEM path.")
        imported.add_argument("--kid", required=True, help="Key ID the verifier knows.")
        imported.add_argument(
            "--purpose",
            choices=[*KeyPurpose.values, "all"],
            default="all",
            help="Default: both employee tokens and sync deliveries.",
        )

    def handle(self, *args, **options):
        action = options["action"]
        if action == "ensure":
            for purpose in KeyPurpose.values:
                self.stdout.write(f"{purpose}: {keys.ensure(purpose).kid}")
        elif action == "rotate":
            key = keys.rotate(options["purpose"])
            self.stdout.write(f"New active {key.purpose} key: {key.kid}")
        elif action == "import":
            path = Path(options["pem"]).expanduser()
            purposes = (
                KeyPurpose.values if options["purpose"] == "all" else [options["purpose"]]
            )
            try:
                pem = path.read_bytes()
                for purpose in purposes:
                    key = keys.import_pem(purpose, pem, options["kid"])
                    self.stdout.write(f"{purpose}: now signs with {key.kid}")
            except (OSError, ValueError) as error:
                raise CommandError(f"Cannot import {path}: {error}") from None
        elif action == "revoke":
            try:
                revoked = keys.revoke(options["kid"])
            except SigningKey.DoesNotExist:
                raise CommandError("No such kid.") from None
            self.stdout.write(
                f"Revoked {options['kid']}. Ask the Marketplace to add it to "
                "REALHRSOFT_REVOKED_KIDS if it was compromised."
            )
            for key in revoked:
                if not SigningKey.objects.filter(
                    purpose=key.purpose, status="active"
                ).exists():
                    self.stdout.write(f"No active {key.purpose} key left: rotate one.")
        else:
            for key in SigningKey.objects.all():
                self.stdout.write(
                    f"{key.kid:40} {key.purpose:9} {key.status:8} {key.created_at:%F %T}"
                )
