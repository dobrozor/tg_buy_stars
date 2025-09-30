import base64
import os
import json
import logging
import sqlite3
import uuid
import threading
import time
import asyncio
import requests
from datetime import datetime
from dotenv import load_dotenv
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message


try:
    from config import STAR_PRICE, MAIN_MENU_IMAGE, WELCOME_MES, logger, REFERRAL_REWARD # ДОБАВЛЕН REFERRAL_REWARD
    from db import (
        init_db, get_user, create_user, update_balance, add_transaction,
        get_pending_payment, update_payment_status,
        set_session_data, get_session_data, delete_session_data,
        get_setting, set_setting, get_referral_count # ДОБАВЛЕН get_referral_count
    )
    from fragment_api import load_fragment_token, authenticate_fragment, send_stars
    from yookassa import create_yookassa_payment, check_payment_status
    from keyboards import (
        main_menu_keyboard, buy_stars_options_keyboard, buy_stars_quantity_keyboard,
        back_to_main_keyboard
    )
except ImportError as e:

    class MockLogger:
        def info(self, msg): print(f"INFO: {msg}")

        def error(self, msg): print(f"ERROR: {msg}")

        def warning(self, msg): print(f"WARNING: {msg}")


# Загрузка переменных окружения
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')

TON_DEPOSIT_ADDRESS = os.getenv('TON_DEPOSIT_ADDRESS')  # Адрес кошелька для приема
TON_API_KEY = os.getenv('TON_API_KEY')  # Ключ от toncenter.com
TON_API_BASE_URL = 'https://toncenter.com'

TON_RATE_API = "https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=rub"

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

animation_running = False


# --- Анимация загрузки ---
def animate_caption(bot, call):
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
            if "message is not modified" not in str(e):
                logger.warning(f"Ошибка при обновлении сообщения анимации: {e}")
            break

        dots = (dots % 3) + 1
        time.sleep(1)


