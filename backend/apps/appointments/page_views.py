from django.views.generic import TemplateView


class AppointmentPageView(TemplateView):
    template_name = "appointments.html"

