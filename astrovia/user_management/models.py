from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone_number = models.CharField(max_length=15, unique=True)
    full_name = models.CharField(max_length=255)
    email = models.EmailField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.full_name


class EmailOTP(models.Model):
    email = models.EmailField(unique=True)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.email} - {self.otp}"


class PhoneOTP(models.Model):
    phone_number = models.CharField(max_length=15, unique=True)
    verification_id = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.phone_number} - {self.verification_id}"