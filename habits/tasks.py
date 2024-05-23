from celery import shared_task
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Habit
from users.models import User
from telegram import Bot
import os

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
bot = Bot(token=TOKEN)


@shared_task
def send_habit_reminder():
    try:
        now = timezone.now()
        habits = Habit.objects.filter(time=now.strftime("%H:%M"))

        for habit in habits:
            user = habit.user
            message = f"Напоминание: Пора выполнить вашу привычку '{habit.name}' - {habit.action} в {habit.place}."
            if user.telegram_chat_id:
                bot.send_message(chat_id=user.telegram_chat_id, text=message)
    except Exception as e:
        print("An error occurred:", str(e))
        raise
