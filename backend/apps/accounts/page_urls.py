from django.urls import path
from .page_views import login_page, home_page, profile_page

urlpatterns = [
    path("", login_page, name="root_login"),
    path("login/", login_page, name="login"),
    path("home/", home_page, name="home"),
    path("profile/", profile_page, name="profile"),
]