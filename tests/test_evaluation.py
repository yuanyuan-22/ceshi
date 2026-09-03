import pytest
from unittest.mock import patch, MagicMock
import numpy as np


class TestEvaluationServices:
    def test_compute_recall_at_k(self):
        from evaluation.services import _compute_recall_at_k
        expected = ["common cold", "hypertension"]
        retrieved = ["common cold", "headache", "hypertension", "diabetes", "fever"]
        assert _compute_recall_at_k(expected, retrieved, 1) == 0.5
        assert _compute_recall_at_k(expected, retrieved, 3) == 1.0
        assert _compute_recall_at_k(expected, retrieved, 5) == 1.0

    def test_compute_recall_none_found(self):
        from evaluation.services import _compute_recall_at_k
        expected = ["common cold"]
        retrieved = ["headache", "fever", "cough"]
        assert _compute_recall_at_k(expected, retrieved, 3) == 0.0

    def test_compute_mrr(self):
        from evaluation.services import _compute_mrr
        expected = ["common cold", "hypertension"]
        retrieved = ["headache", "common cold", "hypertension", "fever"]
        assert _compute_mrr(expected, retrieved) == 0.5

    def test_compute_mrr_first_position(self):
        from evaluation.services import _compute_mrr
        expected = ["common cold"]
        retrieved = ["common cold", "headache"]
        assert _compute_mrr(expected, retrieved) == 1.0

    def test_compute_mrr_not_found(self):
        from evaluation.services import _compute_mrr
        expected = ["common cold"]
        retrieved = ["headache", "fever"]
        assert _compute_mrr(expected, retrieved) == 0.0

    def test_compute_ndcg_at_k(self):
        from evaluation.services import _compute_ndcg_at_k
        expected = ["common cold", "hypertension"]
        retrieved = ["common cold", "headache", "hypertension", "fever"]
        ndcg = _compute_ndcg_at_k(expected, retrieved, 5)
        assert 0 <= ndcg <= 1.1

    def test_compute_ndcg_perfect(self):
        from evaluation.services import _compute_ndcg_at_k
        expected = ["common cold", "hypertension"]
        retrieved = ["common cold", "hypertension"]
        ndcg = _compute_ndcg_at_k(expected, retrieved, 5)
        assert abs(ndcg - 1.0) < 0.01

    def test_load_qa_eval_pairs_structure(self):
        from evaluation.services import _load_qa_eval_pairs
        with patch("evaluation.services.Path.exists", return_value=True), \
             patch("evaluation.services.json.loads") as mock_loads:
            mock_loads.return_value = [{
                "entity_id": "disease_test",
                "canonical_key": "test disease",
                "category": "disease",
                "lang_terms": {
                    "zh": {"name": "测试疾病"},
                    "en": {"name": "Test Disease"},
                }
            }]
            pairs = _load_qa_eval_pairs()
            assert len(pairs) > 0
            for p in pairs:
                assert "question" in p
                assert "expected_entity_keys" in p
                assert p["expected_entity_keys"][0] == "test disease"


class TestEvalAPI:
    EVAL_URL = "/api/eval/"

    def test_dashboard_requires_auth(self, api_client):
        response = api_client.get(f"{self.EVAL_URL}dashboard/")
        assert response.status_code == 401

    def test_dashboard_authenticated(self, auth_client):
        response = auth_client.get(f"{self.EVAL_URL}dashboard/")
        assert response.status_code == 200
        data = response.data
        assert "qa_total_7d" in data
        assert "feedback_total_30d" in data

    def test_runs_list_requires_auth(self, api_client):
        response = api_client.get(f"{self.EVAL_URL}runs/")
        assert response.status_code == 401

    def test_runs_list_authenticated(self, auth_client):
        response = auth_client.get(f"{self.EVAL_URL}runs/")
        assert response.status_code == 200

    def test_trigger_rag_eval_requires_admin(self, auth_client):
        response = auth_client.post(f"{self.EVAL_URL}trigger/rag/", {"top_k": 3, "max_questions": 5}, format="json")
        assert response.status_code == 403

    def test_judge_requires_admin(self, auth_client):
        response = auth_client.post(f"{self.EVAL_URL}judge/", {"question": "test", "answer": "test answer"}, format="json")
        assert response.status_code == 403

    def test_judge_missing_params(self, admin_client):
        response = admin_client.post(f"{self.EVAL_URL}judge/", {}, format="json")
        assert response.status_code == 400


class TestJudgeAnswerQuality:
    def test_judge_without_api(self):
        from evaluation.services import judge_answer_quality
        with patch("evaluation.services.get_qa_generator") as mock_gen:
            mock_gen.return_value.client = None
            result = judge_answer_quality("What is test?", "Test answer.", "Test context.")
            assert "error" in result

    def test_judge_json_parsing(self):
        from evaluation.services import judge_answer_quality
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='{"accuracy": 4, "completeness": 3, "relevance": 5, "brief_comment": "Good answer."}'))
        ]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("evaluation.services.get_qa_generator") as mock_gen:
            mock_gen.return_value.client = mock_client
            result = judge_answer_quality("What is test?", "Test answer.", "Test context.")
            assert result["accuracy"] == 4
            assert result["completeness"] == 3
            assert result["relevance"] == 5
            assert result.get("comment") == "Good answer."


@pytest.fixture
def admin_user(django_user_model):
    return django_user_model.objects.create_superuser(
        username="admin",
        password="adminpass123",
        email="admin@example.com",
    )


@pytest.fixture
def admin_client(api_client, admin_user):
    api_client.force_authenticate(user=admin_user)
    return api_client
