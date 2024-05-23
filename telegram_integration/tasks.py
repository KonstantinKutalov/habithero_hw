# import celery
# from celery import shared_task
# from telegram import Bot
# import os
#
# TELEGRAM_BOT_TOKEN = "7012383716:AAET2suh8TMeg3yaNqa6LxTz3tCaGPIWzYA"
# bot = Bot(token=TELEGRAM_BOT_TOKEN)
#
#
# @shared_task
# def send_reminder(chat_id, message):  # Переименованная функция
#     bot.send_message(chat_id=chat_id, text=message)
#
#
# @shared_task
# def delete_reminder_task(task_id: str) -> None:
#     """Удаляет задачу Celery по её ID."""
#     celery.conf.beat_schedule.pop(task_id, None)
#     celery.conf.beat_schedule.apply_async()