"""Проверяем меню без сети: кнопки, ключи и сборку приложения."""

import os

import pytest
from telegram.ext import Application

os.environ.setdefault("BOT_TOKEN", "0000000000:TESTTOKEN_FOR_UNIT_TESTS_ONLY")

from telegram_meny_abmrab import (  # noqa: E402
    CONTENT,
    MENU_ITEMS,
    build_application,
    channel_menu,
    load_token,
    main_menu,
)


def test_content_keys_match_menu_items() -> None:
    assert set(CONTENT) == {key for key, _label, _text in MENU_ITEMS}


def test_main_menu_has_one_button_per_topic() -> None:
    markup = main_menu()
    buttons = [button for row in markup.inline_keyboard for button in row]
    assert [button.callback_data for button in buttons] == [
        key for key, _label, _text in MENU_ITEMS
    ]


def test_channel_menu_uses_deep_links() -> None:
    markup = channel_menu("abmrab_meny_bot")
    buttons = [button for row in markup.inline_keyboard for button in row]
    urls = [button.url for button in buttons]
    assert urls == [
        f"https://t.me/abmrab_meny_bot?start={key}" for key, _label, _text in MENU_ITEMS
    ]


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
    assert len(app.handlers[0]) >= 4
