import pytest
from django.urls import reverse


class TestHealthCheck:
    def test_health_endpoint(self, api_client):
        response = api_client.get("/api/health/")
        assert response.status_code in (200, 503)
        data = response.json()
        assert "status" in data
        assert "database" in data
        assert "cache" in data

    def test_health_returns_version(self, api_client):
        response = api_client.get("/api/health/")
        data = response.json()
        assert "version" in data
        assert "timestamp" in data
