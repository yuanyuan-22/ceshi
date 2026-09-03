from __future__ import annotations

from datetime import datetime, timedelta

from django.contrib.auth.models import Group, User
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Appointment, DoctorProfile, DoctorSchedule
from .serializers import AppointmentCreateSerializer, AppointmentSerializer, DoctorProfileSerializer, DoctorScheduleSerializer


def _is_admin(user):
    return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))


def _is_doctor(user):
    return bool(
        user
        and user.is_authenticated
        and (
            user.groups.filter(name="doctor").exists()
            or hasattr(user, "doctor_profile")
        )
    )


class DoctorListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        queryset = DoctorProfile.objects.select_related("user").filter(is_active=True).order_by("department", "user__username")
        return Response(DoctorProfileSerializer(queryset, many=True).data)


class DoctorProfileAdminView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not _is_admin(request.user):
            return Response({"detail": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        queryset = DoctorProfile.objects.select_related("user").order_by("department", "user__username")
        return Response(DoctorProfileSerializer(queryset, many=True).data)

    def post(self, request):
        if not _is_admin(request.user):
            return Response({"detail": "forbidden"}, status=status.HTTP_403_FORBIDDEN)

        username = (request.data.get("username") or "").strip()
        if not username:
            return Response({"detail": "username required"}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(username=username).first()
        if not user:
            return Response({"detail": "doctor user not found"}, status=status.HTTP_400_BAD_REQUEST)

        doctor_group, _ = Group.objects.get_or_create(name="doctor")
        user.groups.add(doctor_group)

        profile, _ = DoctorProfile.objects.get_or_create(user=user)
        profile.department = request.data.get("department", profile.department)
        profile.hospital = request.data.get("hospital", profile.hospital)
        profile.title = request.data.get("title", profile.title)
        profile.bio = request.data.get("bio", profile.bio)
        profile.is_active = bool(request.data.get("is_active", True))
        profile.save()

        return Response(DoctorProfileSerializer(profile).data, status=status.HTTP_201_CREATED)


class DoctorScheduleAdminView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not _is_admin(request.user):
            return Response({"detail": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        queryset = DoctorSchedule.objects.select_related("doctor").order_by("schedule_date", "start_time", "doctor__username")
        return Response(DoctorScheduleSerializer(queryset, many=True).data)

    def post(self, request):
        if not _is_admin(request.user):
            return Response({"detail": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        serializer = DoctorScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        schedule = serializer.save()
        return Response(DoctorScheduleSerializer(schedule).data, status=status.HTTP_201_CREATED)


class AppointmentListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if _is_admin(user):
            queryset = Appointment.objects.select_related("patient", "doctor", "doctor__doctor_profile").all()
        elif _is_doctor(user):
            queryset = Appointment.objects.select_related("patient", "doctor", "doctor__doctor_profile").filter(doctor=user)
        else:
            queryset = Appointment.objects.select_related("patient", "doctor", "doctor__doctor_profile").filter(patient=user)
        queryset = queryset.order_by("appointment_time", "created_at")
        return Response(AppointmentSerializer(queryset, many=True).data)

    def post(self, request):
        serializer = AppointmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        appointment = serializer.save(patient=request.user, status=Appointment.STATUS_BOOKED)
        return Response(AppointmentSerializer(appointment).data, status=status.HTTP_201_CREATED)


class AppointmentDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        appointment = Appointment.objects.select_related("patient", "doctor", "doctor__doctor_profile").filter(pk=pk).first()
        if not appointment:
            return Response({"detail": "not found"}, status=status.HTTP_404_NOT_FOUND)

        if request.user != appointment.patient and request.user != appointment.doctor and not _is_admin(request.user):
            return Response({"detail": "forbidden"}, status=status.HTTP_403_FORBIDDEN)

        status_value = request.data.get("status")
        if status_value not in dict(Appointment.STATUS_CHOICES):
            return Response({"detail": "invalid status"}, status=status.HTTP_400_BAD_REQUEST)

        appointment.status = status_value
        appointment.save(update_fields=["status", "updated_at"])
        return Response(AppointmentSerializer(appointment).data)


class DoctorAvailableSlotsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, doctor_id):
        doctor = User.objects.filter(id=doctor_id).first()
        if not doctor:
            return Response({"detail": "doctor not found"}, status=status.HTTP_404_NOT_FOUND)

        date_str = request.query_params.get("date")
        if not date_str:
            return Response({"detail": "date required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return Response({"detail": "invalid date format"}, status=status.HTTP_400_BAD_REQUEST)

        schedules = DoctorSchedule.objects.filter(doctor=doctor, schedule_date=target_date, is_active=True).order_by("start_time")
        slots = []
        seen_slots = set()
        for schedule in schedules:
            current_dt = datetime.combine(target_date, schedule.start_time)
            end_dt = datetime.combine(target_date, schedule.end_time)
            while current_dt < end_dt:
                slot_key = current_dt.isoformat()
                if slot_key in seen_slots:
                    current_dt += timedelta(minutes=schedule.slot_minutes)
                    continue
                slot_count = Appointment.objects.filter(
                    doctor=doctor,
                    appointment_time=current_dt,
                ).exclude(status=Appointment.STATUS_CANCELLED).count()
                if slot_count < schedule.max_appointments_per_slot:
                    seen_slots.add(slot_key)
                    slots.append({
                        "appointment_time": slot_key,
                        "remaining": schedule.max_appointments_per_slot - slot_count,
                        "slot_minutes": schedule.slot_minutes,
                    })
                current_dt += timedelta(minutes=schedule.slot_minutes)

        return Response({
            "doctor_id": doctor.id,
            "date": target_date.isoformat(),
            "slots": slots,
        })


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def appointment_summary(request):
    user = request.user
    if _is_admin(user):
        queryset = Appointment.objects.all()
    elif _is_doctor(user):
        queryset = Appointment.objects.filter(doctor=user)
    else:
        queryset = Appointment.objects.filter(patient=user)

    return Response({
        "total": queryset.count(),
        "waiting": queryset.filter(status=Appointment.STATUS_BOOKED).count(),
        "confirmed": queryset.filter(status=Appointment.STATUS_BOOKED).count(),
        "done": queryset.filter(status=Appointment.STATUS_DONE).count(),
    })
