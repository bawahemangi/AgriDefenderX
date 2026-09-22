from django.contrib.auth.models import User
from django.db import models


class Profile(models.Model):
    class Role(models.TextChoices):
        FARMER = "farmer", "Farmer"
        EXPERT = "expert", "Expert / Lab"
        OFFICER = "officer", "Agriculture Officer"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.FARMER)
    phone = models.CharField(max_length=15, blank=True)
    preferred_language = models.CharField(
        max_length=8,
        choices=[("en", "English"), ("mr", "Marathi"), ("hi", "Hindi")],
        default="en",
    )
    district = models.CharField(max_length=100, blank=True)
    taluka = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"
