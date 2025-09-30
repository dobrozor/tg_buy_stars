import os
import logging
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Константы Бота ---
STAR_PRICE = 1.5
MAIN_MENU_IMAGE = "https://sociogramm.ru/assets/uploads/blogs/blog/kak-poluchit-zvezdy-v-telegram-1.jpeg"
WELCOME_MES = f"Привет👋\n\nДобро пожаловать в бота для покупки Telegram Stars! 🌟\n\nВыберите действие:"
TOKEN_FILE = "auth_token.json"
MIN_STARS = 50

REFERRAL_REWARD = 5.0 # Вознаграждение за приглашенного пользователя (в рублях)

# --- Конфигурация API ---
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = os.getenv('ADMIN_ID')
DB_NAME = 'bot_database.db'

# ЮKassa
YOOKASSA_SHOP_ID = os.getenv('YOOKASSA_SHOP_ID')
YOOKASSA_SECRET_KEY = os.getenv('YOOKASSA_SECRET_KEY')
YOOKASSA_API_URL = "https://api.yookassa.ru/v3/payments"

# TON Wallet Configuration
TON_DEPOSIT_ADDRESS = os.getenv('TON_DEPOSIT_ADDRESS')
TON_API_KEY = os.getenv('TON_API_KEY')
TON_API_BASE_URL = 'https://toncenter.com'

# Fragment API
FRAGMENT_API_URL = "https://api.fragment-api.com/v1"
FRAGMENT_API_KEY = os.getenv("FRAGMENT_API_KEY")
FRAGMENT_PHONE = os.getenv("FRAGMENT_PHONE")
FRAGMENT_MNEMONICS = os.getenv("FRAGMENT_MNEMONICS")

# Проверка наличия токена бота
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не найден в переменных окружения.")

# Проверка наличия учетных данных ЮKassa
if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
    logger.warning("⚠️ Учетные данные ЮKassa не найдены.")

# Проверка наличия учетных данных Fragment
if not FRAGMENT_API_KEY or not FRAGMENT_PHONE or not FRAGMENT_MNEMONICS:
    logger.warning("⚠️ Учетные данные Fragment API не найдены. Отправка звезд будет невозможна.")