from django.contrib import admin

from .models import Activity, Lead


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email", "organization", "status", "is_new", "owner", "created_at")
    list_filter = ("status", "is_new", "owner")
    search_fields = ("name", "email", "phone", "organization")


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("lead", "type", "due_date", "completion_status", "owner", "created_at")
    list_filter = ("type", "completion_status")
    search_fields = ("lead__name", "description")
