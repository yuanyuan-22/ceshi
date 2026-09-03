from django.contrib import admin

from .models import Appointment, DoctorProfile, DoctorSchedule


@admin.register(DoctorProfile)
class DoctorProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "department", "hospital", "title", "is_active")
    search_fields = ("user__username", "department", "hospital", "title")
    list_filter = ("is_active", "department", "hospital")


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("patient", "doctor", "appointment_time", "status", "created_at")
    list_filter = ("status", "appointment_time")
    search_fields = ("patient__username", "doctor__username", "reason")
    ordering = ("appointment_time", "created_at")


@admin.register(DoctorSchedule)
class DoctorScheduleAdmin(admin.ModelAdmin):
    list_display = ("doctor", "schedule_date", "start_time", "end_time", "slot_minutes", "max_appointments_per_slot", "is_active")
    list_filter = ("schedule_date", "is_active")
    search_fields = ("doctor__username", "note")
    ordering = ("schedule_date", "doctor", "start_time")
