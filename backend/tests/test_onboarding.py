"""Тести міст та демо-слів для onboarding-флоу."""
import pytest

from core.onboarding import CITIES, DEMO_WORDS_UK, get_cities, get_demo_word


@pytest.mark.parametrize("target", ["pl", "de", "es", "en", "uk"])
def test_each_target_lang_has_at_least_3_cities(target):
    cities = get_cities(target)
    assert len(cities) >= 3


@pytest.mark.parametrize("target", ["pl", "de", "es", "en"])
def test_demo_word_exists_for_uk_native_each_target(target):
    demo = get_demo_word(target, "uk")
    assert demo is not None
    assert "word" in demo
    assert "translation" in demo
    assert "examples" in demo
    assert isinstance(demo["examples"], list)
    assert len(demo["examples"]) >= 1


def test_demo_word_returns_none_for_non_uk_native():
    # Для не-UA нативів демо поки не реалізовано
    assert get_demo_word("en", "pl") is None
    assert get_demo_word("de", "es") is None


def test_demo_word_examples_have_structure():
    demo = get_demo_word("pl", "uk")
    for ex in demo["examples"]:
        assert "sentence" in ex
        assert "explanation" in ex


def test_cities_dict_has_all_supported_langs():
    for code in ["pl", "de", "es", "en", "uk"]:
        assert code in CITIES


def test_each_city_has_id_and_label():
    for code, cities in CITIES.items():
        for city_id, label in cities:
            assert isinstance(city_id, str) and len(city_id) > 0
            assert isinstance(label, str) and len(label) > 0


def test_demo_word_keys_match_target_langs():
    # У DEMO_WORDS_UK не повинно бути ключів за межами підтримуваних мов
    for code in DEMO_WORDS_UK.keys():
        assert code in {"pl", "de", "es", "en", "uk"}
