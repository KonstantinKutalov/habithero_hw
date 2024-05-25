import os
import sys
import django
import requests
import json
import logging
from datetime import datetime

import telegram
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ConversationHandler, \
    CallbackQueryHandler
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from asgiref.sync import sync_to_async
from celery import Celery
from django.db.utils import IntegrityError

# Настройка пути к Django проекту
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

# Импорт моделей Django
from habits.models import Habit
from users.models import User

# Настройка Celery
celery = Celery('tasks', broker='redis://localhost:6379/0')

# Инициализация бота
TOKEN = '7012383716:AAET2suh8TMeg3yaNqa6LxTz3tCaGPIWzYA'
bot = Bot(token=TOKEN)

# Логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

API_REGISTER_URL = 'http://127.0.0.1:8000/api/register/'

# Состояния для регистрации
REGISTER_USERNAME, REGISTER_EMAIL, REGISTER_PASSWORD = range(3)

# Состояния для добавления привычки
ADD_HABIT_NAME, ADD_HABIT_PLACE, ADD_HABIT_TIME, ADD_HABIT_ACTION, ADD_HABIT_PLEASANT, ADD_HABIT_LINKED, ADD_HABIT_REWARD, ADD_HABIT_EXECUTION_TIME, ADD_HABIT_FREQUENCY, ADD_HABIT_PUBLIC = range(
    10)

PAGINATION_STATE = range(1)


