from django.views.generic import TemplateView
from django.shortcuts import render

class HomeView(TemplateView):
    template_name = "home.html"

class TranslatePageView(TemplateView):
    template_name = "translate.html"

class QAPageView(TemplateView):
    template_name = "qa.html"

class HistoryPageView(TemplateView):
    template_name = "history.html"

def login_page(request):
    return render(request, "login.html")

def home_page(request):
    return render(request, "home.html")

def register_page(request):
    return render(request, "register.html")