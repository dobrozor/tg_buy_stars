import json
import os
import telebot
import config
import requests

from bot import bot
from config import (
    FRAGMENT_API_URL, FRAGMENT_API_KEY, FRAGMENT_PHONE,
    FRAGMENT_MNEMONICS, TOKEN_FILE, logger
)


def load_fragment_token():
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r") as f:
                return json.load(f).get("token")
        except Exception as e:
            logger.error(f"❌ Ошибка чтения токена из файла: {e}")
            return None
    return None


def save_fragment_token(token):
    try:
        with open(TOKEN_FILE, "w") as f:
            json.dump({"token": token}, f)
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения токена в файл: {e}")


def authenticate_fragment():
    if not FRAGMENT_MNEMONICS:
        logger.error("❌ FRAGMENT_MNEMONICS не установлен. Аутентификация невозможна.")
        return None

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


def send_stars(token, username, quantity):
    try:
        data = {
            "username": username,
            "quantity": quantity,
            "show_sender": "false"
        }
        headers = {
            "Authorization": f"JWT {token}",
            "Content-Type": "application/json"
        }

        logger.info(f"🔄 Отправка {quantity} ⭐ пользователю @{username}...")
        res = requests.post(f"{FRAGMENT_API_URL}/order/stars/", json=data, headers=headers)

        if res.status_code == 200:
            bot.send_message(config.ADMIN_ID, f"✅ Отправлены {quantity} ⭐ пользователю @{username}...")
            logger.info("✅ Звезды успешно отправлены!")
            return True, "Успешно"
        else:
            bot.send_message(config.ADMIN_ID, f"❌ Ошибка отправки {quantity} ⭐ пользователю @{username}. \n\nТекст ошибки: {res.text}")
            error_msg = f"❌ Ошибка отправки: {res.text}"
            logger.error(error_msg)
            return False, res.text

    except Exception as e:
        error_msg = f"❌ Исключение при отправке: {e}"
        logger.error(error_msg)
        return False, str(e)