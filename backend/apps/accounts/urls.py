from django.urls import path
from .views import RegisterView, ProfileView, ChangePasswordView, me_view

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("profile/password/", ChangePasswordView.as_view(), name="change_password"),
    path("me/", me_view, name="me"),
]