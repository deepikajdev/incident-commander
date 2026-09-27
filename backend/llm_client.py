"""
Thin wrapper around Groq's OpenAI-compatible chat completions endpoint.
Reads GROQ_API_KEY from the environment (or a .env file via python-dotenv).
Includes one automatic retry when JSON parsing fails.
"""
import json
import os
import re

import httpx
from dotenv import load_dotenv

load_dotenv()

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
_TIMEOUT = 60


def _get_api_key() -> str:
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set. Add it to backend/.env or the environment.")
    return key


def chat(system: str, user: str, temperature: float = 0.2) -> str:
    """Send a chat request and return the raw assistant message string."""
    headers = {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": _MODEL,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    resp = httpx.post(_GROQ_URL, json=payload, headers=headers, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _extract_json(text: str) -> dict | list:
    """Pull the first JSON object or array out of a text that may contain prose."""
    # Try bare parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find the outermost { … } or [ … ]
    for start_char, end_char in (("{", "}"), ("[", "]")):
        start = text.find(start_char)
        end = text.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    raise ValueError(f"No valid JSON found in LLM response:\n{text[:500]}")


def chat_json(system: str, user: str, temperature: float = 0.2) -> dict | list:
    """
    Send a chat request and return a parsed JSON object/array.
    Retries once if the first response cannot be parsed as JSON,
    appending an explicit reminder to return only JSON.
    Also retries once on 429 rate-limit with a 10-second back-off.
    """
    import time

    for attempt in range(2):
        retry_hint = (
            ""
            if attempt == 0
            else "\n\nIMPORTANT: Your previous response could not be parsed as JSON. "
                 "Respond with ONLY valid JSON — no markdown fences, no prose."
        )
        try:
            text = chat(system, user + retry_hint, temperature=temperature)
        except Exception as exc:
            # Retry once on rate-limit
            if attempt == 0 and "429" in str(exc):
                time.sleep(10)
                continue
            raise
        try:
            return _extract_json(text)
        except ValueError:
            if attempt == 1:
                raise
    raise RuntimeError("unreachable")
