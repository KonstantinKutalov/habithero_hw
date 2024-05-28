from django.db import models
from users.models import User


class Habit(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    place = models.CharField(max_length=255)
    time = models.TimeField()
    action = models.CharField(max_length=255)
    is_pleasant = models.BooleanField(default=False)
    linked_habit = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL)
    frequency = models.PositiveIntegerField(default=1)
    reward = models.CharField(max_length=255, blank=True, null=True)
    execution_time = models.PositiveIntegerField()
    is_public = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

