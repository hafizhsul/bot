import json
import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "tencent/hy3:free"

SYSTEM_PROMPT = (
    "You are a senior software engineer performing a concise code review of a "
    "GitHub repository. You will receive concatenated source files. Respond with "
    "ONLY a JSON object, no markdown, with these keys: "
    "score (integer 0-10), summary (string), pros (list of strings), "
    "cons (list of strings), risks (list of strings), suggestions (list of strings)."
)


def review_repo(context: str, api_key: str, model: str = DEFAULT_MODEL,
                timeout: float = 60.0) -> dict:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Repository files:\n\n{context}"},
        ],
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = httpx.post(OPENROUTER_URL, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    content = content.strip()
    if content.startswith("```"):
        content = content.split("```", 2)[1]
        if content.startswith("json"):
            content = content[4:]
    return json.loads(content)
