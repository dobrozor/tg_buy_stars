import base64
import os
import json
import logging
import sqlite3
import uuid
from datetime import datetime
from dotenv import load_dotenv
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

STAR_PRICE = 1.5  # 1.5 рубля за звезду
MAIN_MENU_IMAGE = "https://sociogramm.ru/assets/uploads/blogs/blog/kak-poluchit-zvezdy-v-telegram-1.jpeg"  # URL изображения для главного меню
WELCOME_MES = f"Привет👋\n\nДобро пожаловать в бота для покупки Telegram Stars! 🌟\n\nВыберите действие:"

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN')
YOOKASSA_SHOP_ID = os.getenv('YOOKASSA_SHOP_ID')
YOOKASSA_SECRET_KEY = os.getenv('YOOKASSA_SECRET_KEY')
ADMIN_ID = os.getenv('ADMIN_ID')

# Fragment API настройки
FRAGMENT_API_URL = "https://api.fragment-api.com/v1"
FRAGMENT_API_KEY = os.getenv("FRAGMENT_API_KEY")
FRAGMENT_PHONE = os.getenv("FRAGMENT_PHONE")
FRAGMENT_MNEMONICS = os.getenv("FRAGMENT_MNEMONICS")
TOKEN_FILE = "auth_token.json"
MIN_STARS = 50

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Таблица транзакций
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        type TEXT,
        status TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')

    # Таблица платежей
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        yookassa_id TEXT,
        status TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')

    conn.commit()
    conn.close()

# Функции для работы с базой данных
def get_user(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()

    if user:
        return {
            'user_id': user[0],
            'username': user[1],
            'balance': user[2],
            'created_at': user[3]
        }
    return None

def create_user(user_id, username):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)',
        (user_id, username)
    )
    conn.commit()
    conn.close()

def update_balance(user_id, amount):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE users SET balance = balance + ? WHERE user_id = ?',
        (amount, user_id)
    )
    conn.commit()
    conn.close()

def add_transaction(user_id, amount, transaction_type, status='completed'):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO transactions (user_id, amount, type, status) VALUES (?, ?, ?, ?)',
        (user_id, amount, transaction_type, status)
    )
    conn.commit()
    conn.close()

# Fragment API функции
def load_fragment_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            return json.load(f).get("token")
    return None

def save_fragment_token(token):
    with open(TOKEN_FILE, "w") as f:
        json.dump({"token": token}, f)

def authenticate_fragment():
    try:
        mnemonics_list = FRAGMENT_MNEMONICS.strip().split()
        payload = {
            "api_key": FRAGMENT_API_KEY,
            "phone_number": FRAGMENT_PHONE,
            "mnemonics": mnemonics_list,
            "version": "V4R2"
        }
        res = requests.post(f"{FRAGMENT_API_URL}/auth/authenticate/", json=payload)
        if res.status_code == 200:
            token = res.json().get("token")
            save_fragment_token(token)
            logger.info("✅ Успешная авторизация Fragment.")
            return token
        logger.error(f"❌ Ошибка авторизации Fragment: {res.text}")
        return None
    except Exception as e:
        logger.error(f"❌ Исключение при авторизации Fragment: {e}")
        return None

