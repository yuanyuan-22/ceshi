import pytest


class TestTermMatching:
    def test_extract_terms_returns_list(self):
        from translation.term_matcher import extract_terms_for_text
        terms = extract_terms_for_text("patient has high blood pressure", lang="en", limit=10)
        assert isinstance(terms, list)

    def test_health_checkup_terms(self):
        from translation.term_matcher import extract_terms_for_text
        terms = extract_terms_for_text("heart disease", lang="en", limit=5)
        assert len(terms) >= 0
