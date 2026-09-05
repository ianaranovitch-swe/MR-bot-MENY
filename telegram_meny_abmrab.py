"""Меню-бот для Telegram-канала.

Как это работает простыми словами:
на первом экране — шесть карточек с баннерами.
Текст, фото и ссылки рубрики админ меняет командой /redigera.
Баннеры из папки banners/ при этом не трогаем.

Канал: @abmrab
Бот: @MRAB_SWE_bot
"""

from __future__ import annotations

import html
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
    Update,
)
from telegram.constants import ChatMemberStatus, MessageLimit, ParseMode
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.helpers import create_deep_linked_url

import db

# Читаем секреты из файла .env, чтобы токен не лежал в коде
load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

_SCRIPT_DIR = Path(__file__).resolve().parent
CHANNEL = os.getenv("CHANNEL", "@abmrab").strip()
EXPECTED_BOT_USERNAME = "MRAB_SWE_bot"

# Один список тем: ключ, кнопка, текст по умолчанию, имя файла-баннера.
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

DEFAULT_CONTENT = {key: text for key, _label, text, _banner in MENU_ITEMS}
CONTENT = DEFAULT_CONTENT
TOPIC_KEYS = set(DEFAULT_CONTENT)
TOPIC_LABELS = {key: label for key, label, _text, _banner in MENU_ITEMS}
BANNER_FILES = {key: banner for key, _label, _text, banner in MENU_ITEMS}
CHANNEL_MENU_TEXT = "<b>MENY</b>\n\nVälj ett ämne nedan:"
ADMIN_STATUSES = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}
_BANNER_FILE_IDS_KEY = "banner_file_ids"
_MENU_MESSAGE_IDS_KEY = "menu_message_ids"
_VIEW_IDS_BY_USER_KEY = "view_message_ids_by_user"
_CONTENT_CACHE_KEY = "content_cache"
_PHOTOS_CACHE_KEY = "photos_cache"
_LINKS_CACHE_KEY = "links_cache"
_FRESHNESS_CACHE_KEY = "freshness_cache"
_STEP_PROMPT_ID_KEY = "step_prompt_id"
NEW_MARK_TTL = timedelta(days=2)
_ADMIN_LINK_CALLBACKS = {
    "cancel_edit",
    "done_photos",
    "skip_photos",
    "done_links",
    "skip_links",
    "publish_channel",
    "no_publish",
}


def parse_admin_ids(raw: str | None = None) -> set[int]:
    """ADMIN_IDS=111,222 → множество чисел."""
    value = raw if raw is not None else os.getenv("ADMIN_IDS", "")
    ids: set[int] = set()
    for part in value.split(","):
        piece = part.strip()
        if piece.lstrip("-").isdigit():
            ids.add(int(piece))
    return ids


def is_admin(user_id: int) -> bool:
    return user_id in parse_admin_ids()


@dataclass(frozen=True)
class ChannelLinkStatus:
    """Связка бота с каналом: что уже есть и чего не хватает."""

    channel: str
    bot_username: str | None
    channel_title: str | None
    bot_status: str | None
    can_post: bool
    can_pin: bool
    error: str | None


def _member_can_post(member: object) -> bool:
    status = getattr(member, "status", None)
    if status == ChatMemberStatus.OWNER:
        return True
    return bool(getattr(member, "can_post_messages", False))


def _member_can_pin(member: object) -> bool:
    status = getattr(member, "status", None)
    if status == ChatMemberStatus.OWNER:
        return True
    return bool(getattr(member, "can_pin_messages", False))


def format_channel_link_report(status: ChannelLinkStatus) -> str:
    """Текст для человека: канал и бот связаны или нет."""
    bot_name = f"@{status.bot_username}" if status.bot_username else "@?"
    lines = [
        f"Kanal: {status.channel}",
        f"Bot: {bot_name}",
    ]
    if status.error:
        lines.append(f"Koppling: inte klar. {status.error}")
        lines.append(
            f"Gör så här i Telegram: öppna {status.channel} → "
            "Administrators → Add Administrator → "
            f"@{EXPECTED_BOT_USERNAME}. "
            "Slå på Post Messages, Edit Messages och Pin Messages. "
            "Sedan skriv /publicera_meny här."
        )
        return "\n".join(lines)

    lines.append(f"Kanalens namn: {status.channel_title or '?'}")
    lines.append(f"Botens roll: {status.bot_status or '?'}")
    lines.append(f"Kan publicera: {'ja' if status.can_post else 'nej'}")
    lines.append(f"Kan fästa: {'ja' if status.can_pin else 'nej'}")
    if status.can_post:
        lines.append("Kopplingen är klar. Skriv /publicera_meny för att lägga menyn i kanalen.")
    else:
        lines.append(
            "Boten syns i kanalen men får inte publicera. "
            "Slå på Post Messages för "
            f"@{EXPECTED_BOT_USERNAME} i {status.channel}."
        )
    return "\n".join(lines)