def get_fragment_balance(token):
    url = f"{FRAGMENT_API_URL}/misc/wallet/"
    headers = {
        "Accept": "application/json",
        "Authorization": f"JWT {token}"
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data.get("balance", 0)
        else:
            logger.error(f"❌ Ошибка получения баланса: {response.text}")
            return 0
    except Exception as e:
        logger.error(f"❌ Исключение при получении баланса: {e}")
        return 0

def send_stars(token, username, quantity):
    try:
        if not username.startswith('@'):
            username = f"{username}"

        data = {
            "username": username,
            "quantity": quantity,
            "show_sender": "false"
        }
        headers = {
            "Authorization": f"JWT {token}",
            "Content-Type": "application/json"
        }

        logger.info(f"🔄 Отправка {quantity} ⭐ пользователю {username}...")
        res = requests.post(f"{FRAGMENT_API_URL}/order/stars/", json=data, headers=headers)

        if res.status_code == 200:
            logger.info("✅ Звезды успешно отправлены!")
            return True, "Успешно"
        else:
            error_msg = f"❌ Ошибка отправки: {res.text}"
            logger.error(error_msg)
            return False, res.text

    except Exception as e:
        error_msg = f"❌ Исключение при отправке: {e}"
        logger.error(error_msg)
        return False, str(e)

# ЮKassa функции
def create_yookassa_payment(amount, user_id):
    url = "https://api.yookassa.ru/v3/payments"

    # Генерация корректных авторизационных данных
    auth_string = f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}".encode('utf-8')
    encoded_auth = base64.b64encode(auth_string).decode('utf-8')

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {encoded_auth}",
        "Idempotence-Key": str(uuid.uuid4())  # Уникальный ключ идемпотентности
    }

    payload = {
        "amount": {
            "value": f"{amount:.2f}",
            "currency": "RUB"
        },
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": f"https://t.me/{bot.get_me().username}"  # Используем реальный username бота
        },
        "description": f"Пополнение баланса (user_id: {user_id})",
        "metadata": {
            "user_id": user_id  # Добавляем user_id в метаданные
        }
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        payment_data = response.json()

        # Сохраняем информацию о платеже в базу
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO payments (user_id, amount, yookassa_id, status) VALUES (?, ?, ?, ?)',
            (user_id, amount, payment_data['id'], 'pending')
        )
        conn.commit()
        conn.close()

        return payment_data['confirmation']['confirmation_url']
    except Exception as e:
        logger.error(f"Ошибка создания платежа ЮKassa: {str(e)}")
        return None

def check_payment_status(payment_id):
    url = f"https://api.yookassa.ru/v3/payments/{payment_id}"

    auth_string = f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}".encode('utf-8')
    encoded_auth = base64.b64encode(auth_string).decode('utf-8')

    headers = {
        "Authorization": f"Basic {encoded_auth}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Ошибка проверки платежа: {str(e)}")
        return None

# Добавим новый обработчик для проверки платежа
@bot.callback_query_handler(func=lambda call: call.data == 'check_payment')
def handle_check_payment(call: CallbackQuery):
    user_id = call.from_user.id
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    try:
        # Получаем последний платеж пользователя
        cursor.execute(
            'SELECT yookassa_id, amount FROM payments '
            'WHERE user_id = ? AND status = "pending" '
            'ORDER BY created_at DESC LIMIT 1',
            (user_id,)
        )
        payment = cursor.fetchone()

        if not payment:
            bot.answer_callback_query(call.id, "❌ Платеж не найден", show_alert=True)
            return

        payment_id, amount = payment
        payment_info = check_payment_status(payment_id)

        if not payment_info:
            bot.answer_callback_query(call.id, "❌ Ошибка проверки платежа", show_alert=True)
            return

        if payment_info['status'] == 'succeeded':
            # Обновляем статус платежа
            cursor.execute(
                'UPDATE payments SET status = "succeeded" WHERE yookassa_id = ?',
                (payment_id,)
            )

            # Обновляем баланс пользователя
            cursor.execute(
                'UPDATE users SET balance = balance + ? WHERE user_id = ?',
                (amount, user_id)
            )

            # Добавляем транзакцию
            cursor.execute(
                'INSERT INTO transactions (user_id, amount, type, status) '
                'VALUES (?, ?, ?, ?)',
                (user_id, amount, 'deposit', 'completed')
            )

            conn.commit()

            # Получаем обновленные данные пользователя
            user_data = get_user(user_id)

            # Обновляем caption и клавиатуру
            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=f"✅ Платеж успешно завершен!\n"
                       f"💳 Сумма: {amount} руб\n"
                       f"💰 Новый баланс: {user_data['balance']} руб",
                reply_markup=back_to_main_keyboard()
            )

        elif payment_info['status'] == 'pending':
            bot.answer_callback_query(
                call.id,
                "⌛ Платеж еще не прошел. Попробуйте проверить позже.",
                show_alert=True
            )
        else:
            bot.answer_callback_query(
                call.id,
                f"❌ Платеж не прошел. Статус: {payment_info['status']}",
                show_alert=True
            )

    except Exception as e:
        logger.error(f"Ошибка обработки платежа: {str(e)}")
        bot.answer_callback_query(call.id, "❌ Произошла ошибка при обработке платежа", show_alert=True)
    finally:
        conn.close()

