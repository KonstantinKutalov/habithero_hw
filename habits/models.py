from django.db import models
# from telegram_integration.tasks import send_reminder
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.conf import settings
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

    def clean(self):
        if self.reward and self.linked_habit:
            raise ValidationError(_("Вы не можете установить и награду, и связанный привычку."))
        if self.execution_time > 120:
            raise ValidationError(_("Время выполнения не может превышать 120 секунд."))
        if self.frequency > 7:
            raise ValidationError(_("Вы не можете выполнять привычку реже, чем раз в 7 дней."))
        if self.linked_habit and not self.linked_habit.is_pleasant:
            raise ValidationError(_("Связанная привычка должна быть приятной."))
        if self.is_pleasant and (self.reward or self.linked_habit):
            raise ValidationError(_("Приятные привычки не могут иметь награды или связанных привычек."))

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    # def send_reminder(self):
    #     message = f"Напоминание о выполнении своей привычки: {self.action} at {self.time} in {self.place}."
    #     send_reminder.delay(self.user.telegram_chat_id, message)