# --- Обработчики команд ---
@bot.message_handler(commands=['start', 'menu'])
def start_or_menu(message: Message):
    user = message.from_user
    username = user.username if user.username else None

    # --- ЛОГИКА РЕФЕРАЛЬНОЙ ССЫЛКИ ---
    referrer_id = None
    if message.text and len(message.text.split()) > 1:
        payload = message.text.split()[1]
        # Ожидаем формат: /start r<referrer_id>
        if payload.startswith('r') and payload[1:].isdigit():
            possible_referrer_id = int(payload[1:])
            # Проверяем, что реферер не сам себя пригласил
            if possible_referrer_id != user.id:
                # Проверяем, что реферер существует
                if get_user(possible_referrer_id):
                    referrer_id = possible_referrer_id
                    logger.info(f"Обнаружен реферер: {referrer_id} для нового пользователя: {user.id}")

    # Создаем пользователя и получаем статус создания
    user_created = create_user(user.id, username, referrer_id)  # ПЕРЕДАЕМ referrer_id

    # Если пользователь НОВЫЙ И был реферер, начисляем награду
    if user_created and referrer_id is not None:
        update_balance(referrer_id, REFERRAL_REWARD)
        add_transaction(
            user_id=referrer_id,
            amount=REFERRAL_REWARD,
            transaction_type='referral_reward',
            status='completed',
            target_user=str(user.id)
        )
        # Уведомляем реферера
        try:
            bot.send_message(
                referrer_id,
                f"✅ Награда за реферала!\n\n"
                f"Пользователь @{username or user.id} зарегистрировался по вашей ссылке. На ваш баланс зачислено **{REFERRAL_REWARD} руб**!",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление рефереру {referrer_id}: {e}")

    # --- КОНЕЦ ЛОГИКИ РЕФЕРАЛЬНОЙ ССЫЛКИ ---

    bot.send_photo(
        message.chat.id,
        MAIN_MENU_IMAGE,
        caption=WELCOME_MES,
        reply_markup=main_menu_keyboard()
    )


# --- Обработчики колбэков (Меню и Профиль) ---
@bot.callback_query_handler(func=lambda call: call.data == 'buy_stars')
def buy_stars_selection_menu(call: CallbackQuery):
    bot.edit_message_caption(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        caption="Выберите, кому вы хотите купить звёзды:",
        reply_markup=buy_stars_options_keyboard()
    )


# --- ОБНОВЛЕННАЯ ФУНКЦИЯ КЛАВИАТУРЫ ДЛЯ ДЕПОЗИТА ---
def deposit_keyboard(user_data):
    keyboard = InlineKeyboardMarkup()
    amounts = [50, 100, 500, 1000]
    for amount in amounts:
        keyboard.row(InlineKeyboardButton(f"{amount} руб (ЮKassa)", callback_data=f'deposit_{amount}'))

    # Добавляем TON пополнение
    keyboard.row(InlineKeyboardButton("🪙 Пополнить TON", callback_data='deposit_ton'))

    # Добавляем кнопку для ввода кастомной суммы (ЮKassa)
    keyboard.row(InlineKeyboardButton("✍️ Другая сумма (ЮKassa)", callback_data='deposit_custom'))
    keyboard.row(InlineKeyboardButton("↩️ Назад", callback_data='main_menu'))
    return keyboard


@bot.callback_query_handler(func=lambda call: call.data == 'deposit')
def deposit_menu(call: CallbackQuery):
    user_id = call.from_user.id
    user_data = get_user(user_id)
    bot.edit_message_caption(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        caption="💳 Выберите способ пополнения и сумму:\n\n"
                f"💰 Текущий баланс: {user_data['balance']:.2f} руб",
        reply_markup=deposit_keyboard(user_data)
    )


@bot.callback_query_handler(func=lambda call: call.data == 'profile')
def show_profile(call: CallbackQuery):
    user_id = call.from_user.id
    user_data = get_user(user_id)
    bot.edit_message_caption(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        caption=f"👤 Ваш профиль:\n\n"
                f"🆔 ID: {user_data['user_id']}\n"
                f"👤 Username: @{user_data['username'] or 'Не указан'}\n"
                f"💰 Баланс: {user_data['balance']:.2f} руб\n",
        reply_markup=back_to_main_keyboard()
    )


@bot.callback_query_handler(func=lambda call: call.data == 'referrals_menu')
def show_referrals_menu(call: CallbackQuery):
    user_id = call.from_user.id

    # Получаем никнейм бота для генерации ссылки
    bot_username = bot.get_me().username
    referral_link = f"https://t.me/{bot_username}?start=r{user_id}"

    # Получаем количество рефералов
    referral_count = get_referral_count(user_id)

    # Создаем клавиатуру для меню рефералов
    referral_keyboard = InlineKeyboardMarkup()
    referral_keyboard.row(InlineKeyboardButton("↩️ Назад", callback_data='main_menu'))

    caption = (
        f"🔗 **Реферальная программа**\n\n"
        f"Приглашайте друзей и получайте вознаграждение!\n"
        f"🎁 За каждого приглашенного пользователя, который запустит бота, вы получаете **{REFERRAL_REWARD} руб** на баланс.\n\n"
        f"👤 Количество ваших рефералов: **{referral_count}**\n\n"
        f"**Ваша реферальная ссылка:**\n"
        f"`{referral_link}`"
    )

    bot.edit_message_caption(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        caption=caption,
        reply_markup=referral_keyboard,
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: call.data == 'main_menu')
def main_menu_callback(call: CallbackQuery):
    delete_session_data(call.from_user.id)  # Очищаем сессию при возврате в меню
    bot.edit_message_caption(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        caption=WELCOME_MES,
        reply_markup=main_menu_keyboard()
    )


# --- Покупка звезд (логика остается прежней) ---
@bot.callback_query_handler(func=lambda call: call.data == 'buy_stars_self')
def buy_stars_self(call: CallbackQuery):
    user_id = call.from_user.id
    user_data = get_user(user_id)

    # Сохраняем собственный username и ID сообщения в БД
    session_data = {
        'target_username': user_data['username'],
        'state': 'buying_stars',
        'message_id': call.message.message_id
    }
    set_session_data(user_id, session_data)

    bot.edit_message_caption(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        caption="🎯 Выберите количество звезд для покупки:\n\n"
                f"💰 Ваш баланс: {user_data['balance']:.2f} руб",
        reply_markup=buy_stars_quantity_keyboard(user_data)
    )


@bot.callback_query_handler(func=lambda call: call.data == 'buy_stars_friend')
def buy_stars_friend(call: CallbackQuery):
    user_id = call.from_user.id

    # Сохраняем состояние ожидания username и ID сообщения в БД
    session_data = {
        'state': 'waiting_for_username',
        'message_id': call.message.message_id,
        'target_username': None  # Сбрасываем предыдущего получателя
    }
    set_session_data(user_id, session_data)

    bot.edit_message_caption(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        caption="Пожалуйста, введите @username друга (без @):",
        reply_markup=back_to_main_keyboard()
    )
    bot.register_next_step_handler(call.message, process_friend_username)


def process_friend_username(message: Message):
    user_id = message.from_user.id
    username_input = message.text.strip().lstrip('@')

    # Получаем состояние из БД
    state_data = get_session_data(user_id)
    target_message_id = state_data.get('message_id')

    # Проверка состояния
    if state_data.get('state') != 'waiting_for_username' or not target_message_id:
        return  # Игнорируем, если не в режиме ожидания username

    try:
        # Удаляем сообщение пользователя, чтобы не засорять чат
        if message.message_id != target_message_id:
            bot.delete_message(message.chat.id, message.message_id)
    except Exception as e:
        logger.error(f"Не удалось удалить сообщение: {e}")

    if not username_input:
        bot.edit_message_caption(
            chat_id=message.chat.id,
            message_id=target_message_id,
            caption="❌ Некорректный username. Попробуйте еще раз:",
            reply_markup=back_to_main_keyboard()
        )
        bot.register_next_step_handler(message, process_friend_username)
        return

    # Обновляем сессию в БД: сохраняем получателя и сбрасываем состояние ожидания
    session_data = {
        'target_username': username_input,
        'state': 'buying_stars',
        'message_id': target_message_id
    }
    set_session_data(user_id, session_data)

    user_data = get_user(user_id)

    bot.edit_message_caption(
        chat_id=message.chat.id,
        message_id=target_message_id,
        caption=f"Вы будете покупать звёзды для пользователя **@{username_input}**. Выберите количество:",
        reply_markup=buy_stars_quantity_keyboard(user_data),
        parse_mode='Markdown'
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_'))
def handle_star_purchase(call: CallbackQuery):
    stars = int(call.data.split('_')[1])
    user_id = call.from_user.id
    user_data = get_user(user_id)
    cost = stars * STAR_PRICE

    # Получаем целевой username из БД
    session_data = get_session_data(user_id)
    target_username = session_data.get('target_username')

    if not target_username:
        bot.answer_callback_query(call.id, "❌ Не удалось определить получателя. Пожалуйста, начните заново.",
                                  show_alert=True)
        main_menu_callback(call)
        return

    if user_data['balance'] < cost:
        bot.answer_callback_query(call.id, f"❌ Недостаточно средств на балансе. Нужно {cost:.2f} руб.", show_alert=True)
        return

    # Запуск анимации
    global animation_running
    animation_running = True
    animation_thread = threading.Thread(target=animate_caption, args=(bot, call))
    animation_thread.start()

    try:
        token = load_fragment_token() or authenticate_fragment()
        if not token:
            animation_running = False
            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption="❌ Ошибка системы. Не удалось получить токен Fragment API. Попробуйте позже.",
                reply_markup=back_to_main_keyboard()
            )
            return

        success, message = send_stars(token, target_username, stars)

        animation_running = False
        animation_thread.join()

        if success:
            update_balance(user_data['user_id'], -cost)
            add_transaction(user_data['user_id'], stars, 'stars_purchase', target_user=target_username)
            user_data_new = get_user(user_id)

            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=f"✅ Успешно отправлено {stars} звезд пользователю **@{target_username}**!\n"
                        f"💰 Ваш новый баланс: {user_data_new['balance']:.2f} руб",
                reply_markup=back_to_main_keyboard(),
                parse_mode='Markdown'
            )
        else:
            if "not enough funds" in message.lower() or "баланс" in message.lower():
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
        # Очищаем состояние после завершения
        delete_session_data(user_id)

