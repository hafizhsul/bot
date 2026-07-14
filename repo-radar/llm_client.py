# llm_client.py
import json
import re

import requests

import config

MODEL = "openrouter/tencent/hy3:free"
API_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = (
    "You convert a user's natural-language interest into GitHub repository "
    "search queries. Return ONLY a JSON array of 1 to 5 short search query "
    "strings (a few keywords each, e.g. 'pdf tools', 'ai agent skills'). "
    "No explanations, no markdown."
)


class LLMError(Exception):
    """Raised when the LLM call fails or returns unusable output."""

    def __init__(self, message: str, kind: str = "error"):
        super().__init__(message)
        self.kind = kind


def _extract_json(text: str):
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text.strip()
    return json.loads(candidate)


def suggest_queries(interest: str) -> list[str]:
    if not config.OPENROUTER_API_KEY:
        raise LLMError("OPENROUTER_API_KEY is not set", kind="missing_key")
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": interest},
        ],
    }
    try:
        resp = requests.post(API_URL, headers=headers, json=body, timeout=20)
    except requests.exceptions.RequestException as e:
        raise LLMError(f"network error: {e}", kind="api")
    if resp.status_code != 200:
        raise LLMError(f"OpenRouter returned status {resp.status_code}", kind="api")
    try:
        content = resp.json()["choices"][0]["message"]["content"]
        data = _extract_json(content)
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        raise LLMError(f"invalid response: {e}", kind="bad_output")
    if not isinstance(data, list) or not data:
        raise LLMError("response was not a non-empty list", kind="empty")
    if not all(isinstance(q, str) for q in data):
        raise LLMError("response was not a list of strings", kind="bad_output")
    return [q for q in data][:5]
