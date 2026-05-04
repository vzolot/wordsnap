"""Тести локалізації."""
import pytest

from core.bot_i18n import T, buy_text, help_text, premium_text, t

SUPPORTED_LANGS = ["uk", "en", "es", "pl", "de"]


class TestTranslateFn:
    def test_known_key_uk(self):
        assert t("setup.saved", "uk").startswith("✅")

    def test_unknown_lang_falls_back_to_uk(self):
        assert t("setup.saved", "xx") == t("setup.saved", "uk")

    def test_unknown_key_returns_key(self):
        assert t("nonexistent.key", "uk") == "nonexistent.key"

    def test_var_substitution(self):
        s = t("limit.expired", "uk", xp=42)
        assert "42" in s

    def test_multiple_var_substitution(self):
        # ask_target має {flag} та {name}
        s = t("setup.ask_target", "uk", flag="🇺🇦", name="Українська")
        assert "🇺🇦" in s
        assert "Українська" in s


class TestAllLangsCoverage:
    """Перевіряємо що ключові рядки є у всіх 5 мовах."""

    @pytest.mark.parametrize("lang", SUPPORTED_LANGS)
    def test_setup_saved(self, lang):
        assert "setup.saved" in T[lang]

    @pytest.mark.parametrize("lang", SUPPORTED_LANGS)
    def test_help_title(self, lang):
        assert "help.title" in T[lang]

    @pytest.mark.parametrize("lang", SUPPORTED_LANGS)
    def test_limit_expired(self, lang):
        # Має містити placeholder {xp}
        assert "{xp}" in T[lang]["limit.expired"]

    @pytest.mark.parametrize("lang", SUPPORTED_LANGS)
    def test_tier_up_title(self, lang):
        assert "tierup.title" in T[lang]

    @pytest.mark.parametrize("lang", SUPPORTED_LANGS)
    def test_rewards_keys(self, lang):
        for k in ["rewards.beginner", "rewards.apprentice", "rewards.word_master",
                  "rewards.polyglot", "rewards.sage"]:
            assert k in T[lang]


class TestBuilders:
    @pytest.mark.parametrize("lang", SUPPORTED_LANGS)
    def test_help_text_includes_main_commands(self, lang):
        h = help_text(lang)
        for cmd in ["/review", "/songs", "/app", "/stats", "/language",
                    "/premium", "/buy", "/subscription", "/unsubscribe"]:
            assert cmd in h

    @pytest.mark.parametrize("lang", SUPPORTED_LANGS)
    def test_premium_mentions_price(self, lang):
        assert "$1.49" in premium_text(lang)

    @pytest.mark.parametrize("lang", SUPPORTED_LANGS)
    def test_buy_mentions_price(self, lang):
        assert "$1.49" in buy_text(lang)
