import pytest


class TestRAGSearch:
    @pytest.mark.parametrize(
        "question,expected_lang",
        [
            ("什么是高血压", "zh"),
            ("What is hypertension", "en"),
            ("高血圧とは", "ja"),
        ],
    )
    def test_lang_detection(self, question, expected_lang):
        from qa.views import _detect_question_lang
        assert _detect_question_lang(question) == expected_lang

    @pytest.mark.parametrize(
        "text,lang,expected",
        [
            ("这是一个中文句子", "zh", False),
            ("this is english", "zh", True),
            ("mixed sentence 中文", "en", True),
        ],
    )
    def test_wrong_language_detection(self, text, lang, expected):
        from qa.views import _looks_like_wrong_language
        assert _looks_like_wrong_language(text, lang) == expected
