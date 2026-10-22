from django.contrib import admin, messages

from sync import outbox
from sync.models import OutboxEvent


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display = (
        "event_type",
        "aggregate_uuid",
        "aggregate_revision",
        "status",
        "attempts",
        "last_http_status",
        "created_at",
        "delivered_at",
    )
    list_filter = ("status", "event_type", "last_http_status")
    search_fields = ("event_id", "aggregate_uuid")
    readonly_fields = [field.name for field in OutboxEvent._meta.fields]
    actions = ["retry_now"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Retry selected events now")
    def retry_now(self, request, queryset):
        count = outbox.retry(queryset)
        outbox.kick()
        self.message_user(request, f"{count} event(s) queued.", messages.SUCCESS)
