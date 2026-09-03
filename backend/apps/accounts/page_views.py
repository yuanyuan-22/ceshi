from django.shortcuts import render

def login_page(request):
    return render(request, "login.html")

def home_page(request):
    return render(request, "home.html")

def profile_page(request):
    return render(request, "profile.html")