async def inspect_channel_link(bot: Bot) -> ChannelLinkStatus:
    """Спрашиваем Telegram: видит ли бот канал и может ли туда писать."""
    me = await bot.get_me()
    username = me.username
    try:
        chat = await bot.get_chat(CHANNEL)
        member = await bot.get_chat_member(CHANNEL, me.id)
    except Forbidden:
        return ChannelLinkStatus(
            channel=CHANNEL,
            bot_username=username,
            channel_title=None,
            bot_status=None,
            can_post=False,
            can_pin=False,
            error="boten är inte administratör i kanalen ännu",
        )
    except (BadRequest, TelegramError) as error:
        logger.info("Проверка канала %s не удалась: %s", CHANNEL, error)
        return ChannelLinkStatus(
            channel=CHANNEL,
            bot_username=username,
            channel_title=None,
            bot_status=None,
            can_post=False,
            can_pin=False,
            error="boten når inte kanalen ännu",
        )
    return ChannelLinkStatus(
        channel=CHANNEL,
        bot_username=username,
        channel_title=getattr(chat, "title", None),
        bot_status=str(getattr(member, "status", "")),
        can_post=_member_can_post(member),
        can_pin=_member_can_pin(member),
        error=None,
    )


def normalize_url(raw: str) -> str | None:
    """Если это ссылка — вернём нормальный адрес. Иначе None."""
    candidate = raw.strip()
    if not candidate or " " in candidate:
        return None
    if not candidate.startswith(("http://", "https://")):
        candidate = "https://" + candidate
    parsed = urlparse(candidate)
    host = parsed.netloc.lower()
    if parsed.scheme not in {"http", "https"} or not host:
        return None
    if "." not in host and host != "localhost":
        return None
    return candidate


def link_button_label(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host in {"youtu.be", "youtube.com"} or host.endswith(".youtube.com"):
        return "▶️ Titta på YouTube"
    return "🔗 Läs mer"


def load_token() -> str:
    """Берём токен из переменной окружения, а не из исходника."""
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or token == "KLISTRA_IN_DIN_TOKEN_HAR":
        raise ValueError(
            "Сначала положи токен от @BotFather в файл .env как BOT_TOKEN=..."
        )
    return token


def banners_dir() -> Path:
    """Папка с картинками рядом со скриптом."""
    raw = os.getenv("BANNERS_DIR", "").strip()
    if not raw:
        return _SCRIPT_DIR / "banners"
    path = Path(raw)
    if path.is_absolute():
        return path
    return _SCRIPT_DIR / path


def banner_path(key: str) -> Path | None:
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
    parts = label.split(" ", 1)
    return parts[1] if len(parts) > 1 else label


def topic_display_name(key: str) -> str:
    return topic_title(TOPIC_LABELS.get(key, key))


def remaining_menu_items(selected_key: str) -> tuple[tuple[str, str, str, str], ...]:
    """Остальные рубрики меню — без той, которую уже открыли."""
    return tuple(item for item in MENU_ITEMS if item[0] != selected_key)


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def is_topic_new(context: ContextTypes.DEFAULT_TYPE, key: str) -> bool:
    """🆕 только у той рубрики, где админ менял текст, фото или ссылки."""
    cache = context.application.bot_data.get(_FRESHNESS_CACHE_KEY, {})
    if not isinstance(cache, dict):
        return False
    last = cache.get(key)
    if not isinstance(last, datetime):
        return False
    return datetime.now(timezone.utc) - _as_utc(last) <= NEW_MARK_TTL


def _touch_freshness(context: ContextTypes.DEFAULT_TYPE, key: str) -> None:
    cache = context.application.bot_data.setdefault(_FRESHNESS_CACHE_KEY, {})
    if isinstance(cache, dict):
        cache[key] = datetime.now(timezone.utc)


def menu_card_caption(label: str, is_new: bool = False) -> str:
    title = topic_title(label)
    if is_new:
        return f"<b>🆕 {html.escape(title)}</b>"
    return f"<b>{html.escape(title)}</b>"


def topic_card_markup(
    key: str, label: str, is_new: bool = False
) -> InlineKeyboardMarkup:
    text = f"🆕 {label}" if is_new else label
    return InlineKeyboardMarkup([[InlineKeyboardButton(text, callback_data=key)]])


def redigera_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(label, callback_data=f"edit_{key}")]
        for key, label, _text, _banner in MENU_ITEMS
    ]
    rows.append([InlineKeyboardButton("❌ Avbryt", callback_data="cancel_edit")])
    return InlineKeyboardMarkup(rows)


def cancel_edit_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Avbryt", callback_data="cancel_edit")]]
    )


def photo_step_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Klar", callback_data="done_photos"),
                InlineKeyboardButton("⏭️ Hoppa över", callback_data="skip_photos"),
            ]
        ]
    )


def link_step_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Klar", callback_data="done_links"),
                InlineKeyboardButton("⏭️ Hoppa över", callback_data="skip_links"),
            ]
        ]
    )


def publish_offer_text(photo_count: int, link_count: int) -> str:
    """Вопрос после сохранения: публиковать ли то же обновление в канал."""
    return (
        f"✅ Innehållet är sparat i boten (text, {photo_count} nya foto, "
        f"{link_count} nya länkar). Vill du också publicera det som ett "
        f"nytt inlägg i kanalen {CHANNEL}?"
    )


