import uuid

import litellm


def sid():
    return "s-" + uuid.uuid4().hex[:8]


def chat(client, message, session=None, headers=None, **extra):
    return client.post("/chat", json={"session_id": session or sid(), "message": message, **extra},
                       headers=headers or {})


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "keys_configured": 2, "cache_enabled": True}


def test_chat_live_then_cache_in_new_session(client):
    msg = "unique question " + uuid.uuid4().hex
    first = chat(client, msg).json()
    assert first["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert first["metadata"]["key_id"] == "key_1"
    second = chat(client, msg).json()  # different session, same first message
    assert second["metadata"]["resolution_source"] == "LLM_CACHE"
    assert second["metadata"]["key_id"] is None
    assert second["metadata"]["fallback_attempts"] == 0
    assert second["reply"] == first["reply"]
    assert second["metadata"]["input_tokens"] == first["metadata"]["input_tokens"]


def test_different_message_not_cached(client):
    chat(client, "alpha " + uuid.uuid4().hex)
    r = chat(client, "beta " + uuid.uuid4().hex).json()
    assert r["metadata"]["resolution_source"] == "LIVE_INFERENCE"


def test_failover_single_key(client):
    r = chat(client, "fo " + uuid.uuid4().hex, headers={"X-Simulate-Failure": "key_1=429"})
    assert r.status_code == 200
    md = r.json()["metadata"]
    assert md["key_id"] == "key_2" and md["fallback_attempts"] == 1
    assert md["resolution_source"] == "LIVE_INFERENCE"


def test_failover_500(client):
    r = chat(client, "fo5 " + uuid.uuid4().hex, headers={"X-Simulate-Failure": "key_1=500"})
    assert r.status_code == 200 and r.json()["metadata"]["key_id"] == "key_2"


def test_all_keys_fail_503_and_not_stored(client):
    s = sid()
    r = chat(client, "hello", session=s, headers={"X-Simulate-Failure": "*=429"})
    assert r.status_code == 503
    assert r.json() == {"detail": "all providers unavailable"}
    assert client.get(f"/sessions/{s}/messages").status_code == 404


def test_simulation_ignored_when_disabled(client, monkeypatch):
    monkeypatch.setenv("ENABLE_FAILURE_SIMULATION", "false")
    r = chat(client, "nosim " + uuid.uuid4().hex, headers={"X-Simulate-Failure": "*=429"})
    assert r.status_code == 200


def test_real_provider_error_triggers_failover(client, monkeypatch):
    calls = []
    real = litellm.completion

    def flaky(**kw):
        calls.append(kw["api_key"])
        if kw["api_key"] == "fake-a":
            raise litellm.RateLimitError("quota", "gemini", "m")
        return real(**kw)

    monkeypatch.setattr(litellm, "completion", flaky)
    r = chat(client, "real " + uuid.uuid4().hex)
    assert r.status_code == 200 and r.json()["metadata"]["key_id"] == "key_2"
    assert calls[:2] == ["fake-a", "fake-b"]


def test_validation_422(client):
    assert client.post("/chat", json={"session_id": "x", "message": "   "}).status_code == 422
    assert client.post("/chat", json={"session_id": "", "message": "hi"}).status_code == 422
    assert client.post("/chat", json={"session_id": "x", "message": "a" * 4001}).status_code == 422
    assert client.post("/chat", json={"message": "hi"}).status_code == 422
    r = client.post("/chat", content="{bad json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422 and "detail" in r.json()


def test_history_and_sessions_separate(client):
    a, b = sid(), sid()
    chat(client, "one " + uuid.uuid4().hex, session=a)
    chat(client, "two " + uuid.uuid4().hex, session=a)
    chat(client, "other " + uuid.uuid4().hex, session=b)
    msgs = client.get(f"/sessions/{a}/messages").json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert set(msgs[1]["metadata"]) >= {"resolution_source", "input_tokens", "output_tokens"}
    assert "metadata" not in msgs[0]
    assert len(client.get(f"/sessions/{b}/messages").json()["messages"]) == 2


def test_unknown_session_404(client):
    r = client.get("/sessions/nope/messages")
    assert r.status_code == 404 and r.json() == {"detail": "session not found"}


def test_history_is_sent_to_llm(client, monkeypatch):
    seen = []
    real = litellm.completion

    def spy(**kw):
        seen.append(kw["messages"])
        return real(**kw)

    monkeypatch.setattr(litellm, "completion", spy)
    s = sid()
    chat(client, "my name is Yuvraj " + uuid.uuid4().hex, session=s, system_prompt="Be terse.")
    chat(client, "what is my name? " + uuid.uuid4().hex, session=s)
    assert seen[1][0] == {"role": "system", "content": "Be terse."}
    assert len(seen[1]) == 4  # system + user + assistant + new user
