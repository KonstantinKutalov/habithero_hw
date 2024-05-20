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
from telegram_integration.tasks import send_reminder

# --- Константы ---

# Состояния для обработчиков диалогов
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

# API endpoint для регистрации
API_REGISTER_URL = 'http://127.0.0.1:8000/api/register/'

# --- Настройка Celery ---

celery = Celery('tasks', broker='redis://localhost:6379/0')

# --- Настройка логгирования ---

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Инициализация бота ---

TOKEN = '7012383716:AAET2suh8TMeg3yaNqa6LxTz3tCaGPIWzYA'
bot = Bot(token=TOKEN)


# --- Вспомогательные функции ---

async def get_or_create_user(update: Update, context: CallbackContext):
    """Получает пользователя из базы данных или создает нового."""
    chat_id = update.effective_chat.id
    try:
        user = await sync_to_async(User.objects.get)(telegram_chat_id=chat_id)
    except ObjectDoesNotExist:
        user = await sync_to_async(User.objects.create)(telegram_chat_id=chat_id)
    return user


async def show_menu(update: Update, context: CallbackContext) -> None:
    """Показывает главное меню с доступными командами."""
    keyboard = [
        [InlineKeyboardButton("Добавить привычку", callback_data='add_habit')],
        [InlineKeyboardButton("Список привычек", callback_data='list_habits')],
        [InlineKeyboardButton("Удалить привычку", callback_data='remove_habit')],
        [InlineKeyboardButton("Редактировать привычку", callback_data='edit_habit')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)


async def handle_menu_selection(update: Update, context: CallbackContext) -> None:
    """Обрабатывает выбор пункта меню и вызывает соответствующие функции."""
    query = update.callback_query
    await query.answer()

    # Получаем пользователя по telegram_chat_id
    telegram_chat_id = query.from_user.id
    print(f"Query: {query}")
    print(f"Query data: {query.data}")
    print(f"User: {query.from_user}")
    print(f"User ID: {query.from_user.id}")
    print(f"Update: {update}")
    user = await sync_to_async(User.objects.get)(telegram_chat_id=telegram_chat_id)

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


async def send_reminder_message(user: User, habit: Habit):
    """Отправляет напоминание пользователю."""
    await sync_to_async(send_reminder.delay)(user.telegram_chat_id,
                                             f"Напоминание о привычке: {habit.action} в {habit.time} в {habit.place}.")


async def delete_reminder_task(habit_id: int):
    """Удаляет задачу Celery для указанной привычки."""
    await sync_to_async(delete_reminder_task.delay)(f'reminder-{habit_id}')


async def create_habit_reminder_task(user: User, habit: Habit):
    """Создает задачу Celery для напоминания пользователю о его привычке."""
    schedule = {
        'task': 'telegram_integration.tasks.send_reminder',
        'schedule': crontab(minute=habit.time.minute, hour=habit.time.hour,
                            day_of_week='*', day_of_month='*', month_of_year='*'),
        'args': (user.telegram_chat_id,
                 f"Напоминание о привычке: {habit.action} в {habit.time} в {habit.place}."),
    }
    await sync_to_async(celery.conf.beat_schedule.update)({f'reminder-{habit.id}': schedule})
    await sync_to_async(celery.conf.beat_schedule.apply_async)()


# --- Обработчики команд ---

async def start(update: Update, context: CallbackContext) -> None:
    """Отправляет сообщение, когда команда /start выполнена."""
    user = await get_or_create_user(update, context)
    if user.username:
        await update.message.reply_text(f'Привет! {user.username}, вы уже зарегистрированы.')
        await show_menu(update, context)
    else:
        await update.message.reply_text(f'Привет! Зарегистрируйтесь, используя команду /register.')


async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запускает диалог регистрации."""
    await update.message.reply_text('Введите желаемый username:')
    return REGISTER_USERNAME


async def register_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ввод имени пользователя."""
    username = update.message.text
    context.user_data['username'] = username
    await update.message.reply_text('Введите email:')
    return REGISTER_EMAIL


async def register_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ввод email."""
    email = update.message.text
    context.user_data['email'] = email
    await update.message.reply_text('Введите пароль:')
    return REGISTER_PASSWORD


async def register_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ввод пароля и пытается зарегистрировать пользователя."""
    password = update.message.text
    context.user_data['password'] = password

    # Отправка запроса на API
    data = {
        'username': context.user_data['username'],
        'email': context.user_data['email'],
        'password': context.user_data['password'],
    }

    response = requests.post(API_REGISTER_URL, data=json.dumps(data), headers={'Content-Type': 'application/json'})

    # Обработка ответа API
    if response.status_code == 201:
        user_id = response.json().get('id')
        if user_id:
            user = await sync_to_async(User.objects.get)(id=user_id)
            # Сохраняем telegram_chat_id
            user.telegram_chat_id = update.message.chat_id
            await sync_to_async(user.save)()
            await update.message.reply_text('Регистрация прошла успешно!')
        else:
            await update.message.reply_text(
                'Ошибка регистрации. Не удалось получить ID пользователя.')


# --- Управление привычками ---

async def add_habit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запускает диалог добавления привычки."""
    user = await get_or_create_user(update, context)
    if not user.username:
        await update.message.reply_text(f'Сначала зарегистрируйтесь, используя команду /register.')
        return ConversationHandler.END
    await update.message.reply_text('Введите название привычки:')
    return ADD_HABIT_NAME


async def add_habit_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ввод названия привычки."""
    name = update.message.text
    context.user_data['name'] = name
    await update.message.reply_text('Введите место, где вы будете выполнять привычку:')
    return ADD_HABIT_PLACE


async def add_habit_place(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ввод места."""
    place = update.message.text
    context.user_data['place'] = place
    await update.message.reply_text('Введите время выполнения привычки (формат HH:MM):')
    return ADD_HABIT_TIME


async def add_habit_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ввод времени."""
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
    """Обрабатывает ввод действия."""
    action = update.message.text
    context.user_data['action'] = action
    await update.message.reply_text('Является ли эта привычка приятной? (да/нет):')
    return ADD_HABIT_PLEASANT


async def add_habit_pleasant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ввод о приятности привычки."""
    is_pleasant = update.message.text.lower() == 'да'
    context.user_data['is_pleasant'] = is_pleasant

    if is_pleasant:
        await update.message.reply_text('Введите название связанной привычки (или введите "нет", если ее нет):')
        return ADD_HABIT_LINKED
    else:
        await update.message.reply_text(
            'Введите вознаграждение за выполнение привычки (или введите "нет", если его нет):')
        return ADD_HABIT_REWARD


async def add_habit_linked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ввод о связанной привычке."""
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
    """Обрабатывает ввод о награде."""
    reward = update.message.text
    if reward.lower() == 'нет':
        context.user_data['reward'] = None
    else:
        context.user_data['reward'] = reward
    await update.message.reply_text('Введите время выполнения привычки в секундах (не более 120):')
    return ADD_HABIT_EXECUTION_TIME


async def add_habit_execution_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ввод времени выполнения."""
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
    """Обрабатывает ввод частоты выполнения."""
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
    """Обрабатывает ввод о публичности привычки."""
    is_public = update.message.text.lower() == 'да'
    context.user_data['is_public'] = is_public

    user = await get_or_create_user(update, context)
    if not user.username:
        await update.message.reply_text(f'Сначала зарегистрируйтесь, используя команду /register.')
        return ConversationHandler.END

    # Сохраняем привычку в базу данных
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
        await create_habit_reminder_task(user, habit)
    except Exception as e:
        await update.message.reply_text(f'Ошибка при добавлении привычки: {e}')

    return ConversationHandler.END


async def remove_habit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запускает диалог удаления привычки."""
    user = await get_or_create_user(update, context)
    if not user.username:
        await update.message.reply_text(f'Сначала зарегистрируйтесь, используя команду /register.')
        return ConversationHandler.END
    await update.message.reply_text('Введите номер привычки, которую хотите удалить:')
    return REMOVE_HABIT_NUMBER


async def remove_habit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ввод номера привычки для удаления."""
    try:
        habit_number = int(update.message.text)
    except ValueError:
        await update.message.reply_text('Некорректный номер привычки. Введите число.')
        return REMOVE_HABIT_NUMBER

    user = await get_or_create_user(update, context)
    if not user.username:
        await update.message.reply_text(f'Сначала зарегистрируйтесь, используя команду /register.')
        return ConversationHandler.END

    habits = await sync_to_async(Habit.objects.filter)(user=user)[:5]

    if habit_number > 0 and habit_number <= len(habits):
        habit_to_delete = habits[habit_number - 1]
        await sync_to_async(habit_to_delete.delete)()
        await update.message.reply_text(f'Привычка "{habit_to_delete.name}" удалена.')
        await delete_reminder_task(habit_to_delete.id)
    else:
        await update.message.reply_text('Неверный номер привычки.')

    return ConversationHandler.END


async def edit_habit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запускает диалог редактирования привычки."""
    user = await get_or_create_user(update, context)
    if not user.username:
        await update.message.reply_text(f'Сначала зарегистрируйтесь, используя команду /register.')
        return ConversationHandler.END
    await update.message.reply_text('Введите номер привычки, которую хотите отредактировать:')
    return EDIT_HABIT_NUMBER


async def edit_habit_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ввод номера привычки для редактирования."""
    try:
        habit_number = int(update.message.text)
    except ValueError:
        await update.message.reply_text('Некорректный номер привычки. Введите число.')
        return EDIT_HABIT_NUMBER

    user = await get_or_create_user(update, context)
    if not user.username:
        await update.message.reply_text(f'Сначала зарегистрируйтесь, используя команду /register.')
        return ConversationHandler.END

    habits = await sync_to_async(Habit.objects.filter)(user=user)[:5]

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
    """Обрабатывает выбор поля для редактирования."""
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
    """Обрабатывает ввод нового значения."""
    new_value = update.message.text
    field_name = context.user_data['field_name']
    habit_id = context.user_data['habit_id']

    user = await get_or_create_user(update, context)
    if not user.username:
        await update.message.reply_text(f'Сначала зарегистрируйтесь, используя команду /register.')
        return ConversationHandler.END

    try:
        habit = await sync_to_async(Habit.objects.get)(id=habit_id)
    except ObjectDoesNotExist:
        await update.message.reply_text('Привычка не найдена.')
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

    await sync_to_async(habit.save)()

    # Обновляем задачу Celery, если нужно
    if field_name in ['time', 'action', 'place']:
        await delete_reminder_task(habit.id)
        await create_habit_reminder_task(user, habit)

    await update.message.reply_text(f'Привычка "{habit.name}" успешно обновлена!')
    return ConversationHandler.END


async def list_habits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выводит список активных привычек пользователя."""
    user = await get_or_create_user(update, context)
    if not user.username:
        await update.message.reply_text(f'Сначала зарегистрируйтесь, используя команду /register.')
        return

    habits = await sync_to_async(Habit.objects.filter)(user=user)[:5]

    if habits:
        habit_list = '\n'.join(f"{i + 1}. {habit.name} - {habit.action}" for i, habit in enumerate(habits))
        await update.message.reply_text(f'Ваши активные привычки:\n{habit_list}')
    else:
        await update.message.reply_text('У вас нет активных привычек.')


# --- Обработчик ошибок ---

async def error_handler(update: object, context: CallbackContext) -> None:
    """Логирует ошибку и отправляет сообщение пользователю."""
    logger.error(f'Exception while handling update {update} caused by {context.error}')
    if update.effective_chat:
        try:
            await update.effective_chat.send_message(f'Произошла ошибка. Попробуйте позже.')
        except TelegramError:
            pass


# --- Основная функция ---

def main() -> None:
    """Запускает бота."""
    application = Application.builder().token(TOKEN).build()

    # --- Обработчик меню ---
    application.add_handler(CallbackQueryHandler(handle_menu_selection))

    # --- Обработчики команд ---
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('register', register_start))
    application.add_handler(CommandHandler('add_habit', add_habit_start))
    application.add_handler(CommandHandler('list_habits', list_habits))
    application.add_handler(CommandHandler('remove_habit', remove_habit_start))
    application.add_handler(CommandHandler('edit_habit', edit_habit_start))

    # --- Обработчик ошибок ---
    application.add_error_handler(error_handler)

    # --- Conversation handler for registration ---
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

    # --- Conversation handler for adding habit ---
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

    # --- Conversation handler for removing habit ---
    remove_habit_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('remove_habit', remove_habit_start)],
        states={
            REMOVE_HABIT_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_habit)],
        },
        fallbacks=[],
    )
    application.add_handler(remove_habit_conv_handler)

    # --- Conversation handler for editing habit ---
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

    # --- Запуск бота ---
    application.run_polling()


if __name__ == '__main__':
    main()
