import json

import jwt
import pytest
from django.contrib.auth import get_user_model

from directory.models import Client, Company, Employee, Employment
from signing import keys
from signing.models import KeyPurpose


@pytest.fixture(autouse=True)
def _settings(settings):
    settings.SYNC_DELIVER_ON_COMMIT = False
    settings.ISSUER = "http://realhrsoft.test"
    settings.MARKETPLACE_URL = "http://marketplace.test"
    settings.SNAPSHOT_API_TOKEN = "snapshot-secret"


@pytest.fixture
def signing_keys(db):
    return {purpose: keys.ensure(purpose) for purpose in KeyPurpose.values}


@pytest.fixture
def acme(db):
    client = Client.objects.create(
        organization="Acme Group",
        first_name="Gita",
        last_name="Sharma",
        email="gita@acme.example",
    )
    return {
        "client": client,
        "retail": Company.objects.create(client=client, name="Acme Retail"),
        "foods": Company.objects.create(client=client, name="Acme Foods"),
    }


@pytest.fixture
def make_employee(db, acme):
    def make(username="ram", companies=("retail", "foods"), **fields):
        user = get_user_model().objects.create_user(username, password="pw-12345678")
        employee = Employee.objects.create(
            user=user,
            display_name=fields.pop("display_name", username.title()),
            email=f"{username}@acme.example",
            client=fields.pop("client", acme["client"]),
            **fields,
        )
        for name in companies:
            Employment.objects.create(employee=employee, company=acme[name])
        return employee

    return make


def marketplace_keys():
    """The key set as the Marketplace would fetch it from our JWKS URL."""
    return jwt.PyJWKSet.from_dict(json.loads(json.dumps(keys.jwks())))


def marketplace_key(token):
    kid = jwt.get_unverified_header(token)["kid"]
    for key in marketplace_keys().keys:
        if key.key_id == kid:
            return key.key
    raise LookupError(kid)
