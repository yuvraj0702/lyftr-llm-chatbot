# LLM Chatbot with Key Failover and Response Caching

React + FastAPI + LiteLLM + SQLite, shipped with Docker.

## 1. Live URLs

- Frontend: `<add your Vercel/Netlify URL>`
- Backend: `<add your Render/Railway URL>` (try `/health`)
- Repository: `<add your GitHub URL>`

## 2. Run locally

### With Docker

```
copy .env.example .env
```
Edit `.env` and put at least 2 real keys in `LLM_API_KEYS`, then:
```
make up
```
Frontend: http://localhost:3000, backend: http://localhost:8000. Stop with `make down`.
Without make: `docker compose up --build -d`.

### Without Docker

Backend (Windows CMD):
```
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
set LLM_API_KEYS=key1,key2
set DATABASE_URL=sqlite:///./app.db
set CACHE_DIR=./cache
set ENABLE_FAILURE_SIMULATION=true
set ALLOWED_ORIGINS=http://localhost:3000
uvicorn app.main:app --port 8000
```
Frontend:
```
cd frontend
npm install
set VITE_API_URL=http://localhost:8000
npm run dev
```
Tests: `cd backend && python -m pytest -q`

## 3. Design decisions

**Key fallback.** `LLM_API_KEYS` becomes the pool `key_1..key_N`. Each request walks the pool in order and calls `litellm.completion(api_key=...)`. Any failure (429, quota, 5xx, auth, timeout) moves to the next key. `fallback_attempts` counts failed keys. If every key fails the API returns `503 {"detail": "all providers unavailable"}` and nothing is written to history. Keys are never logged or returned, only `key_id`.

**Caching.** LiteLLM's built-in cache (disk by default, in-memory as fallback) is enabled globally. Its key is the model plus the full message list (system prompt + history + new message), so the same first message in a new session is a hit and a different message is never a hit. A hit is detected from LiteLLM's `cache_hit` flag and reported as `LLM_CACHE` with `key_id = null`, `fallback_attempts = 0`, and the tokens stored with the original response. Requests carrying `X-Simulate-Failure` bypass the cache so a failover demo always returns a real answer.

**SQLite session storage.** `messages` follows the required schema; a small `sessions` table stores the optional per-session system prompt. History is read from SQLite on every request, so the client only sends the new message and history survives restarts (`/data` is a Docker volume). A user and assistant message pair is written in one transaction only after a successful reply, so 422 and 503 requests leave no trace. The schema is created at startup.

**Failure simulation.** `X-Simulate-Failure` (`key_1=429`, `key_1=429,key_2=500`, `*=503`) is parsed per request and only honored when `ENABLE_FAILURE_SIMULATION=true`. A simulated key fails before any provider call; the next key makes a real call.

## 4. Verification

Replace `BACKEND` with your backend URL.

```
curl BACKEND/health
curl -X POST BACKEND/chat -H "Content-Type: application/json" -d "{\"session_id\":\"s-1\",\"message\":\"What is the capital of France?\"}"
```
- Cache hit: send the same first message with a different `session_id`. `resolution_source` becomes `LLM_CACHE`, `key_id` is `null`, `latency_ms` is much lower.
- Failover: add `-H "X-Simulate-Failure: key_1=429"`. Expect 200 with `key_id: key_2`, `fallback_attempts: 1`.
- All keys down: `-H "X-Simulate-Failure: *=429"` gives 503 and the session stays empty.
- Token usage: `input_tokens` and `output_tokens` are per request. In the UI they are shown under every reply.
- History: `curl BACKEND/sessions/s-1/messages`

## 5. Setup Used

- Editor: `<your editor>`
- AI tools: Claude (code generation and review)

## 6. Bonus features

- Optional system prompt field per session (UI and API).
- Disk-backed cache that survives restarts, with automatic fallback to memory.
- `LLM_MOCK_RESPONSE` setting so the app and tests run without real keys.
- Backend test suite covering failover, cache, validation, history and session isolation.
