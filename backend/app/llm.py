"""LiteLLM gateway: key pool, automatic failover and response caching."""
import logging
import time

import litellm
from litellm.caching import Cache

from . import config

log = logging.getLogger("llm")
litellm.drop_params = True
litellm.telemetry = False
litellm.suppress_debug_info = True


class AllProvidersUnavailable(Exception):
    pass


class SimulatedProviderError(Exception):
    def __init__(self, status: int):
        super().__init__(f"simulated provider status {status}")
        self.status_code = status


def setup_cache() -> bool:
    """Enable LiteLLM's built-in cache. Disk cache survives restarts; falls back to memory."""
    try:
        if config.cache_type() == "disk":
            litellm.cache = Cache(type="disk", disk_cache_dir=config.cache_dir())
        else:
            litellm.cache = Cache(type="local")
    except Exception as exc:  # e.g. unwritable directory
        log.warning("disk cache unavailable (%s), using in-memory cache", type(exc).__name__)
        litellm.cache = Cache(type="local")
    return litellm.cache is not None


def parse_simulation(header: str | None) -> dict[str, int]:
    """'key_1=429,key_2=500' or '*=429' -> {'key_1': 429, ...}. Ignores malformed pairs."""
    result: dict[str, int] = {}
    if not header or not config.simulation_enabled():
        return result
    for part in header.split(","):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k, v = k.strip(), v.strip()
        if v in {"429", "500", "502", "503"} and k:
            result[k] = int(v)
    return result


def complete(messages: list[dict], simulate: dict[str, int]) -> dict:
    keys = config.api_keys()
    model = config.model()
    simulating = bool(simulate)
    failures = 0
    start = time.perf_counter()

    for idx, key in enumerate(keys, start=1):
        key_id = f"key_{idx}"
        try:
            status = simulate.get(key_id) or simulate.get("*")
            if status:
                raise SimulatedProviderError(status)
            kwargs = dict(
                model=model,
                messages=messages,
                api_key=key,
                num_retries=0,
                timeout=30,
                max_tokens=2048,
                # simulated requests must hit a real provider, never the cache
                caching=not simulating,
            )
            mock = config.mock_response()
            if mock:
                kwargs["mock_response"] = mock
            resp = litellm.completion(**kwargs)
            text = (resp.choices[0].message.content or "").strip()
            if not text:
                raise ValueError("empty completion")
            cache_hit = bool(getattr(resp, "_hidden_params", {}).get("cache_hit"))
            usage = resp.usage
            return {
                "reply": text,
                "metadata": {
                    "resolution_source": "LLM_CACHE" if cache_hit else "LIVE_INFERENCE",
                    "model": model,
                    "latency_ms": int((time.perf_counter() - start) * 1000),
                    "input_tokens": int(usage.prompt_tokens or 0),
                    "output_tokens": int(usage.completion_tokens or 0),
                    "key_id": None if cache_hit else key_id,
                    "fallback_attempts": 0 if cache_hit else failures,
                },
            }
        except Exception as exc:  # 429, quota, 5xx, auth, timeout: try the next key
            failures += 1
            log.warning("%s failed: %s (status=%s)", key_id, type(exc).__name__,
                        getattr(exc, "status_code", "n/a"))
            continue

    raise AllProvidersUnavailable()
