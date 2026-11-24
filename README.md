# LLM Chatbot with Key Failover and Response Caching

React + FastAPI + LiteLLM + SQLite, shipped with Docker.

## 1\. Live URLs

\- Frontend: https://lyftr-llm-chatbot-tawny.vercel.app

\- Backend: https://lyftr-chat-backend-r7v8.onrender.com (try /health)

\- Repository: https://github.com/yuvraj0702/lyftr-llm-chatbot

## 2\. Run locally

### With Docker

```
copy .env.example .env
```

Edit `.env` and put at least 2 real keys in `LLM\_API\_KEYS`, then:

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
.venv\\Scripts\\activate
pip install -r requirements-dev.txt
set LLM\_API\_KEYS=key1,key2
set DATABASE\_URL=sqlite:///./app.db
set CACHE\_DIR=./cache
set ENABLE\_FAILURE\_SIMULATION=true
set ALLOWED\_ORIGINS=http://localhost:3000
uvicorn app.main:app --port 8000
```

Frontend:

```
cd frontend
npm install
set VITE\_API\_URL=http://localhost:8000
npm run dev
```

Tests: `cd backend \&\& python -m pytest -q`

## 3\. Design decisions

**Key fallback.** `LLM\_API\_KEYS` becomes the pool `key\_1..key\_N`. Each request walks the pool in order and calls `litellm.completion(api\_key=...)`. Any failure (429, quota, 5xx, auth, timeout) moves to the next key. `fallback\_attempts` counts failed keys. If every key fails the API returns `503 {"detail": "all providers unavailable"}` and nothing is written to history. Keys are never logged or returned, only `key\_id`.

**Caching.** LiteLLM's built-in cache (disk by default, in-memory as fallback) is enabled globally. Its key is the model plus the full message list (system prompt + history + new message), so the same first message in a new session is a hit and a different message is never a hit. A hit is detected from LiteLLM's `cache\_hit` flag and reported as `LLM\_CACHE` with `key\_id = null`, `fallback\_attempts = 0`, and the tokens stored with the original response. Requests carrying `X-Simulate-Failure` bypass the cache so a failover demo always returns a real answer.

**SQLite session storage.** `messages` follows the required schema; a small `sessions` table stores the optional per-session system prompt. History is read from SQLite on every request, so the client only sends the new message and history survives restarts (`/data` is a Docker volume). A user and assistant message pair is written in one transaction only after a successful reply, so 422 and 503 requests leave no trace. The schema is created at startup.

**Failure simulation.** `X-Simulate-Failure` (`key\_1=429`, `key\_1=429,key\_2=500`, `\*=503`) is parsed per request and only honored when `ENABLE\_FAILURE\_SIMULATION=true`. A simulated key fails before any provider call; the next key makes a real call.

## 4\. Verification

Replace `BACKEND` with your backend URL.

```
curl BACKEND/health
curl -X POST BACKEND/chat -H "Content-Type: application/json" -d "{\\"session\_id\\":\\"s-1\\",\\"message\\":\\"What is the capital of France?\\"}"
```

* Cache hit: send the same first message with a different `session\_id`. `resolution\_source` becomes `LLM\_CACHE`, `key\_id` is `null`, `latency\_ms` is much lower.
* Failover: add `-H "X-Simulate-Failure: key\_1=429"`. Expect 200 with `key\_id: key\_2`, `fallback\_attempts: 1`.
* All keys down: `-H "X-Simulate-Failure: \*=429"` gives 503 and the session stays empty.
* Token usage: `input\_tokens` and `output\_tokens` are per request. In the UI they are shown under every reply.
* History: `curl BACKEND/sessions/s-1/messages`

## 5\. Setup Used

* Editor: `vscode`
* AI tools: Claude (code generation and review)

## 6\. Bonus features

* Optional system prompt field per session (UI and API).
* Disk-backed cache that survives restarts, with automatic fallback to memory.
* `LLM\_MOCK\_RESPONSE` setting so the app and tests run without real keys.
* Backend test suite covering failover, cache, validation, history and session isolation.

