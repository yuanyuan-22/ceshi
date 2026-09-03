from django.urls import path

from .views import (
    AppointmentDetailView,
    AppointmentListCreateView,
    DoctorListView,
    DoctorProfileAdminView,
    DoctorScheduleAdminView,
    DoctorAvailableSlotsView,
    appointment_summary,
)

urlpatterns = [
    path("doctors/", DoctorListView.as_view()),
    path("admin/doctors/", DoctorProfileAdminView.as_view()),
    path("admin/schedules/", DoctorScheduleAdminView.as_view()),
    path("doctors/<int:doctor_id>/slots/", DoctorAvailableSlotsView.as_view()),
    path("", AppointmentListCreateView.as_view()),
    path("<int:pk>/", AppointmentDetailView.as_view()),
    path("summary/", appointment_summary),
]