# Функции для создания клавиатур
def main_menu_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton("⭐ Купить звезды", callback_data='buy_stars'),
        InlineKeyboardButton("💰 Пополнить баланс", callback_data='deposit')
    )
    keyboard.row(InlineKeyboardButton("👤 Профиль", callback_data='profile'))
    return keyboard

def buy_stars_keyboard(user_data):
    keyboard = InlineKeyboardMarkup()

    # Расчет цен по формуле STAR_PRICE * количество_звезд
    options = [
        (50, f"50 звезд - {STAR_PRICE * 50:.1f} руб"),
        (100, f"100 звезд - {STAR_PRICE * 100:.1f} руб"),
        (500, f"500 звезд - {STAR_PRICE * 500:.1f} руб"),
        (1000, f"1000 звезд - {STAR_PRICE * 1000:.1f} руб")
    ]

    for stars, text in options:
        keyboard.row(InlineKeyboardButton(text, callback_data=f'buy_{stars}'))

    keyboard.row(InlineKeyboardButton("↩️ Назад", callback_data='main_menu'))
    return keyboard

def deposit_keyboard(user_data):
    keyboard = InlineKeyboardMarkup()

    amounts = [50, 100, 500, 1000]
    for amount in amounts:
        keyboard.row(InlineKeyboardButton(f"{amount} руб", callback_data=f'deposit_{amount}'))

    keyboard.row(InlineKeyboardButton("↩️ Назад", callback_data='main_menu'))
    return keyboard

def back_to_main_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.row(InlineKeyboardButton("↩️ Назад", callback_data='main_menu'))
    return keyboard

# Обработчики команд бота
@bot.message_handler(commands=['start'])
def start(message):
    user = message.from_user
    create_user(user.id, user.username)

    bot.send_photo(
        message.chat.id,
        MAIN_MENU_IMAGE,
        caption=WELCOME_MES,
        reply_markup=main_menu_keyboard()
    )

@bot.message_handler(commands=['menu'])
def main_menu(message):
    user = message.from_user
    bot.send_photo(
        message.chat.id,
        MAIN_MENU_IMAGE,
        caption=WELCOME_MES,
        reply_markup=main_menu_keyboard()
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call: CallbackQuery):
    user_id = call.from_user.id
    user_data = get_user(user_id)

    if call.data == 'buy_stars':
        buy_stars_menu(call, user_data)
    elif call.data == 'deposit':
        deposit_menu(call, user_data)
    elif call.data == 'profile':
        show_profile(call, user_data)
    elif call.data == 'main_menu':
        main_menu_callback(call)
    elif call.data.startswith('buy_'):
        stars = int(call.data.split('_')[1])
        process_star_purchase(call, user_data, stars)
    elif call.data.startswith('deposit_'):
        amount = int(call.data.split('_')[1])
        process_deposit(call, user_data, amount)

def buy_stars_menu(call, user_data):
    bot.edit_message_caption(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        caption="🎯 Выберите количество звезд для покупки:\n\n"
               f"💰 Ваш баланс: {user_data['balance']} руб",
        reply_markup=buy_stars_keyboard(user_data)
    )

def deposit_menu(call, user_data):
    bot.edit_message_caption(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        caption="💳 Выберите сумму для пополнения:\n\n"
               f"💰 Текущий баланс: {user_data['balance']} руб",
        reply_markup=deposit_keyboard(user_data)
    )

def show_profile(call, user_data):
    bot.edit_message_caption(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        caption=f"👤 Ваш профиль:\n\n"
               f"🆔 ID: {user_data['user_id']}\n"
               f"👤 Username: @{user_data['username'] or 'Не указан'}\n"
               f"💰 Баланс: {user_data['balance']} руб\n",
        reply_markup=back_to_main_keyboard()
    )

