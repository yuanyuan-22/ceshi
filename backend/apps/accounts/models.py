from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    ROLE_USER = "user"
    ROLE_EXPERT = "expert"
    ROLE_ADMIN = "admin"
    ROLE_CHOICES = [
        (ROLE_USER, "User"),
        (ROLE_EXPERT, "Expert"),
        (ROLE_ADMIN, "Admin"),
    ]

    GENDER_CHOICES = [
        ("M", "Male"),
        ("F", "Female"),
        ("O", "Other"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")

    phone = models.CharField("Phone", max_length=20, blank=True, default="")
    gender = models.CharField("Gender", max_length=1, choices=GENDER_CHOICES, blank=True, default="")
    age = models.IntegerField("Age", null=True, blank=True)
    occupation = models.CharField("Occupation", max_length=100, blank=True, default="")
    department = models.CharField("Department", max_length=100, blank=True, default="")
    hospital = models.CharField("Hospital", max_length=200, blank=True, default="")
    bio = models.TextField("Bio", blank=True, default="")
    role = models.CharField("Role", max_length=16, choices=ROLE_CHOICES, default=ROLE_USER)

    avatar_url = models.URLField("Avatar URL", max_length=500, blank=True, default="")

    created_at = models.DateTimeField("Created At", auto_now_add=True)
    updated_at = models.DateTimeField("Updated At", auto_now=True)

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self):
        return f"{self.user.username} profile"

    @property
    def display_name(self):
        return self.user.username

    @property
    def effective_role(self):
        if self.user.is_superuser or self.user.is_staff:
            return self.ROLE_ADMIN
        if self.role == self.ROLE_ADMIN:
            return self.ROLE_ADMIN
        if self.role == self.ROLE_EXPERT:
            return self.ROLE_EXPERT
        return self.ROLE_USER

    def to_dict(self):
        return {
            "id": self.user.id,
            "username": self.user.username,
            "email": self.user.email,
            "phone": self.phone,
            "gender": self.gender,
            "age": self.age,
            "occupation": self.occupation,
            "department": self.department,
            "hospital": self.hospital,
            "bio": self.bio,
            "role": self.role,
            "effective_role": self.effective_role,
            "avatar_url": self.avatar_url,
            "date_joined": self.user.date_joined.isoformat() if self.user.date_joined else None,
        }
