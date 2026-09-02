"""Меню-бот для Telegram-канала.

Как это работает простыми словами:
пользователь нажимает кнопку в канале → открывается личный чат с ботом
→ бот показывает нужную тему. Админ командой публикует меню в канал.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    filters,
)
from telegram.helpers import create_deep_linked_url

# Читаем секреты из файла .env, чтобы токен не лежал в коде
load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Канал, куда бот публикует меню. Можно переопределить в .env
CHANNEL = os.getenv("CHANNEL", "@abmrab").strip()

# Один список тем: ключ, текст кнопки, текст страницы.
# Новую тему добавляешь только сюда — кнопки обновятся сами.
MENU_ITEMS: tuple[tuple[str, str, str], ...] = (
    (
        "nyheter",
        "📰 Nyheter",
        "<b>Nyheter</b>\n\nHär publiceras de senaste nyheterna och uppdateringarna.",
    ),
    (
        "aquatone",
        "💧 Aquatone",
        "<b>Aquatone</b>\n\nHär hittar du information, nyheter och material om Aquatone.",
    ),
    (
        "biotrem",
        "🔵 Biotrem",
        "<b>Biotrem</b>\n\nHär hittar du information, nyheter och material om Biotrem.",
    ),
    (
        "monicor",
        "🟢 Monicor",
        "<b>Monicor</b>\n\nHär hittar du information, nyheter och material om Monicor.",
    ),
    (
        "kvantresonans",
        "✨ Kvantresonans",
        "<b>Kvantresonans</b>\n\nHär hittar du information, nyheter och material om Kvantresonans.",
    ),
    (
        "rejuvination_club_100",
        "🌿 Rejuvination Club 100+",
        "<b>Rejuvination Club 100+</b>\n\nHär hittar du information, nyheter och material om Rejuvination Club 100+.",
    ),
)

CONTENT = {key: text for key, _label, text in MENU_ITEMS}
MENU_WELCOME = "<b>Välkommen!</b>\n\nVälj ett ämne:"
CHANNEL_MENU_TEXT = "<b>MENY</b>\n\nVälj ett ämne nedan:"
ADMIN_STATUSES = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}


def load_token() -> str:
    """Берём токен из переменной окружения, а не из исходника."""
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or token == "KLISTRA_IN_DIN_TOKEN_HAR":
        raise ValueError(
            "Сначала положи токен от @BotFather в файл .env как BOT_TOKEN=..."
        )
    return token


def main_menu() -> InlineKeyboardMarkup:
    """Кнопки внутри личного чата с ботом (переключают текст сообщения)."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(label, callback_data=key)]
            for key, label, _text in MENU_ITEMS
        ]
    )


def channel_menu(bot_username: str) -> InlineKeyboardMarkup:
    """Кнопки в канале: каждая открывает нужную тему в личке с ботом."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    label,
                    url=create_deep_linked_url(bot_username, key),
                )
            ]
            for key, label, _text in MENU_ITEMS
        ]
    )


def back_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Tillbaka till menyn", callback_data="menu")]]
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start и /menu. Если пришли по кнопке из канала — сразу нужная тема."""
    if update.message is None:
        return

    topic = context.args[0] if context.args else None
    if topic in CONTENT:
        await update.message.reply_text(
            CONTENT[topic],
            parse_mode=ParseMode.HTML,
            reply_markup=back_button(),
        )
        return

    if topic:
        logger.info("Неизвестная тема в deep-link: %s", topic)

    await update.message.reply_text(
        MENU_WELCOME,
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(),
    )


async def _is_channel_admin(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    member = await context.bot.get_chat_member(CHANNEL, user_id)
    return member.status in ADMIN_STATUSES


async def publish_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ канала публикует меню-пост и бот пытается его закрепить."""
    if update.message is None or update.effective_user is None:
        return

    try:
        if not await _is_channel_admin(context, update.effective_user.id):
            await update.message.reply_text(
                "Bara en administratör i kanalen kan publicera menyn."
            )
            return

        bot_info = await context.bot.get_me()
        if not bot_info.username:
            await update.message.reply_text(
                "Boten saknar användarnamn. Sätt ett hos @BotFather."
            )
            return

        sent = await context.bot.send_message(
            chat_id=CHANNEL,
            text=CHANNEL_MENU_TEXT,
            parse_mode=ParseMode.HTML,
            reply_markup=channel_menu(bot_info.username),
        )

        pinned = await _try_pin_menu(context, sent.message_id)
        if pinned:
            await update.message.reply_text(
                "Menyn är publicerad och fäst överst i kanalen."
            )
        else:
            await update.message.reply_text(
                "Menyn är publicerad i kanalen. Fäst gärna menyinlägget överst."
            )
        logger.info("Меню опубликовано, message_id=%s", sent.message_id)
    except Forbidden:
        await update.message.reply_text(
            "Boten får inte skriva i kanalen. Gör boten till administratör "
            "och tillåt att publicera och fästa inlägg."
        )
        logger.exception("Нет прав на публикацию в %s", CHANNEL)
    except TelegramError:
        await update.message.reply_text(
            "Menyn kunde inte publiceras. Kontrollera att boten är administratör "
            "i kanalen och får publicera och redigera inlägg."
        )
        logger.exception("Ошибка публикации меню в %s", CHANNEL)


async def _try_pin_menu(context: ContextTypes.DEFAULT_TYPE, message_id: int) -> bool:
    """Закрепляем пост, если у бота есть право pin. Иначе просто возвращаем False."""
    try:
        await context.bot.pin_chat_message(
            chat_id=CHANNEL,
            message_id=message_id,
            disable_notification=True,
        )
        return True
    except (Forbidden, BadRequest) as error:
        logger.warning("Не удалось закрепить меню: %s", error)
        return False


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Нажатие кнопки внутри личного чата: меняем текст того же сообщения."""
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()

    if query.data == "menu":
        await query.edit_message_text(
            MENU_WELCOME,
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )
        return

    if query.data in CONTENT:
        await query.edit_message_text(
            CONTENT[query.data],
            parse_mode=ParseMode.HTML,
            reply_markup=back_button(),
        )


def build_application(token: str) -> Application:
    """Собираем приложение и вешаем команды. Удобно тестировать без запуска сети."""
    app = ApplicationBuilder().token(token).build()
    private = filters.ChatType.PRIVATE
    app.add_handler(CommandHandler("start", start, filters=private))
    app.add_handler(CommandHandler("menu", start, filters=private))
    app.add_handler(CommandHandler("publicera_meny", publish_menu, filters=private))
    app.add_handler(CallbackQueryHandler(button_handler))
    return app


def main() -> None:
    token = load_token()
    app = build_application(token)
    logger.info("Бот запущен. Канал: %s. Остановка: Ctrl+C.", CHANNEL)
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
