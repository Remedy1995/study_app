from django.db import models
from django.contrib.auth.models import AbstractUser

from django.db import models
from django.conf import settings


class AudioLecture(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    audio_file = models.FileField(upload_to='lectures/')
    transcript = models.TextField(blank=True, null=True)
    flashcards = models.TextField(blank=True,null=True)
    summary = models.TextField(blank=True, null=True)
    status = models.TextField(blank= True,null=True)
    pdf_file = models.FileField(upload_to='summaries/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    is_student = models.BooleanField(default=True)
    is_admin = models.BooleanField(default=False)

    def __str__(self):
        return self.username

