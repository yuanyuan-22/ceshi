from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class DoctorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="doctor_profile")
    department = models.CharField(max_length=100, blank=True, default="")
    hospital = models.CharField(max_length=200, blank=True, default="")
    title = models.CharField(max_length=100, blank=True, default="")
    bio = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} doctor profile"


class DoctorSchedule(models.Model):
    doctor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="schedules")
    schedule_date = models.DateField(default=timezone.localdate)
    start_time = models.TimeField()
    end_time = models.TimeField()
    slot_minutes = models.PositiveIntegerField(default=30)
    max_appointments_per_slot = models.PositiveIntegerField(default=5)
    is_active = models.BooleanField(default=True)
    note = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["schedule_date", "start_time", "doctor"]
        indexes = [
            models.Index(fields=["doctor", "schedule_date"]),
        ]

    def __str__(self):
        return f"{self.doctor.username} {self.schedule_date} {self.start_time}-{self.end_time}"


class Appointment(models.Model):
    STATUS_BOOKED = "BOOKED"
    STATUS_DONE = "DONE"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_CHOICES = [
        (STATUS_BOOKED, "Booked"),
        (STATUS_DONE, "Done"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="appointments")
    doctor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="doctor_appointments")
    appointment_time = models.DateTimeField()
    reason = models.CharField(max_length=255, blank=True, default="")
    note = models.TextField(blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_BOOKED)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["appointment_time", "created_at"]
        indexes = [
            models.Index(fields=["doctor", "appointment_time"]),
            models.Index(fields=["patient", "appointment_time"]),
        ]

    def __str__(self):
        return f"{self.patient_id}->{self.doctor_id} @ {self.appointment_time}"
