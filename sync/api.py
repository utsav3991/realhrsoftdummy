"""The protected snapshot API that Marketplace reconciliation reads.

Matches the consumer in the Marketplace's ``identity_access/services/realhrsoft_api.py``:

- ``GET /{kind}?cursor=&limit=`` (kind: partners, companies, employees) returns
  ``{"items": [...], "next_cursor": "<c>" | null}``;
- ``GET /{kind}/{uuid}`` returns one item, 404 when unknown or never published;
- an item is ``{"aggregate_uuid", "aggregate_revision", "data"}``, where ``data`` is
  the published snapshot at that revision; deactivated records are items with
  ``active`` false, never omitted.

Authentication: ``Authorization: Bearer <SNAPSHOT_API_TOKEN>``.

Dummy limitation: the cursor is a keyset position, not a database snapshot, so a
record changed mid-scan shows its newer revision. That is safe for the Marketplace
(revisions are compared per record) but weaker than the "one consistent snapshot"
the contract asks of the real RealHRSoft.
"""

import base64
import binascii
import hmac
import json

from django.conf import settings
from rest_framework import authentication, exceptions, permissions, viewsets
from rest_framework.response import Response

from directory.models import Client, Company, Employee

KINDS = {"partners": Client, "companies": Company, "employees": Employee}
MAX_LIMIT = 100


class SnapshotTokenAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        expected = settings.SNAPSHOT_API_TOKEN
        header = request.headers.get("Authorization", "")
        scheme, _, token = header.partition(" ")
        if not expected or scheme.lower() != "bearer" or not token:
            raise exceptions.AuthenticationFailed()
        if not hmac.compare_digest(token.encode(), expected.encode()):
            raise exceptions.AuthenticationFailed()
        return ("marketplace", None)

    def authenticate_header(self, request):
        return "Bearer"


def _item(record) -> dict:
    return {
        "aggregate_uuid": str(record.uuid),
        "aggregate_revision": record.revision,
        "data": record.published,
    }


def _encode(position: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"after": position}).encode()).decode()


def _decode(cursor: str) -> int:
    try:
        position = json.loads(base64.urlsafe_b64decode(cursor.encode()))["after"]
    except (binascii.Error, ValueError, KeyError, TypeError):
        raise exceptions.ValidationError({"cursor": "Invalid cursor."}) from None
    if not isinstance(position, int):
        raise exceptions.ValidationError({"cursor": "Invalid cursor."})
    return position


class SnapshotViewSet(viewsets.ViewSet):
    authentication_classes = [SnapshotTokenAuthentication]
    permission_classes = [permissions.AllowAny]
    lookup_value_converter = "uuid"

    def _published(self, kind):
        model = KINDS.get(kind)
        if model is None:
            raise exceptions.NotFound()
        return model.objects.filter(revision__gte=1)

    def list(self, request, kind):
        records = self._published(kind).order_by("id")
        cursor = request.query_params.get("cursor")
        if cursor:
            records = records.filter(id__gt=_decode(cursor))
        try:
            limit = int(request.query_params.get("limit", MAX_LIMIT))
        except ValueError:
            raise exceptions.ValidationError({"limit": "Must be a number."}) from None
        limit = max(1, min(limit, MAX_LIMIT))
        page = list(records[: limit + 1])
        more = len(page) > limit
        page = page[:limit]
        return Response(
            {
                "items": [_item(record) for record in page],
                "next_cursor": _encode(page[-1].id) if more else None,
            },
            headers={"Cache-Control": "no-store"},
        )

    def retrieve(self, request, kind, pk):
        record = self._published(kind).filter(uuid=pk).first()
        if record is None:
            raise exceptions.NotFound()
        return Response(_item(record), headers={"Cache-Control": "no-store"})
