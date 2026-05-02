from django.contrib import admin

from .models import TripSubmission


@admin.register(TripSubmission)
class TripSubmissionAdmin(admin.ModelAdmin):
    list_display = ("log_date", "duty_start", "driver_name", "created_at")
    readonly_fields = ("created_at",)