def publish_offer_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📢 Publicera i kanalen", callback_data="publish_channel"
                )
            ],
            [
                InlineKeyboardButton(
                    "🚫 Publicera inte nu", callback_data="no_publish"
                )
            ],
        ]
    )


def channel_update_caption(label: str, session_text: str) -> str:
    """Заголовок поста в канале + уже готовый HTML-текст рубрики."""
    return f"🆕 <b>{html.escape(label)}</b>\n\n{session_text}"


def session_photo_ids(context: ContextTypes.DEFAULT_TYPE) -> list[str]:
    raw = context.user_data.get("photo_buffer") or []
    return [item for item in raw if isinstance(item, str)]


def session_link_items(context: ContextTypes.DEFAULT_TYPE) -> list[tuple[str, str]]:
    raw = context.user_data.get("link_buffer") or []
    items: list[tuple[str, str]] = []
    for item in raw:
        if isinstance(item, tuple) and len(item) == 2:
            items.append((str(item[0]), str(item[1])))
    return items


def session_link_markup(items: list[tuple[str, str]]) -> InlineKeyboardMarkup | None:
    """Кнопки только для ссылок этой сессии — старые ссылки меню сюда не кладём."""
    if not items:
        return None
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, url=url)] for url, label in items]
    )


def channel_menu(bot_username: str) -> InlineKeyboardMarkup:
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


