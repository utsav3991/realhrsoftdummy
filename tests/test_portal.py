import json
from unittest import mock

import pytest

from portal import assets
from portal.views import SESSION_COMPANY

pytestmark = pytest.mark.django_db

BUILT = assets.EntryAssets(
    script="/static/marketplace/assets/main.js",
    styles=("/static/marketplace/assets/main.css",),
)


@pytest.fixture
def ram(client, make_employee):
    employee = make_employee()
    client.force_login(employee.user)
    return employee


def app_context(response):
    html = response.content.decode()
    start = html.index('id="realhrsoft-context"')
    body = html[html.index(">", start) + 1 : html.index("</script>", start)]
    return json.loads(body)


def test_marketplace_requires_login(client):
    response = client.get("/marketplace/offers")
    assert response.status_code == 302
    assert response["Location"].startswith("/login/")


def test_every_marketplace_path_mounts_the_app_with_the_employee_context(
    client, ram, acme
):
    with mock.patch("portal.views.assets.entry", return_value=BUILT):
        response = client.get("/marketplace/claims/some-id")
    assert response.status_code == 200
    html = response.content.decode()
    assert '<script type="module" src="/static/marketplace/assets/main.js">' in html
    assert 'href="/static/marketplace/assets/main.css"' in html
    context = app_context(response)
    assert context["employee"] == "Ram"
    assert context["client"] == "Acme Group"
    assert {c["id"] for c in context["companies"]} == {
        str(acme["retail"].uuid),
        str(acme["foods"].uuid),
    }
    assert context["selected"] in {c["id"] for c in context["companies"]}
    assert context["urls"]["proxy"] == "/api/marketplace"
    assert context["csrfToken"]
    assert "token" not in json.dumps(context).replace("csrfToken", "")


def test_unbuilt_app_explains_how_to_build(client, ram):
    with mock.patch("portal.views.assets.entry", return_value=None):
        response = client.get("/marketplace")
    assert b"npm run build" in response.content


def test_non_employee_goes_home(client, django_user_model):
    client.force_login(django_user_model.objects.create_user("operator"))
    assert client.get("/marketplace")["Location"] == "/"


def test_company_choice_is_validated_and_kept_in_the_session(client, ram, acme):
    foods = str(acme["foods"].uuid)
    response = client.post(
        "/company", {"company": foods}, HTTP_ACCEPT="application/json"
    )
    assert response.status_code == 204
    assert client.session[SESSION_COMPANY] == foods
    assert app_context(client.get("/marketplace"))["selected"] == foods


def test_company_choice_refuses_a_foreign_company(client, acme, make_employee):
    sita = make_employee("sita", companies=("retail",))
    client.force_login(sita.user)
    response = client.post("/company", {"company": str(acme["foods"].uuid)})
    assert response.status_code == 400


def test_manifest_entry_is_read(tmp_path, monkeypatch):
    manifest = tmp_path / ".vite" / "manifest.json"
    manifest.parent.mkdir()
    manifest.write_text(
        json.dumps({"src/main.ts": {"file": "assets/main-1.js", "css": ["assets/m.css"]}})
    )
    monkeypatch.setattr(assets, "MANIFEST", manifest)
    assert assets.entry() == assets.EntryAssets(
        script="/static/marketplace/assets/main-1.js",
        styles=("/static/marketplace/assets/m.css",),
    )
    manifest.unlink()
    assert assets.entry() is None