@bot.callback_query_handler(func=lambda call: call.data == 'deposit_ton')
def handle_ton_deposit(call: CallbackQuery):
    user_id = call.from_user.id

    if not TON_DEPOSIT_ADDRESS:
        bot.answer_callback_query(call.id, "❌ Пополнение TON временно недоступно (адрес не указан).", show_alert=True)
        return

    # Получаем курс для отображения
    ton_rub_rate = get_ton_rub_rate()
    rate_text = f"~{ton_rub_rate:.2f} руб" if ton_rub_rate else "курс недоступен"

    # URL для быстрой оплаты
    payment_url = f'ton://transfer/{TON_DEPOSIT_ADDRESS}?text={user_id}'

    caption = (
        f"🪙 Пополнение через TON:\n\n"
        f"1. Переведите любую сумму TON на этот адрес:\n"
        f"   `{TON_DEPOSIT_ADDRESS}`\n\n"
        f"2. **Обязательно** укажите в комментарии свой ID:\n"
        f"   `{user_id}`\n\n"
        f"💰 Текущий курс: 1 TON ≈ {rate_text}\n"
        f"⚠️ Средства будут зачислены на ваш баланс в **РУБЛЯХ** после 3 подтверждений сети."
    )

    keyboard = InlineKeyboardMarkup()
    keyboard.row(InlineKeyboardButton("↗️ Оплатить в TON", url=payment_url))
    keyboard.row(InlineKeyboardButton("↩️ Назад", callback_data='deposit'))

    bot.edit_message_caption(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        caption=caption,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )


