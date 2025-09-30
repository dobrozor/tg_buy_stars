import time
import threading
from bot import logger

# Глобальная переменная для управления анимацией.
# Ее определение остается в bot.py, но лучше, если она будет передаваться или управляться классом.
# Для простоты, оставим ее глобальной, но будем импортировать.
# from bot import animation_running # <- Должен быть в bot.py

def animate_caption(bot, call):
    """Показывает анимацию 'Отправляю звезды...'."""
    from bot import animation_running # Локальный импорт, чтобы избежать циклической зависимости
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