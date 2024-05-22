import os
import sys
import django
import requests
import json
from datetime import datetime
from django.core.exceptions import ObjectDoesNotExist
from telegram.error import TelegramError

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ContextTypes, \
    ConversationHandler, CallbackQueryHandler
from django.apps import apps
from celery import Celery
import logging
from asgiref.sync import sync_to_async

from django.contrib.auth import get_user_model

User = get_user_model()
from habits.models import Habit
from celery.schedules import crontab
from telegram_integration.tasks import delete_reminder_task
from users.models import User

REGISTER_USERNAME = 0
REGISTER_EMAIL = 1
REGISTER_PASSWORD = 2

ADD_HABIT_NAME = 0
ADD_HABIT_PLACE = 1
ADD_HABIT_TIME = 2
ADD_HABIT_ACTION = 3
ADD_HABIT_PLEASANT = 4
ADD_HABIT_LINKED = 5
ADD_HABIT_REWARD = 6
ADD_HABIT_EXECUTION_TIME = 7
ADD_HABIT_FREQUENCY = 8
ADD_HABIT_PUBLIC = 9

REMOVE_HABIT_NUMBER = 0

EDIT_HABIT_NUMBER = 0
EDIT_HABIT_FIELD = 1
EDIT_HABIT_NEW_VALUE = 2

# Настройка Celery
celery = Celery('tasks', broker='redis://localhost:6379/0')

# Логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
TOKEN = '7012383716:AAET2suh8TMeg3yaNqa6LxTz3tCaGPIWzYA'
bot = Bot(token=TOKEN)

# API endpoint для регистрации
API_REGISTER_URL = 'http://127.0.0.1:8000/api/register/'


# --- Обработчики команд ---

async def start(update: Update, context: CallbackContext) -> None:
    """Отправьте сообщение, когда будет выпущена команда /старт."""
    user_id = update.effective_user.id
    chat_id = update.message.chat_id

    try:
        # получить пользователя по ID чата
        user = await sync_to_async(User.objects.get)(telegram_chat_id=chat_id)
        await update.message.reply_text(f'Привет! {user.username}, вы уже зарегистрированы.')
        await show_menu(update, context)
    except ObjectDoesNotExist:
        # Если пользователя не существует, запишите ID чата в базу данных
        await update.message.reply_text(f'Привет! Зарегистрируйтесь, используя команду /register.')


# --- Функция для отправки напоминаний ---

@celery.task
def send_reminder(chat_id: int, message: str) -> None:
    """Отправьте сообщение напоминания на указанный идентификатор чата."""
    bot.send_message(chat_id=chat_id, text=message)


@celery.task
def delete_reminder_task(task_id: str) -> None:
    """Удаляет задачу Celery по её ID."""
    celery.conf.beat_schedule.pop(task_id, None)
    celery.conf.beat_schedule.apply_async()


# --- Функция для обработки сообщений ---

async def echo(update: Update, context: CallbackContext) -> None:
    """Повторите сообщение пользователя."""
    await update.message.reply_text(update.message.text)


# --- Регистрация пользователя через Telegram ---

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начните регистрационный разговор."""
    await update.message.reply_text('Введите желаемый username:')
    return REGISTER_USERNAME


async def register_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывать ввод имени пользователя."""
    username = update.message.text
    context.user_data['username'] = username
    await update.message.reply_text('Введите email:')
    return REGISTER_EMAIL


