from django.contrib.auth.models import User
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes

from .models import UserProfile


@api_view(["GET"])
@permission_classes([])
def me_view(request):
    if request.user.is_authenticated:
        return Response({
            "id": request.user.id,
            "username": request.user.username,
            "email": request.user.email,
            "is_staff": request.user.is_staff,
            "is_superuser": request.user.is_superuser,
            "is_doctor": hasattr(request.user, "doctor_profile"),
        })
    return Response({"error": "not authenticated"}, status=401)


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username = (request.data.get("username") or "").strip()
        password = (request.data.get("password") or "").strip()
        email = (request.data.get("email") or "").strip()

        if not username or not password:
            return Response({"error": "username/password required"}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(username=username).exists():
            return Response({"error": "username already exists"}, status=status.HTTP_409_CONFLICT)

        user = User.objects.create_user(
            username=username,
            password=password,
            email=email
        )
        UserProfile.objects.create(user=user)
        return Response({
            "status": "OK",
            "user_id": user.id,
            "username": user.username,
            "email": email
        }, status=status.HTTP_201_CREATED)


class ProfileView(APIView):
    def get(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response({"error": "not authenticated"}, status=status.HTTP_401_UNAUTHORIZED)

        profile, _ = UserProfile.objects.get_or_create(user=user)
        return Response(profile.to_dict())

    def put(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response({"error": "not authenticated"}, status=status.HTTP_401_UNAUTHORIZED)

        profile, _ = UserProfile.objects.get_or_create(user=user)
        data = request.data

        if "email" in data:
            user.email = data.get("email", "") or ""
            user.save()

        profile.phone = data.get("phone", "") or profile.phone
        profile.gender = data.get("gender", "") or profile.gender
        profile.age = int(data["age"]) if data.get("age") not in [None, "", "null"] else profile.age
        profile.occupation = data.get("occupation", "") or profile.occupation
        profile.department = data.get("department", "") or profile.department
        profile.hospital = data.get("hospital", "") or profile.hospital
        profile.bio = data.get("bio", "") or profile.bio
        profile.avatar_url = data.get("avatar_url", "") or profile.avatar_url
        profile.save()

        return Response(profile.to_dict())


class ChangePasswordView(APIView):
    def post(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response({"error": "not authenticated"}, status=status.HTTP_401_UNAUTHORIZED)

        old_password = request.data.get("old_password", "")
        new_password = request.data.get("new_password", "")

        if not user.check_password(old_password):
            return Response({"error": "old password incorrect"}, status=status.HTTP_400_BAD_REQUEST)

        if len(new_password) < 6:
            return Response({"error": "password too short"}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()

        return Response({"status": "password changed"})