# --- Пополнение ЮKassa (логика остается прежней) ---
@bot.callback_query_handler(
    func=lambda call: call.data.startswith('deposit_') and call.data != 'deposit_custom' and call.data != 'deposit_ton')
def handle_predefined_deposit(call: CallbackQuery):
    amount = int(call.data.split('_')[1])
    process_deposit(call, amount)


@bot.callback_query_handler(func=lambda call: call.data == 'deposit_custom')
def handle_custom_deposit(call: CallbackQuery):
    user_id = call.from_user.id

    # Сохраняем состояние ожидания суммы и ID сообщения в БД
    session_data = {
        'state': 'waiting_for_deposit_amount',
        'message_id': call.message.message_id
    }
    set_session_data(user_id, session_data)

    bot.edit_message_caption(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        caption="💰 На какую сумму хотите пополнить?",
        reply_markup=back_to_main_keyboard()
    )
    bot.register_next_step_handler(call.message, process_custom_deposit_amount)


def process_custom_deposit_amount(message: Message):
    user_id = message.from_user.id
    amount_input = message.text.strip()

    # Получаем состояние из БД
    state_data = get_session_data(user_id)
    target_message_id = state_data.get('message_id')

    # Проверка состояния
    if state_data.get('state') != 'waiting_for_deposit_amount' or not target_message_id:
        return

    try:
        # Удаляем сообщение пользователя, чтобы не засорять чат
        if message.message_id != target_message_id and target_message_id:
            bot.delete_message(message.chat.id, message.message_id)
    except Exception as e:
        logger.error(f"Не удалось удалить сообщение: {e}")

    try:
        amount = round(float(amount_input), 2)
        if amount <= 0:
            raise ValueError
    except ValueError:
        if target_message_id:
            bot.edit_message_caption(
                chat_id=message.chat.id,
                message_id=target_message_id,
                caption="❌ Некорректная сумма. Пожалуйста, введите число больше 0:",
                reply_markup=back_to_main_keyboard()
            )
            bot.register_next_step_handler(message, process_custom_deposit_amount)
            return
        else:
            bot.send_message(message.chat.id, "❌ Некорректная сумма. Пожалуйста, начните заново.")
            return

    # --- ИСПРАВЛЕНИЕ БАГА: Создание объекта-заглушки (MockCall) вместо CallbackQuery ---
    call_mock = type('MockCall', (object,), {
        'id': 'mock_id',
        'from_user': message.from_user,
        'message': type('MockMessage', (object,), {
            'chat': type('MockChat', (object,), {'id': message.chat.id})(),
            'message_id': target_message_id
        })()
    })()

    # Создаем и обрабатываем платеж
    process_deposit(call_mock, amount)

    # Удаляем состояние после завершения
    delete_session_data(user_id)