# Обработчики команд
async def start(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id

    try:
        user = await sync_to_async(User.objects.get)(telegram_chat_id=chat_id)
        await update.message.reply_text(f'Привет! {user.username}, вы уже зарегистрированы.')
    except ObjectDoesNotExist:
        await update.message.reply_text(f'Привет! Зарегистрируйтесь, используя команду /register.')


# Регистрация пользователя через Telegram
async def register_start(update: Update, context: CallbackContext):
    await update.message.reply_text('Введите желаемый username:')
    return REGISTER_USERNAME


async def register_username(update: Update, context: CallbackContext):
    context.user_data['username'] = update.message.text
    await update.message.reply_text('Введите email:')
    return REGISTER_EMAIL


async def register_email(update: Update, context: CallbackContext):
    context.user_data['email'] = update.message.text
    await update.message.reply_text('Введите пароль:')
    return REGISTER_PASSWORD


async def register_password(update: Update, context: CallbackContext):
    """Обрабатывать ввод пароля и регистрацию попыток."""
    password = update.message.text
    context.user_data['password'] = password

    data = {
        'username': context.user_data['username'],
        'email': context.user_data['email'],
        'password': context.user_data['password'],
        'telegram_chat_id': update.message.chat_id
    }

    response = requests.post(API_REGISTER_URL, data=json.dumps(data), headers={'Content-Type': 'application/json'})

    if response.status_code == 201:
        user_id = response.json().get('id')

        if user_id:
            user = await sync_to_async(User.objects.get)(id=user_id)
            user.telegram_chat_id = update.message.chat_id
            await sync_to_async(user.save)()

            await update.message.reply_text(
                'Регистрация прошла успешно! Теперь вы можете использовать бота.')
            return await create_habit(update, context)
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


# Функция для создания новой привычки
async def create_habit(update: Update, context: CallbackContext) -> None:
    context.user_data['new_habit'] = {}
    await update.message.reply_text("Введите название привычки:")
    return ADD_HABIT_NAME


async def habit_name(update: Update, context: CallbackContext) -> int:
    context.user_data['new_habit']['name'] = update.message.text
    await update.message.reply_text("Введите место выполнения привычки:")
    return ADD_HABIT_PLACE


async def habit_place(update: Update, context: CallbackContext) -> int:
    context.user_data['new_habit']['place'] = update.message.text
    await update.message.reply_text("Введите время выполнения привычки (HH:MM):")
    return ADD_HABIT_TIME


async def habit_time(update: Update, context: CallbackContext) -> int:
    context.user_data['new_habit']['time'] = update.message.text
    await update.message.reply_text("Введите действие, которое представляет привычка:")
    return ADD_HABIT_ACTION


async def habit_action(update: Update, context: CallbackContext) -> int:
    context.user_data['new_habit']['action'] = update.message.text
    await update.message.reply_text("Является ли привычка приятной? (да/нет):")
    return ADD_HABIT_PLEASANT


async def habit_is_pleasant(update: Update, context: CallbackContext) -> int:
    context.user_data['new_habit']['is_pleasant'] = update.message.text.lower() == 'да'
    if not context.user_data['new_habit']['is_pleasant']:
        await update.message.reply_text("Введите связанную привычку (или напишите 'пропустить' для пропуска):")
        return ADD_HABIT_LINKED
    await update.message.reply_text("Введите периодичность выполнения привычки (в днях):")
    return ADD_HABIT_FREQUENCY


async def habit_linked(update: Update, context: CallbackContext) -> int:
    linked_habit_name = update.message.text
    if linked_habit_name.lower() != 'пропустить':
        linked_habit = await sync_to_async(Habit.objects.filter(name=linked_habit_name).first)()
        if linked_habit:
            context.user_data['new_habit']['linked_habit'] = linked_habit
    await update.message.reply_text("Введите периодичность выполнения привычки (в днях):")
    return ADD_HABIT_FREQUENCY


async def habit_frequency(update: Update, context: CallbackContext) -> int:
    if update.message.text.lower() != 'пропустить':
        context.user_data['new_habit']['frequency'] = int(update.message.text)
    await update.message.reply_text("Введите вознаграждение за выполнение (или напишите 'пропустить' для пропуска):")
    return ADD_HABIT_REWARD


async def habit_reward(update: Update, context: CallbackContext) -> int:
    reward = update.message.text
    if reward.lower() != 'пропустить':
        context.user_data['new_habit']['reward'] = reward
    await update.message.reply_text("Введите время на выполнение привычки (в минутах):")
    return ADD_HABIT_EXECUTION_TIME


async def habit_execution_time(update: Update, context: CallbackContext) -> int:
    context.user_data['new_habit']['execution_time'] = int(update.message.text)
    await update.message.reply_text("Делать привычку публичной? (да/нет):")
    return ADD_HABIT_PUBLIC


async def habit_is_public(update: Update, context: CallbackContext) -> int:
    context.user_data['new_habit']['is_public'] = update.message.text.lower() == 'да'

    try:
        user = await sync_to_async(User.objects.get)(telegram_chat_id=update.message.chat_id)
        new_habit = Habit(
            user=user,
            name=context.user_data['new_habit'].get('name'),
            place=context.user_data['new_habit'].get('place'),
            time=context.user_data['new_habit'].get('time'),
            action=context.user_data['new_habit'].get('action'),
            is_pleasant=context.user_data['new_habit'].get('is_pleasant'),
            linked_habit=context.user_data['new_habit'].get('linked_habit', None),
            frequency=context.user_data['new_habit'].get('frequency', 1),
            reward=context.user_data['new_habit'].get('reward', ''),
            execution_time=context.user_data['new_habit'].get('execution_time', 0),
            is_public=context.user_data['new_habit'].get('is_public', False)
        )
        await sync_to_async(new_habit.full_clean)()
        await sync_to_async(new_habit.save)()
        await update.message.reply_text("Привычка успешно создана!")
    except User.DoesNotExist:
        await update.message.reply_text("Ошибка: пользователь не найден. Пожалуйста, зарегистрируйтесь сначала.")
    except ValidationError as e:
        await update.message.reply_text(f"Ошибка при создании привычки: {e.messages}")
    except IntegrityError as e:
        await update.message.reply_text(f"Ошибка целостности данных при создании привычки: {e}")
    except Exception as e:
        await update.message.reply_text(f"Неизвестная ошибка: {e}")

    return ConversationHandler.END


# Отмена создания привычки
async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Создание привычки отменено.")
    return ConversationHandler.END


# Список привычек пользователя
async def list_habits(update: Update, context: CallbackContext) -> None:
    user = await sync_to_async(User.objects.get)(telegram_chat_id=update.message.chat_id)
    habits = await sync_to_async(list)(Habit.objects.filter(user=user))
    response = "\n".join([f"{habit.name}: {habit.action} в {habit.place} в {habit.time}" for habit in habits])
    await update.message.reply_text(response if response else "У вас нет привычек.")


# Список публичных привычек
async def list_public_habits(update: Update, context: CallbackContext) -> None:
    habits = await sync_to_async(list)(Habit.objects.filter(is_public=True))
    response = "\n".join(
        [f"{habit.name} ({habit.user.username}): {habit.action} в {habit.place} в {habit.time}" for habit in habits])
    await update.message.reply_text(response if response else "Нет публичных привычек.")


# Удаление привычки
async def delete_habit(update: Update, context: CallbackContext) -> None:
    user = await sync_to_async(User.objects.get)(telegram_chat_id=update.message.chat_id)
    habit_name = " ".join(context.args)
    habit = await sync_to_async(Habit.objects.filter(user=user, name=habit_name).first)()
    if habit:
        await sync_to_async(habit.delete)()
        await update.message.reply_text(f"Привычка '{habit_name}' удалена.")
    else:
        await update.message.reply_text(f"Привычка '{habit_name}' не найдена.")


# Редактирование привычки (пока не реализовано)
async def edit_habit(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("Функция редактирования пока не реализована.")


page_size = 5  # Количество привычек на странице


# Функция для отображения списка привычек с пагинацией
async def list_habits_with_pagination(update: Update, context: CallbackContext) -> int:
    user = await sync_to_async(User.objects.get)(telegram_chat_id=update.message.chat_id)
    habits = await sync_to_async(list)(Habit.objects.filter(user=user))

    #  Пагинация:

    total_pages = len(habits) // page_size + (len(habits) % page_size != 0)

    current_page = 1

    if 'current_page' in context.user_data:
        current_page = context.user_data['current_page']

    #  Отображение списка привычек для текущей страницы
    start_index = (current_page - 1) * page_size
    end_index = min(current_page * page_size, len(habits))
    current_habits = habits[start_index:end_index]

    response = "\n".join(
        [f"{habit.name}: {habit.action} в {habit.place} в {habit.time}" for habit in current_habits])

    if response:
        await update.message.reply_text(
            response + f"\nСтраница {current_page} из {total_pages}"
        )
    else:
        await update.message.reply_text("У вас нет привычек.")

    #  Кнопки для перехода по страницам
    keyboard = [
        [
            #  Кнопка "Предыдущая страница"
            telegram.InlineKeyboardButton(
                "Предыдущая страница", callback_data=f"previous_{current_page}"
            ),
            #  Кнопка "Следующая страница"
            telegram.InlineKeyboardButton(
                "Следующая страница", callback_data=f"next_{current_page}"
            ),
        ],
    ]
    reply_markup = telegram.InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)

    return PAGINATION_STATE


# Функция для обработки нажатия на кнопки пагинации
async def paginate_habits(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    data = query.data
    current_page = int(data.split('_')[1])
    if data.startswith('previous'):
        if current_page > 1:
            current_page -= 1
        else:
            await query.answer(text="Это первая страница")
    elif data.startswith('next'):
        user = await sync_to_async(User.objects.get)(telegram_chat_id=update.message.chat_id)
        habits = await sync_to_async(list)(Habit.objects.filter(user=user))
        total_pages = len(habits) // page_size + (len(habits) % page_size != 0)
        if current_page < total_pages:
            current_page += 1
        else:
            await query.answer(text="Это последняя страница")

    # Сохранение текущей страницы в контексте
    context.user_data['current_page'] = current_page

    # Обновление списка привычек для текущей страницы
    await list_habits_with_pagination(update, context)
    return PAGINATION_STATE


# Основная функция для запуска бота
def main() -> None:
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start), CommandHandler('register', register_start),
                      CommandHandler('create', create_habit)],
        states={
            REGISTER_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_username)],
            REGISTER_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_email)],
            REGISTER_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_password)],

            ADD_HABIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, habit_name)],
            ADD_HABIT_PLACE: [MessageHandler(filters.TEXT & ~filters.COMMAND, habit_place)],
            ADD_HABIT_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, habit_time)],
            ADD_HABIT_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, habit_action)],
            ADD_HABIT_PLEASANT: [MessageHandler(filters.TEXT & ~filters.COMMAND, habit_is_pleasant)],
            ADD_HABIT_LINKED: [MessageHandler(filters.TEXT & ~filters.COMMAND, habit_linked)],
            ADD_HABIT_FREQUENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, habit_frequency)],
            ADD_HABIT_REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, habit_reward)],
            ADD_HABIT_EXECUTION_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, habit_execution_time)],
            ADD_HABIT_PUBLIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, habit_is_public)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)
    #  application.add_handler(CommandHandler("list", list_habits))
    application.add_handler(CommandHandler("public", list_public_habits))
    application.add_handler(CommandHandler("delete", delete_habit))
    application.add_handler(CommandHandler("edit", edit_habit))
    # Обновленный обработчик команды /list
    application.add_handler(CommandHandler("list", list_habits_with_pagination))
    application.add_handler(CallbackQueryHandler(paginate_habits, pattern='^previous|^next'))
    application.run_polling()


if __name__ == '__main__':
    main()
