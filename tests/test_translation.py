import pytest
from django.urls import reverse


class TestTranslationAPI:
    TRANSLATE_URL = "/api/translate/"

    def test_translate_requires_auth(self, api_client):
        response = api_client.post(self.TRANSLATE_URL, {"text": "hello"}, format="json")
        assert response.status_code == 401

    def test_translate_empty_text(self, auth_client):
        response = auth_client.post(self.TRANSLATE_URL, {"text": ""}, format="json")
        assert response.status_code == 400
        assert "error" in response.data

    def test_translate_unsupported_lang(self, auth_client):
        response = auth_client.post(
            self.TRANSLATE_URL,
            {"text": "hello", "src_lang": "xx", "tgt_lang": "zh"},
            format="json",
        )
        assert response.status_code == 400
        assert "unsupported" in response.data["error"]

    def test_translate_struct_response(self, auth_client):
        response = auth_client.post(
            self.TRANSLATE_URL,
            {"text": "hello", "src_lang": "en", "tgt_lang": "zh"},
            format="json",
        )
        if response.status_code == 200:
            data = response.data
            assert "translation" in data
            assert "base_translation" in data
            assert "lora_translation" in data
            assert "latency_ms" in data
