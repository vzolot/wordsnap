"""Тести languages.py — прапори та назви."""
import pytest

from core.languages import LANGUAGES, lang_flag, lang_name

SUPPORTED = ["uk", "en", "es", "pl", "de"]


@pytest.mark.parametrize("code", SUPPORTED)
def test_each_supported_has_flag_and_name(code):
    name, flag = LANGUAGES[code]
    assert isinstance(name, str) and len(name) > 0
    assert isinstance(flag, str) and len(flag) >= 1


@pytest.mark.parametrize("code", SUPPORTED)
def test_lang_flag_returns_real_flag(code):
    assert lang_flag(code) != "🌐"


def test_lang_flag_unknown_returns_globe():
    assert lang_flag("xx") == "🌐"


def test_lang_name_for_known_codes():
    assert lang_name("uk") == "Українська"
    assert lang_name("de") == "Deutsch"
    assert lang_name("en") == "English"


def test_lang_name_unknown_returns_question():
    assert lang_name("xx") == "?"