def topic_keyboard(
    context: ContextTypes.DEFAULT_TYPE, key: str
) -> InlineKeyboardMarkup:
    """Ссылки рубрики сверху, «назад» всегда последней строкой."""
    rows = [
        [InlineKeyboardButton(label, url=url)]
        for url, label in topic_links(context, key)
    ]
    rows.append([InlineKeyboardButton("⬅️ Tillbaka till menyn", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def topic_text(context: ContextTypes.DEFAULT_TYPE, key: str) -> str:
    cache = context.application.bot_data.get(_CONTENT_CACHE_KEY, DEFAULT_CONTENT)
    if isinstance(cache, dict) and key in cache:
        return str(cache[key])
    return DEFAULT_CONTENT.get(key, "")


def topic_photo_ids(context: ContextTypes.DEFAULT_TYPE, key: str) -> list[str]:
    cache = context.application.bot_data.get(_PHOTOS_CACHE_KEY, {})
    if not isinstance(cache, dict):
        return []
    raw = cache.get(key, [])
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str)]


def topic_links(context: ContextTypes.DEFAULT_TYPE, key: str) -> list[tuple[str, str]]:
    cache = context.application.bot_data.get(_LINKS_CACHE_KEY, {})
    if not isinstance(cache, dict):
        return []
    raw = cache.get(key, [])
    if not isinstance(raw, list):
        return []
    links: list[tuple[str, str]] = []
    for item in raw:
        if isinstance(item, tuple) and len(item) == 2:
            links.append((str(item[0]), str(item[1])))
    return links


def _update_content_cache(
    context: ContextTypes.DEFAULT_TYPE, key: str, text: str
) -> None:
    cache = context.application.bot_data.setdefault(_CONTENT_CACHE_KEY, dict(DEFAULT_CONTENT))
    if isinstance(cache, dict):
        cache[key] = text


def _update_photos_cache(
    context: ContextTypes.DEFAULT_TYPE, key: str, file_ids: list[str]
) -> None:
    cache = context.application.bot_data.setdefault(_PHOTOS_CACHE_KEY, {})
    if isinstance(cache, dict):
        cache[key] = list(file_ids)


def _append_links_cache(
    context: ContextTypes.DEFAULT_TYPE, key: str, items: list[tuple[str, str]]
) -> None:
    cache = context.application.bot_data.setdefault(_LINKS_CACHE_KEY, {})
    if not isinstance(cache, dict):
        return
    existing = cache.get(key, [])
    if not isinstance(existing, list):
        existing = []
    existing.extend(items)
    cache[key] = existing


def _db_pool(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data.get("db")


def merge_message_ids(*groups: object) -> list[int]:
    """Склеиваем номера сообщений без повторов — как список игрушек в одну коробку."""
    seen: set[int] = set()
    result: list[int] = []
    for group in groups:
        if isinstance(group, int):
            items: list[object] = [group]
        elif isinstance(group, (list, tuple)):
            items = list(group)
        else:
            continue
        for item in items:
            if isinstance(item, int) and item not in seen:
                seen.add(item)
                result.append(item)
    return result


def _context_user_id(context: ContextTypes.DEFAULT_TYPE) -> int | None:
    user_id = getattr(context, "_user_id", None)
    return user_id if isinstance(user_id, int) else None


def _load_view_ids(context: ContextTypes.DEFAULT_TYPE) -> list[int]:
    user_id = _context_user_id(context)
    from_user = context.user_data.get(_MENU_MESSAGE_IDS_KEY)
    from_bot: object = []
    if user_id is not None:
        store = context.application.bot_data.setdefault(_VIEW_IDS_BY_USER_KEY, {})
        if isinstance(store, dict):
            from_bot = store.get(user_id, [])
    return merge_message_ids(from_user, from_bot)


def _save_view_ids(context: ContextTypes.DEFAULT_TYPE, message_ids: list[int]) -> None:
    ids = merge_message_ids(message_ids)
    context.user_data[_MENU_MESSAGE_IDS_KEY] = ids
    user_id = _context_user_id(context)
    if user_id is None:
        return
    store = context.application.bot_data.setdefault(_VIEW_IDS_BY_USER_KEY, {})
    if isinstance(store, dict):
        store[user_id] = ids


def _track_view_id(context: ContextTypes.DEFAULT_TYPE, message_id: int) -> None:
    _save_view_ids(context, [*_load_view_ids(context), message_id])


def _cached_file_id(context: ContextTypes.DEFAULT_TYPE, key: str) -> str | None:
    cache = context.application.bot_data.setdefault(_BANNER_FILE_IDS_KEY, {})
    file_id = cache.get(key)
    return file_id if isinstance(file_id, str) else None


def _remember_file_id(
    context: ContextTypes.DEFAULT_TYPE, key: str, message: Message
) -> None:
    if not message.photo:
        return
    cache = context.application.bot_data.setdefault(_BANNER_FILE_IDS_KEY, {})
    cache[key] = message.photo[-1].file_id


async def _delete_menu_messages(
    bot: Bot,
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    extra_ids: list[int] | None = None,
) -> None:
    """Стираем прошлый экран: старые баннеры и открытую рубрику."""
    message_ids = merge_message_ids(_load_view_ids(context), extra_ids or [])
    if message_ids:
        try:
            await bot.delete_messages(chat_id=chat_id, message_ids=message_ids)
        except (AttributeError, BadRequest, Forbidden, TelegramError):
            for message_id in message_ids:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=message_id)
                except (BadRequest, Forbidden, TelegramError) as error:
                    logger.info(
                        "Не удалось удалить карточку меню %s: %s", message_id, error
                    )
    _save_view_ids(context, [])


async def _send_menu_card(
    *,
    bot: Bot,
    chat_id: int,
    key: str,
    label: str,
    context: ContextTypes.DEFAULT_TYPE,
    track: bool = True,
) -> int:
    is_new = is_topic_new(context, key)
    caption = menu_card_caption(label, is_new)
    markup = topic_card_markup(key, label, is_new)
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
            if track:
                _track_view_id(context, sent.message_id)
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
    if track:
        _track_view_id(context, sent.message_id)
    return sent.message_id


async def _send_menu_gallery(
    *,
    bot: Bot,
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    exclude_key: str | None = None,
    replace_view: bool = True,
    extra_delete_ids: list[int] | None = None,
    track: bool = True,
) -> list[int]:
    if replace_view:
        await _delete_menu_messages(
            bot, chat_id, context, extra_ids=extra_delete_ids
        )
    sent_ids: list[int] = []
    items = remaining_menu_items(exclude_key) if exclude_key else MENU_ITEMS
    for key, label, _text, _banner in items:
        sent_ids.append(
            await _send_menu_card(
                bot=bot,
                chat_id=chat_id,
                key=key,
                label=label,
                context=context,
                track=track,
            )
        )
    return sent_ids


async def _send_topic_banner(
    *,
    bot: Bot,
    chat_id: int,
    key: str,
    context: ContextTypes.DEFAULT_TYPE,
    track: bool = True,
) -> int:
    """Баннер открытой рубрики: картинка сверху, без кнопки (её уже нажали)."""
    label = TOPIC_LABELS.get(key, key)
    caption = menu_card_caption(label, is_topic_new(context, key))
    photo = _cached_file_id(context, key) or banner_path(key)

    if photo is not None:
        try:
            sent = await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                parse_mode=ParseMode.HTML,
                disable_notification=True,
            )
            _remember_file_id(context, key, sent)
            if track:
                _track_view_id(context, sent.message_id)
            return sent.message_id
        except TelegramError:
            logger.exception("Не удалось отправить баннер рубрики %s, шлём текст", key)

    sent = await bot.send_message(
        chat_id=chat_id,
        text=caption,
        parse_mode=ParseMode.HTML,
        disable_notification=True,
    )
    if track:
        _track_view_id(context, sent.message_id)
    return sent.message_id


async def _send_topic_photos(
    bot: Bot,
    chat_id: int,
    topic: str,
    context: ContextTypes.DEFAULT_TYPE,
    track: bool = True,
) -> list[int]:
    """Доп.фото рубрики — не баннеры. Одно фото отдельно, много — пачками по 10."""
    file_ids = topic_photo_ids(context, topic)
    if not file_ids:
        return []
    sent_ids: list[int] = []
    try:
        if len(file_ids) == 1:
            sent = await bot.send_photo(chat_id=chat_id, photo=file_ids[0])
            if track:
                _track_view_id(context, sent.message_id)
            return [sent.message_id]
        for chunk in db.chunk_ids(file_ids, 10):
            if len(chunk) == 1:
                sent = await bot.send_photo(chat_id=chat_id, photo=chunk[0])
                sent_ids.append(sent.message_id)
            else:
                messages = await bot.send_media_group(
                    chat_id=chat_id,
                    media=[InputMediaPhoto(file_id) for file_id in chunk],
                )
                sent_ids.extend(message.message_id for message in messages)
    except TelegramError:
        logger.exception("Не удалось отправить фото рубрики %s", topic)
    if track:
        for message_id in sent_ids:
            _track_view_id(context, message_id)
    return sent_ids


