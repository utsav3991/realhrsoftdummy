"""The HR back office. Every save publishes the change to the Marketplace.

Publishing happens in ``save_related`` (after inlines are saved, inside the admin's
transaction), so an employee's event already reflects their new employments.
Nothing can be deleted: deactivate instead, which the Marketplace needs as an
explicit tombstone.

Superusers see everything. Client HR users (``ClientUser``) see and choose only their
own client, its companies and its employees; other staff see nothing.
"""

from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from directory.models import Client, ClientUser, Company, Employee, Employment
from directory.services import client_of, end_foreign_employments, make_client_user
from sync import outbox

SYNC_FIELDS = ("uuid", "revision", "published_at", "published")


def superuser_only(self, request, obj=None):
    return request.user.is_superuser


def scope(request):
    """``None`` for a superuser (no limit), else the user's client (or ``False``)."""
    if request.user.is_superuser:
        return None
    return client_of(request.user) or False


class ScopedAdmin(admin.ModelAdmin):
    client_path = "client"  # lookup from this model to its Client

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        client = scope(request)
        if client is None:
            return queryset
        if client is False:
            return queryset.none()
        return queryset.filter(**{self.client_path: client.pk})

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        client = scope(request)
        if client is not None and db_field.related_model is Client:
            kwargs["queryset"] = Client.objects.filter(pk=getattr(client, "pk", None))
            kwargs["initial"] = getattr(client, "pk", None)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class PublishingAdmin(ScopedAdmin):
    actions = ["republish", "deactivate", "activate"]

    def get_readonly_fields(self, request, obj=None):
        return SYNC_FIELDS

    def has_delete_permission(self, request, obj=None):
        return False

    def prepare(self, obj):
        """Hook to adjust related state before publishing."""

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        self.prepare(form.instance)
        if outbox.publish(form.instance):
            self.message_user(
                request, f"Published revision {form.instance.revision}.", messages.INFO
            )

    def _set_active(self, request, queryset, active):
        changed = 0
        for obj in queryset:
            obj.active = active
            obj.save(update_fields=["active", "updated_at"])
            changed += outbox.publish(obj) is not None
        self.message_user(request, f"Published {changed} change(s).")

    @admin.action(description="Deactivate (publishes a tombstone)", permissions=["change"])
    def deactivate(self, request, queryset):
        self._set_active(request, queryset, False)

    @admin.action(description="Activate", permissions=["change"])
    def activate(self, request, queryset):
        self._set_active(request, queryset, True)

    @admin.action(description="Republish if the snapshot changed", permissions=["change"])
    def republish(self, request, queryset):
        changed = sum(outbox.publish(obj) is not None for obj in queryset)
        self.message_user(request, f"Published {changed} change(s).")


class CompanyInline(admin.TabularInline):
    model = Company
    fields = ("name", "active", "uuid", "revision")
    readonly_fields = ("name", "active", "uuid", "revision")
    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


class ClientUserInline(admin.TabularInline):
    model = ClientUser
    fields = ("user",)
    extra = 0
    verbose_name = "client HR user"

    has_view_permission = has_add_permission = superuser_only
    has_change_permission = has_delete_permission = superuser_only


@admin.register(Client)
class ClientAdmin(PublishingAdmin):
    client_path = "pk"
    list_display = ("organization", "email", "active", "revision", "uuid")
    list_filter = ("active",)
    search_fields = ("organization", "email", "uuid")
    inlines = [CompanyInline, ClientUserInline]

    def get_actions(self, request):
        # Client HR keeps its own client's details current but cannot switch it off.
        return super().get_actions(request) if request.user.is_superuser else {}

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        return fields if request.user.is_superuser else fields + ("active",)


@admin.register(Company)
class CompanyAdmin(PublishingAdmin):
    list_display = ("name", "client", "active", "revision", "uuid")
    list_filter = ("active", "client")
    search_fields = ("name", "uuid")

    def get_readonly_fields(self, request, obj=None):
        # A company never moves to another client.
        return SYNC_FIELDS + (("client",) if obj else ())


class EmploymentFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        client_id = self.instance.client_id
        for form in self.forms:
            # Untouched rows elsewhere are ended by the client switch itself.
            if not form.has_changed():
                continue
            data = getattr(form, "cleaned_data", None) or {}
            company = data.get("company")
            if not company or data.get("DELETE") or data.get("ended_on"):
                continue
            if company.client_id != client_id:
                raise ValidationError(
                    f"{company} belongs to {company.client}; set the employee's "
                    "client to it first (current employments elsewhere end on save)."
                )


class EmploymentInline(admin.TabularInline):
    model = Employment
    formset = EmploymentFormSet
    fields = ("company", "started_on", "ended_on")
    extra = 0
    can_delete = False

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        client = scope(request)
        if db_field.name == "company" and client is not None:
            kwargs["queryset"] = (
                Company.objects.filter(client=client) if client else Company.objects.none()
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class EmployeeAddForm(forms.ModelForm):
    """Adding an employee also creates their RealHRSoft login."""

    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput, strip=False)

    class Meta:
        model = Employee
        fields = ("username", "password", "display_name", "email", "client", "active")

    def clean_username(self):
        username = self.cleaned_data["username"]
        if get_user_model().objects.filter(username__iexact=username).exists():
            raise ValidationError("That username is taken.")
        return username

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        return password


@admin.register(Employee)
class EmployeeAdmin(PublishingAdmin):
    list_display = ("display_name", "email", "client", "active", "revision", "uuid")
    list_filter = ("active", "client")
    search_fields = ("display_name", "email", "uuid", "user__username")
    inlines = [EmploymentInline]

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is None:
            kwargs["form"] = EmployeeAddForm
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return list(EmployeeAddForm.Meta.fields)
        return ["user", "display_name", "email", "client", "active", *SYNC_FIELDS]

    def get_readonly_fields(self, request, obj=None):
        return SYNC_FIELDS + (("user",) if obj else ())

    def save_model(self, request, obj, form, change):
        if not change:
            obj.user = get_user_model().objects.create_user(
                form.cleaned_data["username"],
                email=obj.email,
                password=form.cleaned_data["password"],
            )
        super().save_model(request, obj, form, change)

    def prepare(self, obj):
        end_foreign_employments(obj)


@admin.register(ClientUser)
class ClientUserAdmin(admin.ModelAdmin):
    list_display = ("user", "client", "created_at")
    list_filter = ("client",)
    search_fields = ("user__username", "user__email", "client__organization")
    autocomplete_fields = ("user",)

    has_module_permission = has_view_permission = has_add_permission = superuser_only
    has_change_permission = has_delete_permission = superuser_only

    def save_model(self, request, obj, form, change):
        # Staff status and the Client HR group come with the link.
        make_client_user(obj.user, obj.client)