async def register_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывать ввод электронной почты."""
    email = update.message.text
    context.user_data['email'] = email
    await update.message.reply_text('Введите пароль:')
    return REGISTER_PASSWORD


async def register_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывать ввод пароля и регистрацию попыток."""
    password = update.message.text
    context.user_data['password'] = password

    # --- Отправка запроса на API ---

    data = {
        'username': context.user_data['username'],
        'email': context.user_data['email'],
        'password': context.user_data['password'],
        'telegram_chat_id': update.message.chat_id
    }

    response = requests.post(API_REGISTER_URL, data=json.dumps(data), headers={'Content-Type': 'application/json'})
    # --- Обработка ответа API ---

    if response.status_code == 201:
        # Получите ID пользователя из ответа API
        user_id = response.json().get('id')

        if user_id:
            # Сохраните telegram_chat_id только после успешной регистрации
            user = await sync_to_async(User.objects.get)(id=user_id)
            user.telegram_chat_id = update.message.chat_id
            await sync_to_async(user.save)()

            await update.message.reply_text(
                'Регистрация прошла успешно! Теперь вы можете использовать бота.')
            await show_menu(update, context)
        else:
            await update.message.reply_text(
                'Ошибка регистрации. Не удалось получить ID пользователя.')
    elif response.status_code == 400 and 'username' in response.json():
        await update.message.reply_text('Такое имя пользователя уже существует. Пожалуйста, выберите другое.')
        return await register_start(update, context)
    elif response.status_code == 400 and 'email' in response.json():
        await update.message.reply_text('Такой адрес электронной почты уже используется. Пожалуйста, введите другой.')
        return await register_start(update, context)
    else:
        error_message = f"Ошибка регистрации: {response.text}"
        await update.message.reply_text(error_message[:4000])

    return ConversationHandler.END


# --- Добавление привычки ---

async def add_habit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинаем диалог добавления привычки"""
    if update.callback_query:
        await update.callback_query.message.reply_text('Введите название привычки:')
        return ADD_HABIT_NAME
    elif update.message:
        await update.message.reply_text('Введите название привычки:')
        return ADD_HABIT_NAME
    else:
        logger.error('Ошибка: Отсутствует сообщение от пользователя.')


async def add_habit_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатываем ввод названия привычки"""
    name = update.message.text
    context.user_data['name'] = name
    await update.message.reply_text('Введите место, где вы будете выполнять привычку:')
    return ADD_HABIT_PLACE


