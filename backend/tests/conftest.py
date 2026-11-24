import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture()
def client(monkeypatch):
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp}/test.db")
    monkeypatch.setenv("LLM_API_KEYS", "fake-a,fake-b")
    monkeypatch.setenv("ENABLE_FAILURE_SIMULATION", "true")
    monkeypatch.setenv("CACHE_TYPE", "local")
    monkeypatch.setenv("LLM_MOCK_RESPONSE", "The capital of France is Paris.")
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c
