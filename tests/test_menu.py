"""Проверяем меню без сети: кнопки, ключи, баннеры и сборку приложения."""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from telegram.constants import MessageLimit
from telegram.ext import Application

os.environ.setdefault("BOT_TOKEN", "0000000000:TESTTOKEN_FOR_UNIT_TESTS_ONLY")

from telegram_meny_abmrab import (  # noqa: E402
    BANNER_FILES,
    CONTENT,
    DEFAULT_CONTENT,
    MENU_ITEMS,
    TOPIC_KEYS,
    _SCRIPT_DIR,
    banner_path,
    banners_dir,
    build_application,
    channel_menu,
    is_admin,
    link_button_label,
    load_token,
    normalize_url,
    menu_card_caption,
    parse_admin_ids,
    redigera_menu,
    remaining_menu_items,
    topic_card_markup,
    topic_keyboard,
    topic_title,
    _FRESHNESS_CACHE_KEY,
    _LINKS_CACHE_KEY,
    NEW_MARK_TTL,
    is_topic_new,
)

EXPECTED_BANNERS = {
    "nyheter": "nyheter.png",
    "aquatone": "aquatone.png",
    "biotrem": "biotrem.png",
    "monicor": "monicor.png",
    "kvantresonans": "kvantresonans.png",
    "longevity_club_100": "longevity_club_100.png",
}


def test_menu_items_are_four_tuples() -> None:
    assert MENU_ITEMS
    for item in MENU_ITEMS:
        assert len(item) == 4


def test_content_and_banner_keys_match_menu_items() -> None:
    keys = {key for key, _label, _text, _banner in MENU_ITEMS}
    assert set(CONTENT) == keys
    assert set(DEFAULT_CONTENT) == keys
    assert TOPIC_KEYS == keys
    assert set(BANNER_FILES) == keys
    assert BANNER_FILES == EXPECTED_BANNERS


def test_captions_fit_telegram_limit() -> None:
    for text in CONTENT.values():
        assert len(text) <= MessageLimit.CAPTION_LENGTH


def test_topic_titles_and_card_captions() -> None:
    assert topic_title("📰 Nyheter") == "Nyheter"
    assert topic_title("🌿 Longevity Club 100+") == "Longevity Club 100+"
    assert menu_card_caption("💧 Aquatone") == "<b>Aquatone</b>"
    assert menu_card_caption("📰 Nyheter", is_new=True) == "<b>🆕 Nyheter</b>"


def test_remaining_menu_items_skips_opened_topic() -> None:
    rest = remaining_menu_items("nyheter")
    keys = [key for key, _label, _text, _banner in rest]
    assert "nyheter" not in keys
    assert keys == [
        key for key, _label, _text, _banner in MENU_ITEMS if key != "nyheter"
    ]
    assert len(rest) == len(MENU_ITEMS) - 1


def test_topic_card_has_matching_button() -> None:
    for key, label, _text, _banner in MENU_ITEMS:
        markup = topic_card_markup(key, label)
        buttons = [button for row in markup.inline_keyboard for button in row]
        assert len(buttons) == 1
        assert buttons[0].callback_data == key
        assert buttons[0].text == label


def test_new_topic_button_keeps_callback() -> None:
    markup = topic_card_markup("nyheter", "📰 Nyheter", is_new=True)
    button = markup.inline_keyboard[0][0]
    assert button.text == "🆕 📰 Nyheter"
    assert button.callback_data == "nyheter"


def test_channel_menu_uses_deep_links() -> None:
    markup = channel_menu("abmrab_meny_bot")
    buttons = [button for row in markup.inline_keyboard for button in row]
    urls = [button.url for button in buttons]
    assert urls == [
        f"https://t.me/abmrab_meny_bot?start={key}"
        for key, _label, _text, _banner in MENU_ITEMS
    ]


def test_banner_path_missing_file_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BANNERS_DIR", str(tmp_path))
    assert banner_path("nyheter") is None
    assert banner_path("unknown_topic") is None


def test_banner_path_finds_existing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BANNERS_DIR", str(tmp_path))
    image = tmp_path / "aquatone.png"
    image.write_bytes(b"fake-image")
    assert banner_path("aquatone") == image
    assert banner_path("nyheter") is None


