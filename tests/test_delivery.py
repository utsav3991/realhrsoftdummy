from unittest import mock

import jwt
import pytest
import requests

from sync import outbox
from sync.models import DeliveryStatus, OutboxEvent
from tests.conftest import marketplace_key

pytestmark = pytest.mark.django_db


def answer(status, body=None):
    response = mock.Mock(status_code=status, text=str(body))
    response.json.return_value = body
    return response


@pytest.fixture
def event(signing_keys, acme):
    return outbox.publish(acme["client"])


def test_accepted_event_is_delivered_with_its_signature(event):
    receipt = {"receipt_id": "r1", "status": "pending", "duplicate": False}
    with mock.patch("sync.outbox.requests.post", return_value=answer(202, receipt)) as post:
        assert outbox.deliver_due() == 1
    url = post.call_args.args[0]
    sent = post.call_args.kwargs
    assert url == "http://marketplace.test/api/v1/integrations/realhrsoft/events"
    assert sent["data"] == event.body.encode()
    signature = sent["headers"]["X-RealHRSoft-Signature"]
    claims = jwt.decode(
        signature,
        key=marketplace_key(signature),
        algorithms=["RS256"],
        audience="realhrsoft-marketplace-sync",
        options={"verify_iat": False},
    )
    assert claims["event_id"] == str(event.event_id)
    event.refresh_from_db()
    assert event.status == DeliveryStatus.DELIVERED
    assert event.receipt == receipt


def test_rejected_event_fails_without_retry(event):
    problem = {"code": "VALIDATION_ERROR"}
    with mock.patch("sync.outbox.requests.post", return_value=answer(422, problem)):
        outbox.deliver_due()
    event.refresh_from_db()
    assert (event.status, event.attempts, event.last_http_status) == ("failed", 1, 422)


@pytest.mark.parametrize("failure", [503, 401, "network"])
def test_transient_failures_retry_later_with_the_same_body(event, failure):
    if failure == "network":
        patch = mock.patch(
            "sync.outbox.requests.post", side_effect=requests.ConnectionError("down")
        )
    else:
        patch = mock.patch("sync.outbox.requests.post", return_value=answer(failure))
    with patch:
        outbox.deliver_due()
        event.refresh_from_db()
        assert event.status == DeliveryStatus.PENDING
        assert event.attempts == 1
        assert event.next_attempt_at > event.created_at
        assert outbox.deliver_due() == 0  # not due yet
    body = event.body
    OutboxEvent.objects.filter(pk=event.pk).update(next_attempt_at=event.created_at)
    with mock.patch("sync.outbox.requests.post", return_value=answer(202, {})) as post:
        outbox.deliver_due()
    assert post.call_args.kwargs["data"] == body.encode()


def test_gives_up_after_max_attempts(event, settings):
    settings.SYNC_MAX_ATTEMPTS = 1
    with mock.patch("sync.outbox.requests.post", return_value=answer(503)):
        outbox.deliver_due()
    event.refresh_from_db()
    assert event.status == DeliveryStatus.FAILED
