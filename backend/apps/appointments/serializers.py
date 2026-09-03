from __future__ import annotations

from rest_framework import serializers

from .models import Appointment, DoctorProfile, DoctorSchedule


class DoctorProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    full_name = serializers.SerializerMethodField()
    user_id = serializers.IntegerField(source="user.id", read_only=True)

    class Meta:
        model = DoctorProfile
        fields = [
            "id",
            "user_id",
            "username",
            "full_name",
            "department",
            "hospital",
            "title",
            "bio",
            "is_active",
        ]

    def get_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.username


class DoctorScheduleSerializer(serializers.ModelSerializer):
    doctor_username = serializers.CharField(source="doctor.username", read_only=True)

    class Meta:
        model = DoctorSchedule
        fields = [
            "id",
            "doctor",
            "doctor_username",
            "schedule_date",
            "start_time",
            "end_time",
            "slot_minutes",
            "max_appointments_per_slot",
            "is_active",
            "note",
        ]

    def validate(self, attrs):
        doctor = attrs.get("doctor") or getattr(self.instance, "doctor", None)
        schedule_date = attrs.get("schedule_date") or getattr(self.instance, "schedule_date", None)
        start_time = attrs.get("start_time") or getattr(self.instance, "start_time", None)
        end_time = attrs.get("end_time") or getattr(self.instance, "end_time", None)

        if start_time >= end_time:
            raise serializers.ValidationError("schedule end time must be after start time")

        queryset = DoctorSchedule.objects.filter(
            doctor=doctor,
            schedule_date=schedule_date,
            is_active=True,
        )
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)

        for existing in queryset:
            if existing.start_time < end_time and start_time < existing.end_time:
                raise serializers.ValidationError("doctor schedule overlaps with an existing schedule")

        return attrs


class AppointmentSerializer(serializers.ModelSerializer):
    doctor_name = serializers.SerializerMethodField()
    patient_name = serializers.SerializerMethodField()
    doctor_profile = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = [
            "id",
            "patient",
            "patient_name",
            "doctor",
            "doctor_name",
            "doctor_profile",
            "appointment_time",
            "reason",
            "note",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["patient", "status", "created_at", "updated_at"]

    def get_doctor_name(self, obj):
        return obj.doctor.get_full_name() or obj.doctor.username

    def get_patient_name(self, obj):
        return obj.patient.get_full_name() or obj.patient.username

    def get_doctor_profile(self, obj):
        profile = getattr(obj.doctor, "doctor_profile", None)
        if not profile:
            return None
        return {
            "department": profile.department,
            "hospital": profile.hospital,
            "title": profile.title,
        }


class AppointmentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = ["doctor", "appointment_time", "reason", "note"]

    def validate(self, attrs):
        doctor = attrs["doctor"]
        appointment_time = attrs["appointment_time"]

        profile = getattr(doctor, "doctor_profile", None)
        if not profile or not profile.is_active:
            raise serializers.ValidationError("doctor is not available")

        schedule_date = appointment_time.date()
        schedules = DoctorSchedule.objects.filter(
            doctor=doctor,
            schedule_date=schedule_date,
            is_active=True,
        )
        if not schedules.exists():
            raise serializers.ValidationError("doctor has no schedule for this date")

        matched_schedule = None
        for schedule in schedules:
            if schedule.start_time <= appointment_time.time() < schedule.end_time:
                minute_delta = (
                    appointment_time.hour * 60
                    + appointment_time.minute
                    - schedule.start_time.hour * 60
                    - schedule.start_time.minute
                )
                if minute_delta % schedule.slot_minutes == 0:
                    matched_schedule = schedule
                    break
        if matched_schedule is None:
            raise serializers.ValidationError("appointment time is not in doctor's available schedule")

        same_slot_count = Appointment.objects.filter(
            doctor=doctor,
            appointment_time=appointment_time,
        ).exclude(status=Appointment.STATUS_CANCELLED).count()
        if same_slot_count >= matched_schedule.max_appointments_per_slot:
            raise serializers.ValidationError("appointment slot is full")

        return attrs
