from django.contrib import admin
from .models import Service, DemoWorkspace, Appointment, Applicant, Review, Availability, UserProfile
admin.site.site_header = "GoClinical · Administración Django"
admin.site.site_title = "GoClinical"
@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "category", "price", "duration")
    search_fields = ("name", "code")
    list_filter = ("category",)
@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("id", "service", "date", "time", "status", "price", "workspace")
    list_filter = ("status", "date")
    readonly_fields = ("payment_key", "created_at")
admin.site.register([UserProfile, DemoWorkspace, Applicant, Review, Availability])
