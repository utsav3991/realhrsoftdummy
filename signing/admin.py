from django.contrib import admin, messages

from signing import keys
from signing.models import KeyPurpose, SigningKey


@admin.register(SigningKey)
class SigningKeyAdmin(admin.ModelAdmin):
    list_display = ("kid", "purpose", "status", "created_at", "retired_at", "revoked_at")
    list_filter = ("purpose", "status")
    readonly_fields = ("kid", "purpose", "status", "created_at", "retired_at", "revoked_at")
    exclude = ("private_pem",)
    actions = ["rotate_purpose", "revoke_keys"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Rotate: new active key for each selected key's purpose")
    def rotate_purpose(self, request, queryset):
        for purpose in set(queryset.values_list("purpose", flat=True)):
            key = keys.rotate(purpose)
            self.message_user(request, f"New {KeyPurpose(purpose).label} key {key.kid}.")

    @admin.action(description="Revoke selected keys (drop from the JWKS now)")
    def revoke_keys(self, request, queryset):
        for key in queryset:
            keys.revoke(key.kid)
        self.message_user(
            request,
            "Revoked. If compromised, ask the Marketplace to list the kid in "
            "REALHRSOFT_REVOKED_KIDS, and rotate to get a new active key.",
            messages.WARNING,
        )