async def add_habit_place(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатываем ввод места"""
    place = update.message.text
    context.user_data['place'] = place
    await update.message.reply_text('Введите время выполнения привычки (формат HH:MM):')
    return ADD_HABIT_TIME


async def add_habit_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатываем ввод времени"""
    time_str = update.message.text
    try:
        time = datetime.strptime(time_str, '%H:%M').time()
    except ValueError:
        await update.message.reply_text('Некорректный формат времени. Используйте HH:MM.')
        return ADD_HABIT_TIME
    context.user_data['time'] = time
    await update.message.reply_text('Введите действие, которое представляет собой привычку:')
    return ADD_HABIT_ACTION


async def add_habit_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатываем ввод действия"""
    action = update.message.text
    context.user_data['action'] = action
    await update.message.reply_text('Является ли эта привычка приятной? (да/нет):')
    return ADD_HABIT_PLEASANT


async def add_habit_pleasant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатываем ввод о приятности привычки"""
    is_pleasant = update.message.text.lower() == 'да'
    context.user_data['is_pleasant'] = is_pleasant

    if is_pleasant:
        # Если приятная, то спрашиваем о связанной привычке
        await update.message.reply_text('Введите название связанной привычки (или введите "нет", если ее нет):')
        return ADD_HABIT_LINKED
    else:
        # Если не приятная, то спрашиваем о награде
        await update.message.reply_text(
            'Введите вознаграждение за выполнение привычки (или введите "нет", если его нет):')
        return ADD_HABIT_REWARD


async def add_habit_linked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатываем ввод о связанной привычке"""
    linked_habit_name = update.message.text
    if linked_habit_name.lower() == 'нет':
        context.user_data['linked_habit'] = None
        await update.message.reply_text('Введите время выполнения привычки в секундах (не более 120):')
        return ADD_HABIT_EXECUTION_TIME
    else:
        context.user_data['linked_habit_name'] = linked_habit_name
        await update.message.reply_text('Введите время выполнения привычки в секундах (не более 120):')
        return ADD_HABIT_EXECUTION_TIME


async def add_habit_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатываем ввод о награде"""
    reward = update.message.text
    if reward.lower() == 'нет':
        context.user_data['reward'] = None
    else:
        context.user_data['reward'] = reward
    await update.message.reply_text('Введите время выполнения привычки в секундах (не более 120):')
    return ADD_HABIT_EXECUTION_TIME


async def add_habit_execution_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатываем ввод времени выполнения"""
    try:
        execution_time = int(update.message.text)
        if execution_time > 120:
            raise ValueError
    except ValueError:
        await update.message.reply_text('Некорректное время выполнения. Введите число не более 120.')
        return ADD_HABIT_EXECUTION_TIME
    context.user_data['execution_time'] = execution_time
    await update.message.reply_text('Введите частоту выполнения привычки в днях (от 1 до 7):')
    return ADD_HABIT_FREQUENCY


async def add_habit_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатываем ввод частоты выполнения"""
    try:
        frequency = int(update.message.text)
        if frequency < 1 or frequency > 7:
            raise ValueError
    except ValueError:
        await update.message.reply_text('Некорректная частота выполнения. Введите число от 1 до 7.')
        return ADD_HABIT_FREQUENCY
    context.user_data['frequency'] = frequency
    await update.message.reply_text('Сделать привычку публичной? (да/нет):')
    return ADD_HABIT_PUBLIC


async def add_habit_public(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатываем ввод о публичности привычки"""
    is_public = update.message.text.lower() == 'да'
    context.user_data['is_public'] = is_public

    # Сохраняем привычку в базу данных
    user_id = update.effective_user.id
    try:
        user = await sync_to_async(User.objects.get)(id=user_id)
    except ObjectDoesNotExist:
        await update.message.reply_text('Пользователь не найден. Зарегистрируйтесь в приложении.')
        return ConversationHandler.END

    data = {
        'user': user.id,
        'name': context.user_data['name'],
        'place': context.user_data['place'],
        'time': context.user_data['time'],
        'action': context.user_data['action'],
        'is_pleasant': context.user_data['is_pleasant'],
        'execution_time': context.user_data['execution_time'],
        'frequency': context.user_data['frequency'],
        'is_public': context.user_data['is_public'],
    }

    if 'linked_habit_name' in context.user_data:
        linked_habit = await sync_to_async(
            Habit.objects.filter(user=user, name=context.user_data['linked_habit_name']).first)()
        if linked_habit:
            data['linked_habit'] = linked_habit.id
        else:
            await update.message.reply_text('Связанная привычка не найдена. Проверьте ее название.')
            return ConversationHandler.END

    if 'reward' in context.user_data:
        data['reward'] = context.user_data['reward']

    try:
        habit = await sync_to_async(Habit.objects.create)(**data)
        await update.message.reply_text(f'Привычка "{habit.name}" успешно добавлена!')
    except Exception as e:
        await update.message.reply_text(f'Ошибка при добавлении привычки: {e}')

    # Настройка рассылки через Celery
    schedule = {
        'task': 'telegram_integration.tasks.send_reminder',
        'schedule': crontab(minute=context.user_data['time'].minute, hour=context.user_data['time'].hour,
                            day_of_week='*', day_of_month='*', month_of_year='*'),
        'args': (
            user.telegram_chat_id, f"Reminder to perform your habit: {habit.action} at {habit.time} in {habit.place}."),
    }
    celery.conf.beat_schedule.update({f'reminder-{habit.id}': schedule})
    celery.conf.beat_schedule.apply_async()

    return ConversationHandler.END


# --- Удаление привычки ---

async def remove_habit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинаем диалог удаления привычки."""
    await update.message.reply_text('Введите номер привычки, которую хотите удалить:')
    return REMOVE_HABIT_NUMBER


async def remove_habit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатываем ввод номера привычки для удаления."""
    try:
        habit_number = int(update.message.text)
    except ValueError:
        await update.message.reply_text('Некорректный номер привычки. Введите число.')
        return REMOVE_HABIT_NUMBER

    user_id = update.effective_user.id
    try:
        user = await sync_to_async(User.objects.get)(id=user_id)
    except ObjectDoesNotExist:
        await update.message.reply_text('Пользователь не найден. Зарегистрируйтесь в приложении.')
        return ConversationHandler.END

    habits = await sync_to_async(Habit.objects.filter)(user=user)[:5]  # Получаем 5 активных привычек

    if habit_number > 0 and habit_number <= len(habits):
        habit_to_delete = habits[habit_number - 1]
        await sync_to_async(habit_to_delete.delete)()
        await update.message.reply_text(f'Привычка "{habit_to_delete.name}" удалена.')
        # Удаляем задачу Celery, связанную с этой привычкой
        delete_reminder_task.delay(f'reminder-{habit_to_delete.id}')
    else:
        await update.message.reply_text('Неверный номер привычки.')

    return ConversationHandler.END


# --- Редактирование привычки ---

async def edit_habit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинаем диалог редактирования привычки."""
    await update.message.reply_text('Введите номер привычки, которую хотите отредактировать:')
    return EDIT_HABIT_NUMBER


async def edit_habit_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатываем ввод номера привычки для редактирования."""
    try:
        habit_number = int(update.message.text)
    except ValueError:
        await update.message.reply_text('Некорректный номер привычки. Введите число.')
        return EDIT_HABIT_NUMBER

    user_id = update.effective_user.id
    try:
        user = await sync_to_async(User.objects.get)(id=user_id)
    except ObjectDoesNotExist:
        await update.message.reply_text('Пользователь не найден. Зарегистрируйтесь в приложении.')
        return ConversationHandler.END

    habits = await sync_to_async(Habit.objects.filter)(user=user)[:5]  # Получаем 5 активных привычек

    if habit_number > 0 and habit_number <= len(habits):
        habit_to_edit = habits[habit_number - 1]
        keyboard = [
            [InlineKeyboardButton("Название", callback_data=f'edit_name_{habit_to_edit.id}')],
            [InlineKeyboardButton("Место", callback_data=f'edit_place_{habit_to_edit.id}')],
            [InlineKeyboardButton("Время", callback_data=f'edit_time_{habit_to_edit.id}')],
            [InlineKeyboardButton("Действие", callback_data=f'edit_action_{habit_to_edit.id}')],
            [InlineKeyboardButton("Приятная?", callback_data=f'edit_pleasant_{habit_to_edit.id}')],
            [InlineKeyboardButton("Связанная привычка", callback_data=f'edit_linked_{habit_to_edit.id}')],
            [InlineKeyboardButton("Награда", callback_data=f'edit_reward_{habit_to_edit.id}')],
            [InlineKeyboardButton("Время выполнения", callback_data=f'edit_execution_time_{habit_to_edit.id}')],
            [InlineKeyboardButton("Частота", callback_data=f'edit_frequency_{habit_to_edit.id}')],
            [InlineKeyboardButton("Публичная?", callback_data=f'edit_public_{habit_to_edit.id}')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f'Выберите поле, которое хотите отредактировать:', reply_markup=reply_markup)
        context.user_data['habit_to_edit'] = habit_to_edit
        return EDIT_HABIT_FIELD
    else:
        await update.message.reply_text('Неверный номер привычки.')

    return ConversationHandler.END


async def edit_habit_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатываем выбор поля для редактирования."""
    query = update.callback_query
    await query.answer()
    field_data = query.data.split('_')
    field_name = field_data[1]
    habit_id = int(field_data[2])

    context.user_data['field_name'] = field_name
    context.user_data['habit_id'] = habit_id

    if field_name == 'pleasant':
        await update.message.reply_text('Введите "да", если привычка приятная, или "нет", если нет:')
        return EDIT_HABIT_NEW_VALUE
    else:
        await update.message.reply_text(f'Введите новое значение для поля "{field_name}":')
        return EDIT_HABIT_NEW_VALUE


async def edit_habit_new_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатываем ввод нового значения."""
    new_value = update.message.text
    field_name = context.user_data['field_name']
    habit_id = context.user_data['habit_id']
    user_id = update.effective_user.id

    try:
        user = await sync_to_async(User.objects.get)(id=user_id)
        habit = await sync_to_async(Habit.objects.get)(id=habit_id)
    except ObjectDoesNotExist:
        await update.message.reply_text('Пользователь или привычка не найдены.')
        return ConversationHandler.END

    if field_name == 'name':
        habit.name = new_value
    elif field_name == 'place':
        habit.place = new_value
    elif field_name == 'time':
        try:
            habit.time = datetime.strptime(new_value, '%H:%M').time()
        except ValueError:
            await update.message.reply_text('Некорректный формат времени. Используйте HH:MM.')
            return EDIT_HABIT_NEW_VALUE
    elif field_name == 'action':
        habit.action = new_value
    elif field_name == 'pleasant':
        habit.is_pleasant = new_value.lower() == 'да'
    elif field_name == 'linked':
        if new_value.lower() == 'нет':
            habit.linked_habit = None
        else:
            linked_habit = await sync_to_async(Habit.objects.filter(user=user, name=new_value).first)()
            if linked_habit:
                habit.linked_habit = linked_habit
            else:
                await update.message.reply_text('Связанная привычка не найдена. Проверьте ее название.')
                return EDIT_HABIT_NEW_VALUE
    elif field_name == 'reward':
        if new_value.lower() == 'нет':
            habit.reward = None
        else:
            habit.reward = new_value
    elif field_name == 'execution_time':
        try:
            habit.execution_time = int(new_value)
            if habit.execution_time > 120:
                raise ValueError
        except ValueError:
            await update.message.reply_text('Некорректное время выполнения. Введите число не более 120.')
            return EDIT_HABIT_NEW_VALUE
    elif field_name == 'frequency':
        try:
            habit.frequency = int(new_value)
            if habit.frequency < 1 or habit.frequency > 7:
                raise ValueError
        except ValueError:
            await update.message.reply_text('Некорректная частота выполнения. Введите число от 1 до 7.')
            return EDIT_HABIT_NEW_VALUE
    elif field_name == 'public':
        habit.is_public = new_value.lower() == 'да'

    await habit.save()

    # Обновляем расписание Celery, если нужно
    if field_name in ['time', 'action', 'place']:
        delete_reminder_task.delay(f'reminder-{habit.id}')
        schedule = {
            'task': 'telegram_integration.tasks.send_reminder',
            'schedule': crontab(minute=habit.time.minute, hour=habit.time.hour, day_of_week='*', day_of_month='*',
                                month_of_year='*'),
            'args': (
                user.telegram_chat_id,
                f"Напоминание о том, чтобы выполнить свою привычку: {habit.action} с {habit.time} по {habit.place}."),
        }

        celery.conf.beat_schedule.update({f'reminder-{habit.id}': schedule})
        celery.conf.beat_schedule.apply_async()

    await update.message.reply_text(f'Привычка "{habit.name}" успешно обновлена!')
    return ConversationHandler.END


async def list_habits(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выводит список активных привычек пользователя."""
    user_id = update.effective_user.id
    try:
        user = await sync_to_async(User.objects.get)(id=user_id)
    except ObjectDoesNotExist:
        if update.callback_query and update.callback_query.message:
            await update.callback_query.message.reply_text('Пользователь не найден. Зарегистрируйтесь в приложении.')
        elif update.message:
            await update.message.reply_text('Пользователь не найден. Зарегистрируйтесь в приложении.')
        return

    habits = await sync_to_async(Habit.objects.filter)(user=user)[:5]  # Выводит максимум 5 привычек

    if habits:
        habit_list = '\n'.join(f"{i + 1}. {habit.name} - {habit.action}" for i, habit in enumerate(habits))

        if update.callback_query and update.callback_query.message:
            await update.callback_query.message.reply_text(f'Ваши активные привычки:\n{habit_list}')
        elif update.message:
            await update.message.reply_text(f'Ваши активные привычки:\n{habit_list}')
    else:
        if update.callback_query and update.callback_query.message:
            await update.callback_query.message.reply_text('У вас нет активных привычек.')
        elif update.message:
            await update.message.reply_text('У вас нет активных привычек.')


async def show_menu(update: Update, context: CallbackContext) -> None:
    """Показать главное меню с доступными командами."""
    keyboard = [
        [InlineKeyboardButton("Добавить привычку", callback_data='add_habit')],
        [InlineKeyboardButton("Список привычек", callback_data='list_habits')],
        [InlineKeyboardButton("Удалить привычку", callback_data='remove_habit')],
        [InlineKeyboardButton("Редактировать привычку", callback_data='edit_habit')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)


async def handle_menu_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка выбора меню и вызова соответствующих функций."""
    query = update.callback_query
    await query.answer()
    selected_action = query.data

    if selected_action == 'add_habit':
        await add_habit_start(update, context)
    elif selected_action == 'list_habits':
        await list_habits(update, context)
    elif selected_action == 'remove_habit':
        await remove_habit_start(update, context)
    elif selected_action == 'edit_habit':
        await edit_habit_start(update, context)

    # После выполнения действия снова отображаем меню
    await show_menu(update, context)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Вход в систему ошибки и отправка сообщение пользователю."""
    logger.error(f'Exception while handling update {update} caused by {context.error}')

    # Вывод сообщения пользователю
    if update.effective_chat:
        try:
            await update.effective_chat.send_message('Произошла ошибка. Попробуйте позже.')
        except TelegramError:
            pass  # Не удается отправить сообщение пользователю, игнорируем


# --- Основная функция ---

def main() -> None:
    """Запустить бота"""
    application = Application.builder().token(TOKEN).build()

    # --- Обработчик меню ---
    application.add_handler(CallbackQueryHandler(handle_menu_selection))

    # --- Обработчики команд ---
    application.add_handler(CommandHandler('start', start))
    # application.add_handler(CommandHandler('register_chat_id', register_chat_id))
    application.add_handler(CommandHandler('add_habit', add_habit_start))
    application.add_handler(CommandHandler('list_habits', list_habits))
    application.add_handler(CommandHandler('remove_habit', remove_habit_start))
    application.add_handler(CommandHandler('edit_habit', edit_habit_start))

    # --- Обработчик ошибок ---
    application.add_error_handler(error_handler)

    # --- Обработчик разговора для регистрации ---
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('register', register_start)],
        states={
            REGISTER_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_username)],
            REGISTER_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_email)],
            REGISTER_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_password)],
        },
        fallbacks=[],
    )
    application.add_handler(conv_handler)

    # --- Обработчик разговора за добавление привычки ---
    add_habit_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('add_habit', add_habit_start)],
        states={
            ADD_HABIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_habit_name)],
            ADD_HABIT_PLACE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_habit_place)],
            ADD_HABIT_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_habit_time)],
            ADD_HABIT_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_habit_action)],
            ADD_HABIT_PLEASANT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_habit_pleasant)],
            ADD_HABIT_LINKED: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_habit_linked)],
            ADD_HABIT_REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_habit_reward)],
            ADD_HABIT_EXECUTION_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_habit_execution_time)],
            ADD_HABIT_FREQUENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_habit_frequency)],
            ADD_HABIT_PUBLIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_habit_public)],
        },
        fallbacks=[],
    )
    application.add_handler(add_habit_conv_handler)

    # --- Обработчик разговора для удаления привычки ---
    remove_habit_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('remove_habit', remove_habit_start)],
        states={
            REMOVE_HABIT_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_habit)],
        },
        fallbacks=[],
    )
    application.add_handler(remove_habit_conv_handler)

    # --- Обработчик разговора для редактирования привычки ---
    edit_habit_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('edit_habit', edit_habit_start)],
        states={
            EDIT_HABIT_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_habit_number)],
            EDIT_HABIT_FIELD: [CallbackQueryHandler(edit_habit_field)],
            EDIT_HABIT_NEW_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_habit_new_value)],
        },
        fallbacks=[],
    )
    application.add_handler(edit_habit_conv_handler)

    # --- Обработчик для эхо-сообщений ---
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # --- Запуск бота ---
    application.run_polling()


if __name__ == '__main__':
    main()