def process_deposit(call, amount: float):
    # 'call' может быть как CallbackQuery, так и MockCall
    bot_username = bot.get_me().username
    payment_url = create_yookassa_payment(amount, call.from_user.id, bot_username)

    if payment_url:
        keyboard = InlineKeyboardMarkup()
        keyboard.row(InlineKeyboardButton("✅ Я оплатил", callback_data='check_payment'))

        bot.edit_message_caption(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            caption=f"💳 Для пополнения на **{amount:.2f} руб**:\n\n"
                    f"1. Перейдите по ссылке: {payment_url}\n"
                    f"2. Оплатите счет\n"
                    f"3. Нажмите кнопку '✅ Я оплатил'\n\n"
                    "⚠️ Платеж обрабатывается автоматически в течение нескольких минут.",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    else:
        # bot.answer_callback_query работает как с CallbackQuery, так и с MockCall (если атрибут 'id' корректно имитирован)
        try:
            bot.answer_callback_query(call.id, "❌ Ошибка создания платежа! Попробуйте позже.", show_alert=True)
        except Exception:
            logger.error("Не удалось ответить на MockCall, но продолжаем...")

        # Возврат в меню депозита
        deposit_menu(call)


@bot.callback_query_handler(func=lambda call: call.data == 'check_payment')
def handle_check_payment(call: CallbackQuery):
    user_id = call.from_user.id

    payment = get_pending_payment(user_id)

    if not payment:
        bot.answer_callback_query(call.id, "❌ Активный платеж для проверки не найден", show_alert=True)
        return

    payment_id, amount = payment
    payment_info = check_payment_status(payment_id)

    if not payment_info:
        bot.answer_callback_query(call.id, "❌ Ошибка проверки платежа", show_alert=True)
        return

    if payment_info['status'] == 'succeeded':
        # Обновление статуса платежа
        update_payment_status(payment_id, 'succeeded')

        # Обновление баланса и добавление транзакции
        update_balance(user_id, amount)
        add_transaction(user_id, amount, 'deposit', 'completed')

        user_data = get_user(user_id)

        bot.edit_message_caption(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            caption=f"✅ Платеж успешно завершен!\n"
                    f"💳 Сумма: **{amount:.2f} руб**\n"
                    f"💰 Новый баланс: **{user_data['balance']:.2f} руб**",
            reply_markup=back_to_main_keyboard(),
            parse_mode='Markdown'
        )

    elif payment_info['status'] == 'pending':
        bot.answer_callback_query(
            call.id,
            "⌛ Платеж еще не прошел. Попробуйте проверить позже.",
            show_alert=True
        )
    else:
        # Платеж не прошел (например, canceled, expired, etc.)
        update_payment_status(payment_id, payment_info['status'])
        bot.answer_callback_query(
            call.id,
            f"❌ Платеж не прошел. Статус: {payment_info['status']}",
            show_alert=True
        )


# --- ФУНКЦИИ ФОНОВОГО МОНИТОРИНГА TON (ОБНОВЛЕННЫЕ) ---

def get_ton_rub_rate():
    """Получает текущий курс TON к рублю."""
    try:
        # Небольшая задержка, чтобы не спамить API
        time.sleep(0.5)
        response = requests.get(TON_RATE_API, timeout=5)
        response.raise_for_status()
        data = response.json()
        rate = data.get('the-open-network', {}).get('rub')
        if rate:
            return float(rate)
        return None
    except Exception as e:
        logger.error(f"Ошибка получения курса TON/RUB: {e}")
        return None


async def check_deposits():
    """Мониторинг TON транзакций и пополнение баланса."""
    if not TON_DEPOSIT_ADDRESS or not TON_API_KEY:
        logger.error("TON_DEPOSIT_ADDRESS или TON_API_KEY не заданы. Мониторинг не запущен.")
        return

    # --- Чтение last_lt из БД вместо файла ---
    last_lt_str = get_setting('last_lt', '0')
    try:
        last_lt = int(last_lt_str)
    except ValueError:
        logger.error(f"Некорректное значение last_lt в БД: '{last_lt_str}'. Используется 0.")
        last_lt = 0

    logger.info(f"Запуск мониторинга TON. Последний LT: {last_lt}")

    while True:
        await asyncio.sleep(10)  # Проверяем каждые 10 секунд
        try:
            ton_rub_rate = get_ton_rub_rate()
            if not ton_rub_rate:
                continue

            api_url = (
                f'{TON_API_BASE_URL}/api/v2/getTransactions?'
                f'address={TON_DEPOSIT_ADDRESS}&limit=100&'
                f'archival=true&api_key={TON_API_KEY}'
            )

            resp = requests.get(api_url, timeout=10).json()

            if not resp.get('ok'):
                logger.error(f"Ошибка ответа TON API: {resp.get('error', 'Неизвестная ошибка')}")
                continue

            current_max_lt = last_lt

            # Обрабатываем транзакции в обратном порядке (от новых к старым)
            for tx in reversed(resp.get('result', [])):
                lt = int(tx['transaction_id']['lt'])

                if lt > current_max_lt:
                    current_max_lt = lt

                if lt <= last_lt:
                    continue

                in_msg = tx.get('in_msg')
                if not in_msg:
                    continue

                value_nano = int(in_msg.get('value', 0))

                if value_nano > 0:
                    uid_str = ''
                    # Пытаемся получить user_id из поля 'message' (обычно там комментарий)
                    uid_str = in_msg.get('message', '').strip()

                    if not uid_str.isdigit():
                        logger.warning(f"Пропущена транзакция: {lt}. Некорректный uid в комментарии: '{uid_str}'")
                        continue

                    uid = int(uid_str)
                    ton_amount = value_nano / 1e9

                    # Конвертация TON в RUB
                    rub_amount = round(ton_amount * ton_rub_rate, 2)

                    if rub_amount < 1.0:  # Игнорируем слишком маленькие суммы
                        continue

                    user_data = get_user(uid)
                    if not user_data:
                        logger.warning(f"Пропущена транзакция: {lt}. Пользователь {uid} не найден.")
                        continue

                    # Пополнение баланса в РУБЛЯХ
                    update_balance(uid, rub_amount)
                    # target_user используем для хранения информации о TON транзакции
                    add_transaction(uid, rub_amount, 'deposit_ton', 'completed', target_user=f'{ton_amount:.4f} TON')

                    logger.info(f"✅ Депозит TON подтвержден! User: {uid}, TON: {ton_amount}, RUB: {rub_amount}")

                    try:
                        bot.send_message(
                            uid,
                            '✅ Депозит через TON подтвержден!\n'
                            f'Сумма: *+{ton_amount:.4f} TON* ({rub_amount:.2f} руб)\n'
                            f'Ваш новый баланс: {get_user(uid)["balance"]:.2f} руб',
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        logger.error(f"Error sending message to user {uid}: {e}")

            # --- Сохранение максимального LT в БД ---
            if current_max_lt > last_lt:
                last_lt = current_max_lt
                set_setting('last_lt', last_lt)  # <--- Запись в БД

        except requests.exceptions.Timeout:
            logger.error("TON API запрос таймаут.")
        except Exception as e:
            logger.error(f"Критическая ошибка в TON мониторинге: {e}")


def run_async_loop():
    """Запуск asyncio loop в отдельном потоке."""
    # Небольшая задержка перед запуском
    time.sleep(1)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(check_deposits())


# --- ГЛАВНАЯ ФУНКЦИЯ ---

def main():
    # Предполагается, что init_db() определен в db.py
    try:
        init_db()
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")

    # --- ЗАПУСК TON МОНИТОРИНГА ---
    deposit_thread = threading.Thread(target=run_async_loop, daemon=True)
    deposit_thread.start()
    logger.info("Запущен фоновый мониторинг TON депозитов.")

    # Проверка и обновление токена Fragment API
    logger.info("Проверка и обновление токена Fragment API...")
    try:
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
    except Exception as e:
        logger.error(f"Ошибка работы с Fragment API: {e}")

    logger.info("Бот запущен...")
    try:
        bot.infinity_polling()
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")


if __name__ == "__main__":
    main()