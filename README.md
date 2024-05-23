## Habithero: Ваш бот-помощник для формирования полезных привычек

Habithero - это телеграм-бот, который поможет вам формировать новые полезные привычки и отслеживать их выполнение. 

**Функционал:**

* **Регистрация:** Создайте аккаунт в Habithero, чтобы начать отслеживать свои привычки. 
* **Добавление привычки:**
    * Название привычки
    * Место выполнения
    * Время выполнения
    * Действие
    * Является ли привычка приятной
    * Связанная приятная привычка (опционально)
    * Награда (опционально)
    * Время выполнения (в секундах)
    * Частота выполнения (в днях)
    * Публичная ли привычка
* **Список привычек:** Просматривайте список ваших активных привычек. 
* **Удаление привычки:** Удалите привычку из вашего списка.
* **Редактирование привычки:** Измените параметры существующей привычки.

**Как пользоваться:**

1. Найдите бота Habithero24bot в Telegram.
2. Начните диалог с ботом, используя команду `/start`.
3. Если вы ещё не зарегистрированы, воспользуйтесь командой `/register`.
4. После регистрации вы можете пользоваться основными функциями бота: добавление, удаление и редактирование привычек, а также просмотр списка активных привычек.
5. Для добавления привычки /create
6. 
**Как работает интеграция с Telegram:**

* При запуске бота устанавливается соединение с вашим Telegram-аккаунтом.
* При добавлении привычки бот автоматически настраивает расписание напоминаний, которые будут отправляться в ваш чат.
* Вы можете управлять своими привычками и получать уведомления прямо в Telegram.

**Установка и запуск:**

1. **Создайте виртуальное окружение:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
2. **Установите зависимости:**
    ```bash
    pip install -r requirements.txt
    ```
3. **Создайте файл `.env`:**
    ```bash
    cp .env.example .env
    ```
4. **Заполните файл `.env`:**
    * Замените `TELEGRAM_BOT_TOKEN` на ваш токен бота.
    * Заполните данные для подключения к базе данных.
5. **Запустите сервер:**
    ```bash
    python manage.py runserver
    ```
6. **Запустите бота:**
    ```bash
    python telegram_integration/telegram_bot.py
    ```