async def _send_topic(
    *,
    bot: Bot,
    chat_id: int,
    topic: str,
    context: ContextTypes.DEFAULT_TYPE,
    include_remaining_menu: bool = True,
    track_view: bool = True,
    extra_delete_ids: list[int] | None = None,
) -> None:
    """Сначала баннер темы, потом её текст и фото, потом остальные карточки меню."""
    if track_view:
        await _delete_menu_messages(
            bot, chat_id, context, extra_ids=extra_delete_ids
        )

    await _send_topic_banner(
        bot=bot,
        chat_id=chat_id,
        key=topic,
        context=context,
        track=track_view,
    )
    text = await bot.send_message(
        chat_id=chat_id,
        text=topic_text(context, topic),
        parse_mode=ParseMode.HTML,
        reply_markup=topic_keyboard(context, topic),
    )
    if track_view:
        _track_view_id(context, text.message_id)
    await _send_topic_photos(
        bot, chat_id, topic, context, track=track_view
    )

    if include_remaining_menu:
        await _send_menu_gallery(
            bot=bot,
            chat_id=chat_id,
            context=context,
            exclude_key=topic,
            replace_view=False,
            track=track_view,
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    topic = context.args[0] if context.args else None
    if topic in TOPIC_KEYS:
        await _send_topic(
            bot=context.bot,
            chat_id=update.message.chat_id,
            topic=topic,
            context=context,
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


async def check_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ видит, связана ли личка бота с каналом @abmrab."""
    if update.message is None or update.effective_user is None:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Du har inte behörighet.")
        return
    status = await inspect_channel_link(context.bot)
    await update.message.reply_text(format_channel_link_report(status))


async def publish_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    try:
        link = await inspect_channel_link(context.bot)
        if not link.can_post:
            await update.message.reply_text(format_channel_link_report(link))
            return

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
            f"Boten @{EXPECTED_BOT_USERNAME} får inte skriva i {CHANNEL}. "
            "Gör boten till administratör och tillåt att publicera och fästa inlägg."
        )
        logger.exception("Нет прав на публикацию в %s", CHANNEL)
    except TelegramError:
        await update.message.reply_text(
            f"Menyn kunde inte publiceras i {CHANNEL}. "
            f"Kontrollera att @{EXPECTED_BOT_USERNAME} är administratör "
            "och får publicera och redigera inlägg."
        )
        logger.exception("Ошибка публикации меню в %s", CHANNEL)


async def _try_pin_menu(context: ContextTypes.DEFAULT_TYPE, message_id: int) -> bool:
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


async def redigera(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ выбирает рубрику и пишет новый текст обычным Telegram-форматированием."""
    if update.message is None or update.effective_user is None:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Du har inte behörighet.")
        return
    await update.message.reply_text(
        "Välj en rubrik att redigera:",
        reply_markup=redigera_menu(),
    )


async def _show_redigera_menu_on_query(query) -> None:
    await query.edit_message_text(
        "Välj en rubrik att redigera:",
        reply_markup=redigera_menu(),
    )


async def _forget_step_prompt(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data[_STEP_PROMPT_ID_KEY] = None


async def _delete_step_prompt(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int
) -> None:
    """Убираем старые Klar-кнопки, чтобы не искать их вверх по чату."""
    old_id = context.user_data.get(_STEP_PROMPT_ID_KEY)
    if isinstance(old_id, int):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=old_id)
        except (BadRequest, Forbidden, TelegramError):
            pass
    await _forget_step_prompt(context)


async def _send_step_prompt(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    markup: InlineKeyboardMarkup,
) -> None:
    """Новое сообщение с Klar/Hoppa över всегда внизу чата."""
    await _delete_step_prompt(context, chat_id)
    sent = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=markup,
    )
    context.user_data[_STEP_PROMPT_ID_KEY] = sent.message_id


async def _show_topic_preview(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, key: str
) -> None:
    """Показать админу результат сразу. Перезапуск бота не нужен — кэш уже обновлён."""
    await context.bot.send_message(
        chat_id=chat_id,
        text="Så här ser rubriken ut nu:",
    )
    await _send_topic(
        bot=context.bot,
        chat_id=chat_id,
        topic=key,
        context=context,
        include_remaining_menu=False,
        track_view=False,
    )


async def _start_photo_step(
    context: ContextTypes.DEFAULT_TYPE, key: str, message: Message
) -> None:
    context.user_data["awaiting_edit"] = None
    context.user_data["awaiting_photos"] = key
    context.user_data["photo_buffer"] = []
    context.user_data["awaiting_links"] = None
    context.user_data["link_buffer"] = []
    await _send_step_prompt(
        context,
        message.chat_id,
        "✅ Texten är sparad. Skicka nu ett eller flera foton att bifoga "
        "innehållet — ett i taget. Tryck ✅ Klar när du är färdig.",
        photo_step_markup(),
    )


async def handle_admin_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.message is None or update.effective_user is None:
        return
    if not is_admin(update.effective_user.id):
        return
    if context.user_data.get("awaiting_links"):
        await _collect_admin_link(update, context)
        return
    if context.user_data.get("awaiting_photos"):
        await _send_step_prompt(
            context,
            update.message.chat_id,
            "Skicka ett foto eller tryck ✅ Klar / ⏭️ Hoppa över.",
            photo_step_markup(),
        )
        return
    key = context.user_data.get("awaiting_edit")
    if not isinstance(key, str) or key not in TOPIC_KEYS:
        return

    new_text = update.message.text_html or html.escape(update.message.text or "")
    if not new_text.strip():
        await update.message.reply_text("Texten är tom. Skicka texten igen.")
        return

    pool = _db_pool(context)
    if pool is None:
        await update.message.reply_text("Databasen är inte redo. Försök igen senare.")
        return

    title = topic_display_name(key)
    await db.upsert_content(pool, key, new_text, update.effective_user.id)
    _update_content_cache(context, key, new_text)
    _touch_freshness(context, key)
    context.user_data["session_key"] = key
    context.user_data["session_text"] = new_text
    await update.message.reply_text(f"✅ Innehållet för {title} är uppdaterat.")
    await update.message.reply_html(new_text)
    await _start_photo_step(context, key, update.message)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    if not is_admin(update.effective_user.id):
        return
    if not context.user_data.get("awaiting_photos"):
        return
    if not update.message.photo:
        return

    buffer = context.user_data.setdefault("photo_buffer", [])
    if not isinstance(buffer, list):
        buffer = []
        context.user_data["photo_buffer"] = buffer
    buffer.append(update.message.photo[-1].file_id)
    await _send_step_prompt(
        context,
        update.message.chat_id,
        f"📷 Foto mottaget ({len(buffer)} st hittills). "
        "Skicka fler eller tryck ✅ Klar / ⏭️ Hoppa över.",
        photo_step_markup(),
    )


def _clear_photo_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["awaiting_photos"] = None
    context.user_data["photo_buffer"] = []


def _clear_link_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["awaiting_links"] = None
    context.user_data["link_buffer"] = []


def _clear_edit_session(context: ContextTypes.DEFAULT_TYPE) -> None:
    """После публикации или отказа стираем всю сессию правки."""
    context.user_data["awaiting_edit"] = None
    context.user_data["session_key"] = None
    context.user_data["session_text"] = None
    _clear_photo_state(context)
    _clear_link_state(context)


async def _start_link_step(
    context: ContextTypes.DEFAULT_TYPE, key: str, message: Message
) -> None:
    # Фото этой сессии оставляем: они ещё понадобятся для поста в канал.
    context.user_data["awaiting_photos"] = None
    context.user_data["awaiting_links"] = key
    context.user_data["link_buffer"] = []
    await _send_step_prompt(
        context,
        message.chat_id,
        "🔗 Vill du lägga till länkar (t.ex. till YouTube)? "
        "Skicka en länk i taget. Tryck ✅ Klar när du är färdig.",
        link_step_markup(),
    )


async def _collect_admin_link(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.message is None:
        return
    raw = (update.message.text or "").strip()
    url = normalize_url(raw)
    if url is None:
        await _send_step_prompt(
            context,
            update.message.chat_id,
            "Det där ser inte ut som en länk. Försök igen eller tryck ✅ Klar.",
            link_step_markup(),
        )
        return
    buffer = context.user_data.setdefault("link_buffer", [])
    if not isinstance(buffer, list):
        buffer = []
        context.user_data["link_buffer"] = buffer
    buffer.append((url, link_button_label(url)))
    await _send_step_prompt(
        context,
        update.message.chat_id,
        f"🔗 Länk mottagen ({len(buffer)} st hittills). "
        "Skicka fler eller tryck ✅ Klar / ⏭️ Hoppa över.",
        link_step_markup(),
    )


async def _handle_done_photos(
    query, context: ContextTypes.DEFAULT_TYPE, user_id: int
) -> None:
    key = context.user_data.get("awaiting_photos")
    buffer = context.user_data.get("photo_buffer") or []
    file_ids = [item for item in buffer if isinstance(item, str)]
    if not isinstance(key, str) or key not in TOPIC_KEYS:
        _clear_edit_session(context)
        await _forget_step_prompt(context)
        await query.edit_message_text("Redigeringen är avbruten.")
        return

    title = topic_display_name(key)
    if not file_ids:
        context.user_data["photo_buffer"] = []
        await _forget_step_prompt(context)
        await query.edit_message_text(
            "Inga foton sparades — innehållet är oförändrat vad gäller bilder."
        )
        await _start_link_step(context, key, query.message)
        return

    pool = _db_pool(context)
    if pool is None:
        await _forget_step_prompt(context)
        await query.edit_message_text("Databasen är inte redo. Försök igen senare.")
        return

    await db.replace_photos(pool, key, file_ids, user_id)
    _update_photos_cache(context, key, file_ids)
    _touch_freshness(context, key)
    await _forget_step_prompt(context)
    await query.edit_message_text(f"✅ {len(file_ids)} foto sparade för {title}.")
    await _start_link_step(context, key, query.message)


async def _handle_skip_photos(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    key = context.user_data.get("awaiting_photos")
    context.user_data["photo_buffer"] = []
    await _forget_step_prompt(context)
    await query.edit_message_text(
        "Innehållet är sparat utan ändringar av foton."
    )
    if isinstance(key, str) and key in TOPIC_KEYS:
        await _start_link_step(context, key, query.message)
        return
    _clear_edit_session(context)


async def _offer_channel_publish(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int
) -> None:
    """Финальный вопрос: сохранить только в боте или ещё и пост в канал."""
    context.user_data["awaiting_links"] = None
    await context.bot.send_message(
        chat_id=chat_id,
        text=publish_offer_text(
            len(session_photo_ids(context)),
            len(session_link_items(context)),
        ),
        reply_markup=publish_offer_markup(),
    )


async def _handle_done_links(
    query, context: ContextTypes.DEFAULT_TYPE, user_id: int
) -> None:
    key = context.user_data.get("awaiting_links")
    items = session_link_items(context)
    if not isinstance(key, str) or key not in TOPIC_KEYS:
        _clear_edit_session(context)
        await _forget_step_prompt(context)
        await query.edit_message_text("Redigeringen är avbruten.")
        return

    title = topic_display_name(key)
    chat_id = query.message.chat_id
    if not items:
        await _forget_step_prompt(context)
        await query.edit_message_text(
            f"Inga länkar lades till. ✅ Rubriken {title} är helt uppdaterad."
        )
        await _show_topic_preview(context, chat_id, key)
        await _offer_channel_publish(context, chat_id)
        return

    pool = _db_pool(context)
    if pool is None:
        await _forget_step_prompt(context)
        await query.edit_message_text("Databasen är inte redo. Försök igen senare.")
        return

    await db.append_links(pool, key, items, user_id)
    _append_links_cache(context, key, items)
    _touch_freshness(context, key)
    await _forget_step_prompt(context)
    await query.edit_message_text(
        f"✅ {len(items)} nya länkar tillagda för {title}. "
        f"Rubriken är helt uppdaterad."
    )
    await _show_topic_preview(context, chat_id, key)
    await _offer_channel_publish(context, chat_id)


async def _handle_skip_links(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    key = context.user_data.get("awaiting_links")
    title = topic_display_name(key) if isinstance(key, str) else ""
    chat_id = query.message.chat_id
    context.user_data["link_buffer"] = []
    await _forget_step_prompt(context)
    if title and isinstance(key, str) and key in TOPIC_KEYS:
        await query.edit_message_text(
            f"Inga länkar lades till. ✅ Rubriken {title} är helt uppdaterad."
        )
        await _show_topic_preview(context, chat_id, key)
        await _offer_channel_publish(context, chat_id)
        return
    _clear_edit_session(context)
    await query.edit_message_text("Redigeringen är avslutad.")


async def _send_session_photos_to_channel(
    bot: Bot, file_ids: list[str]
) -> None:
    """Новые фото сессии — отдельными постами после баннера, пачками по 10."""
    if not file_ids:
        return
    if len(file_ids) == 1:
        await bot.send_photo(chat_id=CHANNEL, photo=file_ids[0])
        return
    for chunk in db.chunk_ids(file_ids, 10):
        if len(chunk) == 1:
            await bot.send_photo(chat_id=CHANNEL, photo=chunk[0])
        else:
            await bot.send_media_group(
                chat_id=CHANNEL,
                media=[InputMediaPhoto(file_id) for file_id in chunk],
            )


async def _handle_publish_channel(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    key = context.user_data.get("session_key")
    session_text = context.user_data.get("session_text")
    if not isinstance(key, str) or key not in TOPIC_KEYS:
        _clear_edit_session(context)
        await query.edit_message_text("Redigeringen är avbruten.")
        return
    if not isinstance(session_text, str) or not session_text.strip():
        session_text = topic_text(context, key)

    link = await inspect_channel_link(context.bot)
    if not link.can_post:
        await query.edit_message_text(format_channel_link_report(link))
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=publish_offer_text(
                len(session_photo_ids(context)),
                len(session_link_items(context)),
            ),
            reply_markup=publish_offer_markup(),
        )
        return

    label = topic_display_name(key)
    caption = channel_update_caption(label, session_text)
    markup = session_link_markup(session_link_items(context))
    extra_photos = session_photo_ids(context)
    photo = _cached_file_id(context, key) or banner_path(key)
    caption_fits = len(caption) <= MessageLimit.CAPTION_LENGTH

    try:
        if photo is not None and caption_fits:
            sent = await context.bot.send_photo(
                chat_id=CHANNEL,
                photo=photo,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
            )
            _remember_file_id(context, key, sent)
        elif photo is not None:
            short = f"🆕 <b>{html.escape(label)}</b>"
            sent = await context.bot.send_photo(
                chat_id=CHANNEL,
                photo=photo,
                caption=short,
                parse_mode=ParseMode.HTML,
            )
            _remember_file_id(context, key, sent)
            await context.bot.send_message(
                chat_id=CHANNEL,
                text=session_text,
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
            )
        else:
            await context.bot.send_message(
                chat_id=CHANNEL,
                text=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
            )
        await _send_session_photos_to_channel(context.bot, extra_photos)
    except Forbidden:
        await query.edit_message_text(
            f"Boten får inte skriva i {CHANNEL}. "
            f"Gör @{EXPECTED_BOT_USERNAME} till administratör först."
        )
        return
    except TelegramError:
        logger.exception("Не удалось опубликовать обновление в %s", CHANNEL)
        await query.edit_message_text(
            f"Inlägget kunde inte publiceras i {CHANNEL}. Försök igen."
        )
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=publish_offer_text(
                len(session_photo_ids(context)),
                len(session_link_items(context)),
            ),
            reply_markup=publish_offer_markup(),
        )
        return

    _clear_edit_session(context)
    await query.edit_message_text(f"✅ Publicerat i kanalen {CHANNEL}!")


async def _handle_no_publish(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    _clear_edit_session(context)
    await query.edit_message_text(
        "OK, inlägget publicerades inte i kanalen — bara sparat i boten."
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None or query.message is None:
        return

    await query.answer()
    chat_id = query.message.chat_id
    user = query.from_user
    user_id = user.id if user is not None else 0
    data = query.data

    if data.startswith("edit_") or data in _ADMIN_LINK_CALLBACKS:
        if not is_admin(user_id):
            return
        if data.startswith("edit_"):
            key = data.removeprefix("edit_")
            if key not in TOPIC_KEYS:
                return
            _clear_edit_session(context)
            context.user_data["awaiting_edit"] = key
            await _forget_step_prompt(context)
            title = topic_display_name(key)
            await query.edit_message_text(
                f"✏️ Skicka den nya texten för {title}. "
                "Du kan använda Telegrams vanliga formatering (fet, kursiv, länk).",
                reply_markup=cancel_edit_markup(),
            )
            return
        if data == "cancel_edit":
            _clear_edit_session(context)
            await _forget_step_prompt(context)
            await _show_redigera_menu_on_query(query)
            return
        if data == "done_photos":
            await _handle_done_photos(query, context, user_id)
            return
        if data == "skip_photos":
            await _handle_skip_photos(query, context)
            return
        if data == "done_links":
            await _handle_done_links(query, context, user_id)
            return
        if data == "skip_links":
            await _handle_skip_links(query, context)
            return
        if data == "publish_channel":
            await _handle_publish_channel(query, context)
            return
        await _handle_no_publish(query, context)
        return

    if data == "menu":
        await _send_menu_gallery(
            bot=context.bot,
            chat_id=chat_id,
            context=context,
            extra_delete_ids=[query.message.message_id],
        )
        return

    if data in TOPIC_KEYS:
        await _send_topic(
            bot=context.bot,
            chat_id=chat_id,
            topic=data,
            context=context,
            extra_delete_ids=[query.message.message_id],
        )


async def on_startup(application: Application) -> None:
    pool = await db.create_pool()
    await db.init_schema(pool)
    await db.seed_content_if_empty(pool, DEFAULT_CONTENT)
    cache = dict(DEFAULT_CONTENT)
    cache.update(await db.fetch_content_map(pool))
    application.bot_data["db"] = pool
    application.bot_data[_CONTENT_CACHE_KEY] = cache
    application.bot_data[_PHOTOS_CACHE_KEY] = await db.fetch_all_photo_ids(pool)
    application.bot_data[_LINKS_CACHE_KEY] = await db.fetch_all_links(pool)
    application.bot_data[_FRESHNESS_CACHE_KEY] = await db.fetch_last_activity(pool)
    logger.info("База готова. Текстов в кэше: %s.", len(cache))
    link = await inspect_channel_link(application.bot)
    if link.can_post:
        logger.info(
            "Канал связан: %s ↔ @%s (роль %s).",
            CHANNEL,
            link.bot_username,
            link.bot_status,
        )
    else:
        logger.warning(
            "Канал %s ещё не связан с @%s: %s",
            CHANNEL,
            link.bot_username or EXPECTED_BOT_USERNAME,
            link.error or "нет права публиковать",
        )


async def on_shutdown(application: Application) -> None:
    pool = application.bot_data.get("db")
    if pool is not None:
        await pool.close()
        logger.info("Соединения с базой закрыты.")


def build_application(token: str) -> Application:
    app = (
        ApplicationBuilder()
        .token(token)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )
    private = filters.ChatType.PRIVATE
    app.add_handler(CommandHandler("start", start, filters=private))
    app.add_handler(CommandHandler("menu", start, filters=private))
    app.add_handler(CommandHandler("publicera_meny", publish_menu, filters=private))
    app.add_handler(CommandHandler("kolla_kanal", check_channel, filters=private))
    app.add_handler(CommandHandler("redigera", redigera, filters=private))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO & private, handle_photo))
    app.add_handler(
        MessageHandler(filters.TEXT & private & ~filters.COMMAND, handle_admin_text)
    )
    return app


def main() -> None:
    token = load_token()
    log_banner_status()
    app = build_application(token)
    logger.info(
        "Бот запущен. Канал: %s. Ожидаемый бот: @%s. Остановка: Ctrl+C.",
        CHANNEL,
        EXPECTED_BOT_USERNAME,
    )
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
