"""M7: вітання white-label учню — від бренду, без згадок WordSnap (pure logic)."""
from core.bot_i18n import branded_welcome


def test_branded_welcome_no_wordsnap_mention():
    for lang in ("uk", "en", "es", "pl", "de", "fr", "unknown"):
        w = branded_welcome(lang, "Слова з Оксаною")
        assert "WordSnap" not in w
        assert "Слова з Оксаною" in w
