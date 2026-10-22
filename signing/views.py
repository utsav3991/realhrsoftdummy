from django.http import JsonResponse
from django.views.decorators.http import require_GET

from signing import keys


@require_GET
def jwks(request):
    """The public key set the Marketplace verifies with (REALHRSOFT_JWKS_URL)."""
    response = JsonResponse(keys.jwks())
    response["Cache-Control"] = "public, max-age=60"
    return response