def test_banners_dir_uses_absolute_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BANNERS_DIR", str(tmp_path))
    assert banners_dir() == tmp_path


def test_relative_banners_dir_is_next_to_script(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BANNERS_DIR", "banners")
    monkeypatch.chdir(tmp_path)

    assert banners_dir() == _SCRIPT_DIR / "banners"
    assert banners_dir().is_absolute()


def test_unset_banners_dir_is_next_to_script(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("BANNERS_DIR", raising=False)
    monkeypatch.chdir(tmp_path)

    assert banners_dir() == _SCRIPT_DIR / "banners"


def test_load_token_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123:ABC")
    assert load_token() == "123:ABC"


def test_load_token_rejects_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "KLISTRA_IN_DIN_TOKEN_HAR")
    with pytest.raises(ValueError):
        load_token()


def test_build_application_registers_handlers() -> None:
    app = build_application("0000000000:TESTTOKEN_FOR_UNIT_TESTS_ONLY")
    assert isinstance(app, Application)
    assert len(app.handlers[0]) >= 7


def test_parse_admin_ids() -> None:
    assert parse_admin_ids("111111111,222222222") == {111111111, 222222222}
    assert parse_admin_ids("  42 , , 7 ") == {42, 7}
    assert parse_admin_ids("") == set()


def test_is_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_IDS", "100,200")
    assert is_admin(100) is True
    assert is_admin(200) is True
    assert is_admin(999) is False


def test_normalize_url_accepts_http_and_bare_hosts() -> None:
    assert normalize_url("https://youtu.be/abc") == "https://youtu.be/abc"
    assert normalize_url("youtube.com/watch?v=1") == "https://youtube.com/watch?v=1"
    assert normalize_url("hej på dig") is None
    assert normalize_url("") is None


def test_link_button_label_for_youtube_and_other() -> None:
    assert link_button_label("https://youtu.be/abc") == "▶️ Titta på YouTube"
    assert link_button_label("https://www.youtube.com/watch?v=1") == "▶️ Titta på YouTube"
    assert link_button_label("https://example.com/page") == "🔗 Läs mer"


def test_topic_keyboard_puts_links_before_back() -> None:
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                _LINKS_CACHE_KEY: {
                    "nyheter": [("https://youtu.be/abc", "▶️ Titta på YouTube")]
                }
            }
        )
    )
    markup = topic_keyboard(context, "nyheter")
    rows = markup.inline_keyboard
    assert rows[0][0].url == "https://youtu.be/abc"
    assert rows[-1][0].callback_data == "menu"


def test_redigera_menu_has_edit_callbacks_and_cancel() -> None:
    markup = redigera_menu()
    buttons = [button for row in markup.inline_keyboard for button in row]
    callbacks = [button.callback_data for button in buttons]
    assert callbacks[-1] == "cancel_edit"
    assert callbacks[:-1] == [f"edit_{key}" for key, _label, _text, _banner in MENU_ITEMS]


def _freshness_context(last_at: datetime | None) -> SimpleNamespace:
    cache: dict[str, datetime] = {}
    if last_at is not None:
        cache["nyheter"] = last_at
    return SimpleNamespace(
        application=SimpleNamespace(bot_data={_FRESHNESS_CACHE_KEY: cache})
    )


def test_new_mark_ttl_is_two_days() -> None:
    assert NEW_MARK_TTL == timedelta(days=2)


def test_is_topic_new_within_two_days() -> None:
    recent = datetime.now(timezone.utc) - timedelta(hours=12)
    assert is_topic_new(_freshness_context(recent), "nyheter") is True


def test_is_topic_new_after_two_days() -> None:
    old = datetime.now(timezone.utc) - timedelta(days=2, seconds=1)
    assert is_topic_new(_freshness_context(old), "nyheter") is False


def test_is_topic_new_without_timestamp() -> None:
    assert is_topic_new(_freshness_context(None), "nyheter") is False


def test_is_topic_new_only_the_edited_topic() -> None:
    recent = datetime.now(timezone.utc)
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={_FRESHNESS_CACHE_KEY: {"nyheter": recent}}
        )
    )
    assert is_topic_new(context, "nyheter") is True
    assert is_topic_new(context, "aquatone") is False
    assert is_topic_new(context, "biotrem") is False
