import base64
import uuid
import requests
from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, YOOKASSA_API_URL, logger
from db import add_payment

def create_yookassa_payment(amount, user_id, bot_username):
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        logger.error("❌ Учетные данные ЮKassa отсутствуют.")
        return None

    auth_string = f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}".encode('utf-8')
    encoded_auth = base64.b64encode(auth_string).decode('utf-8')

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {encoded_auth}",
        "Idempotence-Key": str(uuid.uuid4())
    }

    payload = {
        "amount": {
            "value": f"{amount:.2f}",
            "currency": "RUB"
        },
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": f"https://t.me/{bot_username}"
        },
        "description": f"Пополнение баланса (user_id: {user_id})",
        "metadata": {
            "user_id": user_id
        }
    }

    try:
        response = requests.post(YOOKASSA_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        payment_data = response.json()

        # Сохранение информации о платеже в БД
        add_payment(user_id, amount, payment_data['id'], 'pending')

        return payment_data['confirmation']['confirmation_url']
    except Exception as e:
        logger.error(f"Ошибка создания платежа ЮKassa: {str(e)}")
        return None


def check_payment_status(payment_id):
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        logger.error("❌ Учетные данные ЮKassa отсутствуют.")
        return None

    url = f"{YOOKASSA_API_URL}/{payment_id}"

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