import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import config, db, llm

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("app")

state = {"cache_enabled": False}


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    state["cache_enabled"] = llm.setup_cache()
    yield


app = FastAPI(title="LLM Chatbot", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.allowed_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)
    system_prompt: str | None = Field(default=None, max_length=4000)

    @field_validator("system_prompt")
    @classmethod
    def blank_to_none(cls, v):
        return v or None


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    log.exception("unhandled error")
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


@app.get("/health")
def health():
    keys = len(config.api_keys())
    if not db.ping() or keys == 0:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "keys_configured": keys,
                     "cache_enabled": state["cache_enabled"]},
        )
    return {"status": "ok", "keys_configured": keys, "cache_enabled": state["cache_enabled"]}


@app.post("/chat")
def chat(body: ChatRequest, x_simulate_failure: str | None = Header(default=None)):
    system_prompt = body.system_prompt or db.get_system_prompt(body.session_id) \
        or config.default_system_prompt()
    history = db.get_history(body.session_id)
    messages = [{"role": "system", "content": system_prompt}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": body.message})

    try:
        result = llm.complete(messages, llm.parse_simulation(x_simulate_failure))
    except llm.AllProvidersUnavailable:
        raise HTTPException(status_code=503, detail="all providers unavailable")

    db.save_exchange(body.session_id, body.message, result["reply"], result["metadata"],
                     body.system_prompt)
    return {"session_id": body.session_id, "reply": result["reply"],
            "metadata": result["metadata"]}


@app.get("/sessions/{session_id}/messages")
def session_messages(session_id: str):
    messages = db.get_history(session_id)
    if not messages:
        raise HTTPException(status_code=404, detail="session not found")
    slim = []
    for m in messages:
        item = {"role": m["role"], "content": m["content"]}
        if "metadata" in m:
            md = m["metadata"]
            item["metadata"] = {
                "resolution_source": md.get("resolution_source"),
                "input_tokens": md.get("input_tokens"),
                "output_tokens": md.get("output_tokens"),
            }
        slim.append(item)
    return {"session_id": session_id, "messages": slim}
