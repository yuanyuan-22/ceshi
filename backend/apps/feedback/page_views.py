from django.views.generic import TemplateView


class SystemFeedbackPageView(TemplateView):
    template_name = "system_feedback.html"