def main_menu_callback(call):
    bot.edit_message_caption(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        caption=WELCOME_MES,
        reply_markup=main_menu_keyboard()
    )


import threading
import time

# Определяем флаг для остановки анимации
animation_running = True


def animate_caption(bot, call):
    """
    Функция для анимации сообщения о загрузке.
    """
    global animation_running
    dots = 1
    while animation_running:
        caption = "🔄 Отправляю звезды" + "." * dots
        try:
            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=caption,
                reply_markup=None
            )
        except Exception as e:
            # Обработка исключения, если сообщение было удалено
            print(f"Ошибка при обновлении сообщения: {e}")
            break

        dots = (dots % 3) + 1
        time.sleep(1)  # Задержка в 1 секунду


def process_star_purchase(call, user_data, stars):
    global animation_running
    cost = stars * STAR_PRICE

    if user_data['balance'] < cost:
        bot.answer_callback_query(call.id, "❌ Недостаточно средств на балансе!", show_alert=True)
        return

    # Запускаем анимацию в отдельном потоке
    animation_running = True
    animation_thread = threading.Thread(target=animate_caption, args=(bot, call))
    animation_thread.start()

    try:
        # Получаем токен Fragment
        token = load_fragment_token() or authenticate_fragment()
        if not token:
            # Останавливаем анимацию
            animation_running = False
            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption="❌ Ошибка системы. Попробуйте позже.",
                reply_markup=back_to_main_keyboard()
            )
            return

        # Отправляем звезды
        success, message = send_stars(token, user_data['username'], stars)

        # Останавливаем анимацию после завершения
        animation_running = False

        if success:
            # Списание средств
            update_balance(user_data['user_id'], -cost)
            add_transaction(user_data['user_id'], stars, 'stars_purchase')

            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=f"✅ Успешно отправлено {stars} звезд!",
                reply_markup=back_to_main_keyboard()
            )
        else:
            # Проверяем, закончились ли звезды (типичная ошибка Fragment)
            if "Not enough funds for wallet " in message.lower() or "баланс" in message.lower() or "not enough funds" in message.lower():
                error_message = "❌ У нас закончились звезды. Попробуйте позже."
            else:
                error_message = f"❌ Ошибка при отправке: {message}"

            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=error_message,
                reply_markup=back_to_main_keyboard()
            )
    finally:
        # Убеждаемся, что анимация всегда останавливается
        animation_running = False
        animation_thread.join()  # Ждем завершения потока с анимацией

def process_deposit(call, user_data, amount):
    payment_url = create_yookassa_payment(amount, user_data['user_id'])

    if payment_url:
        keyboard = InlineKeyboardMarkup()
        keyboard.row(InlineKeyboardButton("✅ Я оплатил", callback_data='check_payment'))
        keyboard.row(InlineKeyboardButton("↩️ Назад", callback_data='deposit'))

        bot.edit_message_caption(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            caption=f"💳 Для пополнения на {amount} руб:\n\n"
                   f"1. Перейдите по ссылке: {payment_url}\n"
                   f"2. Оплатите счет\n"
                   f"3. Нажмите кнопку '✅ Я оплатил'\n\n"
                   "⚠️ Платеж обрабатывается автоматически в течение нескольких минут.",
            reply_markup=keyboard
        )
    else:
        bot.answer_callback_query(call.id, "❌ Ошибка создания платежа!", show_alert=True)

def main():
    # Инициализация базы данных
    init_db()

    # Проверка и получение JWT-токена Fragment API при запуске
    logger.info("Проверка и обновление токена Fragment API...")
    token = load_fragment_token()
    if not token:
        logger.info("Токен не найден. Запуск аутентификации...")
        token = authenticate_fragment()
        if token:
            logger.info("✅ Аутентификация Fragment API прошла успешно!")
        else:
            logger.error("❌ Не удалось получить токен Fragment API. Отправка звезд будет невозможна.")
    else:
        logger.info("✅ Существующий токен Fragment API найден.")

    # Запуск бота
    logger.info("Бот запущен...")
    bot.infinity_polling()

if __name__ == "__main__":
    main()
