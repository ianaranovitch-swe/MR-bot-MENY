"""Меню-бот для Telegram-канала.

Как это работает простыми словами:
на первом экране бот показывает шесть карточек подряд —
картинка и крупное название. По нажатию открывается текст темы.
"""

from __future__ import annotations

import html
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
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

# Рядом со скриптом лежит папка banners/. На Railway можно указать диск Volume.
_SCRIPT_DIR = Path(__file__).resolve().parent
CHANNEL = os.getenv("CHANNEL", "@abmrab").strip()

# Один список тем: ключ, кнопка, текст, имя файла-баннера.
# Новую тему добавляешь только сюда — карточки меню подхватятся сами.
MENU_ITEMS: tuple[tuple[str, str, str, str], ...] = (
    (
        "nyheter",
        "📰 Nyheter",
        "<b>Nyheter</b>\n\nHär publiceras de senaste nyheterna och uppdateringarna.",
        "nyheter.png",
    ),
    (
        "aquatone",
        "💧 Aquatone",
        "<b>Aquatone</b>\n\nHär hittar du information, nyheter och material om Aquatone.",
        "aquatone.png",
    ),
    (
        "biotrem",
        "🔵 Biotrem",
        "<b>Biotrem</b>\n\nHär hittar du information, nyheter och material om Biotrem.",
        "biotrem.png",
    ),
    (
        "monicor",
        "🟢 Monicor",
        "<b>Monicor</b>\n\nHär hittar du information, nyheter och material om Monicor.",
        "monicor.png",
    ),
    (
        "kvantresonans",
        "✨ Kvantresonans",
        "<b>Kvantresonans</b>\n\nHär hittar du information, nyheter och material om Kvantresonans.",
        "kvantresonans.png",
    ),
    (
        "longevity_club_100",
        "🌿 Longevity Club 100+",
        "<b>Longevity Club 100+</b>\n\nHär hittar du information, nyheter och material om Longevity Club 100+.",
        "longevity_club_100.png",
    ),
)

CONTENT = {key: text for key, _label, text, _banner in MENU_ITEMS}
BANNER_FILES = {key: banner for key, _label, _text, banner in MENU_ITEMS}
CHANNEL_MENU_TEXT = "<b>MENY</b>\n\nVälj ett ämne nedan:"
ADMIN_STATUSES = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}
_BANNER_FILE_IDS_KEY = "banner_file_ids"
_MENU_MESSAGE_IDS_KEY = "menu_message_ids"


def load_token() -> str:
    """Берём токен из переменной окружения, а не из исходника."""
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or token == "KLISTRA_IN_DIN_TOKEN_HAR":
        raise ValueError(
            "Сначала положи токен от @BotFather в файл .env как BOT_TOKEN=..."
        )
    return token


def banners_dir() -> Path:
    """Папка с картинками рядом со скриптом.

    Абсолютный BANNERS_DIR (например /data/banners на Railway) берём как есть.
    Относительный путь всегда от папки скрипта, а не от текущей рабочей папки.
    """
    raw = os.getenv("BANNERS_DIR", "").strip()
    if not raw:
        return _SCRIPT_DIR / "banners"
    path = Path(raw)
    if path.is_absolute():
        return path
    return _SCRIPT_DIR / path


def banner_path(key: str) -> Path | None:
    """Путь к баннеру, если файл лежит на диске. Иначе None — покажем только текст."""
    filename = BANNER_FILES.get(key)
    if not filename:
        return None
    path = banners_dir() / filename
    if path.is_file():
        return path
    return None


def log_banner_status() -> None:
    found = [key for key, *_rest in MENU_ITEMS if banner_path(key)]
    missing = [key for key, *_rest in MENU_ITEMS if banner_path(key) is None]
    logger.info("Папка баннеров: %s", banners_dir())
    logger.info("Баннеры найдены: %s", ", ".join(found) if found else "нет")
    if missing:
        logger.warning("Баннеры отсутствуют, будет только текст: %s", ", ".join(missing))


def topic_title(label: str) -> str:
    """Из «📰 Nyheter» берём крупное имя темы: Nyheter."""
    parts = label.split(" ", 1)
    return parts[1] if len(parts) > 1 else label


def menu_card_caption(label: str) -> str:
    """Крупный заголовок под картинкой на первом экране."""
    return f"<b>{html.escape(topic_title(label))}</b>"


def topic_card_markup(key: str, label: str) -> InlineKeyboardMarkup:
    """Одна кнопка на карточке меню — это пункт меню."""
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=key)]])


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
            for key, label, _text, _banner in MENU_ITEMS
        ]
    )


