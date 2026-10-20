from django.contrib import admin

from .models import Authorization, AuditLog, Client, Episode, FundingSource, Medication, Oca, WaitlistEntry


@admin.register(FundingSource)
class FundingSourceAdmin(admin.ModelAdmin):
    list_display = ["name", "level_of_care", "bed_capacity", "is_active"]
    list_filter = ["level_of_care", "is_active"]
    list_editable = ["level_of_care", "bed_capacity", "is_active"]
    search_fields = ["name"]


@admin.register(Oca)
class OcaAdmin(admin.ModelAdmin):
    list_display = ["code", "description", "is_active"]
    list_filter = ["funding_sources", "is_active"]
    search_fields = ["code", "description"]
    filter_horizontal = ["funding_sources"]


class EpisodeInline(admin.TabularInline):
    model = Episode
    extra = 0
    fields = ["record_id", "funding_source", "admit_date", "discharge_date", "discharge_reason"]
    show_change_link = True


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ["last_name", "first_name", "date_of_birth", "ssn_masked"]
    search_fields = ["first_name", "last_name", "ssn_last4", "episodes__record_id"]
    readonly_fields = ["ssn_masked", "created_at", "updated_at"]
    exclude = ["ssn_encrypted", "ssn_hash", "ssn_last4"]
    inlines = [EpisodeInline]


class AuthorizationInline(admin.TabularInline):
    model = Authorization
    extra = 0


class MedicationInline(admin.TabularInline):
    model = Medication
    extra = 0


@admin.register(Episode)
class EpisodeAdmin(admin.ModelAdmin):
    list_display = ["client", "record_id", "funding_source", "admit_date", "discharge_date", "discharge_reason"]
    list_filter = ["level_of_care", "funding_source", "discharge_reason"]
    search_fields = ["client__first_name", "client__last_name", "record_id"]
    date_hierarchy = "admit_date"
    autocomplete_fields = ["client"]
    inlines = [AuthorizationInline, MedicationInline]


@admin.register(Authorization)
class AuthorizationAdmin(admin.ModelAdmin):
    list_display = ["auth_number", "episode", "funding_source", "oca", "start_date", "end_date", "days_authorized"]
    list_filter = ["funding_source", "oca"]
    search_fields = ["auth_number", "episode__client__last_name", "episode__record_id"]
    autocomplete_fields = ["episode"]


@admin.register(WaitlistEntry)
class WaitlistEntryAdmin(admin.ModelAdmin):
    list_display = ["client", "funding_source", "status", "rank", "date_added", "closed_date"]
    list_filter = ["status", "funding_source"]
    search_fields = ["client__first_name", "client__last_name"]
    autocomplete_fields = ["client", "admitted_episode"]


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["timestamp", "user", "action", "model", "object_repr"]
    list_filter = ["action", "model"]
    search_fields = ["object_repr", "user__username"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
