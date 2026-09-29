"""LLM calls through Unity AI Gateway (OpenAI-compatible). Falls back to /serving-endpoints if the Gateway URL fails."""
from __future__ import annotations

import json
import logging

import httpx
from openai import OpenAI

from . import config

log = logging.getLogger("lochard.llm")


def _strip_strict(request: httpx.Request) -> None:
    """Claude via the Gateway rejects OpenAI's tool 'strict' flag – drop it on the wire."""
    if b"/chat/completions" not in request.url.path.encode():
        return
    try:
        body = json.loads(request.content or b"{}")
    except Exception:  # noqa: BLE001
        return
    changed = False
    for tool in body.get("tools") or []:
        if isinstance(tool, dict):
            changed |= tool.pop("strict", None) is not None
            fn = tool.get("function")
            if isinstance(fn, dict):
                changed |= fn.pop("strict", None) is not None
    if changed:
        data = json.dumps(body).encode()
        request.stream = httpx.ByteStream(data)
        request.headers["content-length"] = str(len(data))


def _client(base_url: str, timeout_s: float = 90) -> OpenAI:
    token = config.app_client().config.authenticate()["Authorization"].split(" ", 1)[1]
    return OpenAI(api_key=token, base_url=base_url.rstrip("/"),
                  http_client=httpx.Client(event_hooks={"request": [_strip_strict]}, timeout=httpx.Timeout(timeout_s, connect=20)))


def chat(messages: list[dict], model: str | None = None, max_tokens: int = 2000, user: str | None = None,
         temperature: float = 0.2, timeout_s: float = 90) -> tuple[str, str, str]:
    """Returns (text, model, route) where route is 'ai-gateway' or 'serving-endpoints'.
    `user` is accepted for call-site readability but not forwarded: /serving-endpoints rejects extra fields."""
    model = model or config.LLM_ECONOMY_MODEL
    last = None
    routes = [("ai-gateway", config.AI_GATEWAY_URL, model),
              ("serving-endpoints", f"{config.host()}/serving-endpoints", config.LLM_FALLBACK_ENDPOINT)]
    for route, base, m in routes:
        try:
            # temperature omitted: Opus 5.5 / Sonnet 5 (routed via lochard_assistant) reject it
            r = _client(base, timeout_s).chat.completions.create(model=m, messages=messages, max_tokens=max_tokens)
            content = r.choices[0].message.content
            if isinstance(content, list):  # reasoning models (e.g. Sonnet 5) return content blocks
                content = "".join(b.get("text", "") if isinstance(b, dict) else getattr(b, "text", "")
                                  for b in content
                                  if (b.get("type") if isinstance(b, dict) else getattr(b, "type", "")) in ("text", "output_text"))
            return content or "", m, route
        except Exception as e:  # noqa: BLE001
            log.warning("LLM via %s failed: %s", route, e)
            last = e
    raise RuntimeError(f"LLM unavailable: {last}")