def back_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Tillbaka till menyn", callback_data="menu")]]
    )


def _cached_file_id(context: ContextTypes.DEFAULT_TYPE, key: str) -> str | None:
    cache = context.application.bot_data.setdefault(_BANNER_FILE_IDS_KEY, {})
    file_id = cache.get(key)
    return file_id if isinstance(file_id, str) else None


def _remember_file_id(
    context: ContextTypes.DEFAULT_TYPE, key: str, message: Message
) -> None:
    """Telegram запоминает картинку. Второй раз шлём номер, а не файл заново."""
    if not message.photo:
        return
    cache = context.application.bot_data.setdefault(_BANNER_FILE_IDS_KEY, {})
    cache[key] = message.photo[-1].file_id


async def _try_delete_message(message: Message) -> None:
    try:
        await message.delete()
    except (BadRequest, Forbidden, TelegramError) as error:
        logger.info("Не удалось удалить старое сообщение: %s", error)


async def _delete_menu_messages(
    bot: Bot, chat_id: int, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Убираем старые карточки, чтобы меню не копилось в чате."""
    raw_ids = context.user_data.get(_MENU_MESSAGE_IDS_KEY, [])
    message_ids = [item for item in raw_ids if isinstance(item, int)]
    for message_id in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except (BadRequest, Forbidden, TelegramError) as error:
            logger.info("Не удалось удалить карточку меню %s: %s", message_id, error)
    context.user_data[_MENU_MESSAGE_IDS_KEY] = []


async def _send_menu_card(
    *,
    bot: Bot,
    chat_id: int,
    key: str,
    label: str,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Одна карточка: баннер + крупное название + кнопка пункта меню."""
    caption = menu_card_caption(label)
    markup = topic_card_markup(key, label)
    photo = _cached_file_id(context, key) or banner_path(key)

    if photo is not None:
        try:
            sent = await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
                disable_notification=True,
            )
            _remember_file_id(context, key, sent)
            return sent.message_id
        except TelegramError:
            logger.exception("Не удалось отправить баннер меню %s, шлём текст", key)

    sent = await bot.send_message(
        chat_id=chat_id,
        text=caption,
        parse_mode=ParseMode.HTML,
        reply_markup=markup,
        disable_notification=True,
    )
    return sent.message_id


async def _send_menu_gallery(
    *,
    bot: Bot,
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Первый экран: шесть картинок подряд, как витрина."""
    await _delete_menu_messages(bot, chat_id, context)
    sent_ids: list[int] = []
    for key, label, _text, _banner in MENU_ITEMS:
        sent_ids.append(
            await _send_menu_card(
                bot=bot,
                chat_id=chat_id,
                key=key,
                label=label,
                context=context,
            )
        )
    context.user_data[_MENU_MESSAGE_IDS_KEY] = sent_ids


async def _send_topic(
    *,
    bot: Bot,
    chat_id: int,
    topic: str,
    reply_to: Message | None = None,
) -> None:
    """После нажатия пункта — только текст темы, без повторного баннера."""
    text = CONTENT[topic]
    markup = back_button()
    if reply_to is not None:
        await reply_to.reply_text(
            text, parse_mode=ParseMode.HTML, reply_markup=markup
        )
        return
    await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=markup,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start и /menu. Без аргументов — витрина из баннеров."""
    if update.message is None:
        return

    topic = context.args[0] if context.args else None
    if topic in CONTENT:
        await _send_topic(
            bot=context.bot,
            chat_id=update.message.chat_id,
            topic=topic,
            reply_to=update.message,
        )
        return

    if topic:
        logger.info("Неизвестная тема в deep-link: %s", topic)

    await _send_menu_gallery(
        bot=context.bot,
        chat_id=update.message.chat_id,
        context=context,
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
    """Кнопка на карточке открывает текст. Назад снова рисует витрину."""
    query = update.callback_query
    if query is None or query.data is None or query.message is None:
        return

    await query.answer()
    chat_id = query.message.chat_id

    if query.data == "menu":
        await _try_delete_message(query.message)
        await _send_menu_gallery(
            bot=context.bot, chat_id=chat_id, context=context
        )
        return

    if query.data in CONTENT:
        await _delete_menu_messages(context.bot, chat_id, context)
        await _try_delete_message(query.message)
        await _send_topic(
            bot=context.bot,
            chat_id=chat_id,
            topic=query.data,
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
    log_banner_status()
    app = build_application(token)
    logger.info("Бот запущен. Канал: %s. Остановка: Ctrl+C.", CHANNEL)
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
