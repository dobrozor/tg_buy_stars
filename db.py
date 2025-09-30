import sqlite3
from config import DB_NAME, logger


# Инициализация базы данных
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance REAL DEFAULT 0.0,
        referrer_id INTEGER,  -- НОВОЕ ПОЛЕ для ID пригласившего
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (referrer_id) REFERENCES users (user_id)
    )
    ''')

    # Таблица транзакций
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        type TEXT,
        status TEXT,
        target_user TEXT,
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

    # Таблица сессий/состояний
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sessions (
        user_id INTEGER PRIMARY KEY,
        state TEXT,
        target_username TEXT,
        message_id INTEGER,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')

    # --- НОВАЯ ТАБЛИЦА: НАСТРОЙКИ (для last_lt) ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    ''')

    conn.commit()
    conn.close()
    logger.info("✅ База данных инициализирована.")


def get_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()

    if user:
        # Обновленный возврат с учетом нового поля referrer_id
        return {
            'user_id': user[0],
            'username': user[1],
            'balance': user[2],
            'referrer_id': user[3],  # Индекс 3 для referrer_id
            'created_at': user[4]   # Индекс 4 для created_at
        }
    return None


def create_user(user_id, username, referrer_id=None):  # ДОБАВЛЕН referrer_id
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Обновленный запрос: добавлено поле referrer_id
    cursor.execute(
        'INSERT OR IGNORE INTO users (user_id, username, referrer_id) VALUES (?, ?, ?)',
        (user_id, username, referrer_id)  # ПЕРЕДАЧА referrer_id
    )
    conn.commit()
    conn.close()

    # Возвращаем True, если пользователь был создан (ROWCOUNT=1)
    return cursor.rowcount == 1

def get_referral_count(user_id):
    """Возвращает количество пользователей, приглашенных данным пользователем."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT COUNT(*) FROM users WHERE referrer_id = ?',
        (user_id,)
    )
    count = cursor.fetchone()[0]
    conn.close()
    return count


def update_balance(user_id, amount):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE users SET balance = ROUND(balance + ?, 2) WHERE user_id = ?',
        (amount, user_id)
    )
    conn.commit()
    conn.close()


def add_transaction(user_id, amount, transaction_type, status='completed', target_user=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO transactions (user_id, amount, type, status, target_user) VALUES (?, ?, ?, ?, ?)',
        (user_id, amount, transaction_type, status, target_user)
    )
    conn.commit()
    conn.close()


def add_payment(user_id, amount, yookassa_id, status='pending'):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO payments (user_id, amount, yookassa_id, status) VALUES (?, ?, ?, ?)',
        (user_id, amount, yookassa_id, status)
    )
    conn.commit()
    conn.close()


def get_pending_payment(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT yookassa_id, amount FROM payments '
        'WHERE user_id = ? AND status = "pending" '
        'ORDER BY created_at DESC LIMIT 1',
        (user_id,)
    )
    payment = cursor.fetchone()
    conn.close()
    return payment


def update_payment_status(yookassa_id, status):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE payments SET status = ? WHERE yookassa_id = ?',
        (status, yookassa_id)
    )
    conn.commit()
    conn.close()


# --- НОВЫЕ ФУНКЦИИ ДЛЯ РАБОТЫ С СЕССИЯМИ/СОСТОЯНИЯМИ ---

def set_session_data(user_id, data):
    """Сохраняет или обновляет данные сессии пользователя."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    state = data.get('state')
    target_username = data.get('target_username')
    message_id = data.get('message_id')

    cursor.execute(
        '''
        INSERT OR REPLACE INTO sessions 
        (user_id, state, target_username, message_id, updated_at) 
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''',
        (user_id, state, target_username, message_id)
    )
    conn.commit()
    conn.close()


def get_session_data(user_id):
    """Получает данные сессии пользователя."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT state, target_username, message_id FROM sessions WHERE user_id = ?',
        (user_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            'state': row[0],
            'target_username': row[1],
            'message_id': row[2]
        }
    return {}


def delete_session_data(user_id):
    """Удаляет данные сессии пользователя."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM sessions WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def get_setting(key, default=None):
    """Получает значение настройки по ключу."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default


def set_setting(key, value):
    """Сохраняет или обновляет значение настройки."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        '''
        INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)
        ''',
        (key, str(value))
    )
    conn.commit()
    conn.close()