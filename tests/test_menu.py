"""Проверяем меню без сети: кнопки, ключи, баннеры и сборку приложения."""

import os
from pathlib import Path

import pytest
from telegram.constants import MessageLimit
from telegram.ext import Application

os.environ.setdefault("BOT_TOKEN", "0000000000:TESTTOKEN_FOR_UNIT_TESTS_ONLY")

from telegram_meny_abmrab import (  # noqa: E402
    BANNER_FILES,
    CONTENT,
    MENU_ITEMS,
    _SCRIPT_DIR,
    banner_path,
    banners_dir,
    build_application,
    channel_menu,
    load_token,
    main_menu,
)

EXPECTED_BANNERS = {
    "nyheter": "nyheter.png",
    "aquatone": "aquatone.png",
    "biotrem": "biotrem.png",
    "monicor": "monicor.png",
    "kvantresonans": "kvantresonans.png",
    "rejuvination_club_100": "rejuvination_club_100.png",
}


def test_menu_items_are_four_tuples() -> None:
    assert MENU_ITEMS
    for item in MENU_ITEMS:
        assert len(item) == 4


def test_content_and_banner_keys_match_menu_items() -> None:
    keys = {key for key, _label, _text, _banner in MENU_ITEMS}
    assert set(CONTENT) == keys
    assert set(BANNER_FILES) == keys
    assert BANNER_FILES == EXPECTED_BANNERS


def test_captions_fit_telegram_limit() -> None:
    for text in CONTENT.values():
        assert len(text) <= MessageLimit.CAPTION_LENGTH


def test_main_menu_has_one_button_per_topic() -> None:
    markup = main_menu()
    buttons = [button for row in markup.inline_keyboard for button in row]
    assert [button.callback_data for button in buttons] == [
        key for key, _label, _text, _banner in MENU_ITEMS
    ]


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
    assert len(app.handlers[0]) >= 4
