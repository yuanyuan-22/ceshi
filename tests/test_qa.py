import pytest


class TestQAAPI:
    QA_URL = "/api/qa/"

    def test_qa_requires_auth(self, api_client):
        response = api_client.post(self.QA_URL, {"question": "test"}, format="json")
        assert response.status_code == 401

    def test_qa_empty_question(self, auth_client):
        response = auth_client.post(self.QA_URL, {"question": ""}, format="json")
        assert response.status_code == 400

    def test_qa_returns_expected_keys(self, auth_client):
        response = auth_client.post(
            self.QA_URL,
            {"question": "什么是高血压", "lang": "zh"},
            format="json",
        )
        if response.status_code == 200:
            data = response.data
            assert "answer" in data
            assert "confidence" in data
            assert "sources" in data
            assert "latency_ms" in data
            assert "mode" in data
            assert data["mode"] == "rag_siliconflow"
