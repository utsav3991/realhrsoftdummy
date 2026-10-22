from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from portal import proxy, views
from signing.views import jwks
from sync.api import SnapshotViewSet

# Snapshot API: /api/marketplace-sync/v1/{partners|companies|employees}[/{uuid}]
snapshots = SimpleRouter(trailing_slash=False, use_regex_path=False)
snapshots.register("<str:kind>", SnapshotViewSet, basename="snapshot")

urlpatterns = [
    path("admin/", admin.site.urls),
    path(".well-known/jwks.json", jwks, name="jwks"),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.home, name="portal-home"),
    path("company", views.select_company, name="portal-select-company"),
    # The Marketplace employee screens (Vue, history routing): every path is the app.
    path("marketplace", views.marketplace, name="portal-marketplace"),
    path("marketplace/<path:rest>", views.marketplace),
    path("api/marketplace/<path:path>", proxy.proxy, name="marketplace-proxy"),
    path("api/marketplace-sync/v1/", include(snapshots.urls)),
]
