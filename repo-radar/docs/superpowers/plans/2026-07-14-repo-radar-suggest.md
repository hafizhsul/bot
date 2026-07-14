# Repo Radar — Interest-Based Suggestions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an LLM-powered feature so users get GitHub repo recommendations from a natural-language interest, via a `/suggest` command and a passive auto mode.

**Architecture:** `llm_client.py` calls OpenRouter (`openrouter/tencent/hy3:free`) to turn an interest string into GitHub search queries; `main.py` adds a `/suggest` slash command and an `on_message` listener (triggered by mention or keywords) that reuse the existing `github_client.search_repositories` + `build_embed` to post repo cards.

**Tech Stack:** Python 3.11+, `discord.py`, `requests`, `python-dotenv`, OpenRouter chat completions API, `pytest`.

## Global Constraints

- LLM model is fixed: `openrouter/tencent/hy3:free` (per spec).
- No channel-history scanning; interest comes only from user text (command arg or trigger message). Per spec.
- Auto mode triggers ONLY on bot mention OR trigger words (recommend/suggest/find me/repos for/show me); never on its own messages, slash commands, or normal chatter. Per spec.
- Reuse existing `github_client.search_repositories` and `build_embed`; no DB. Per spec.
- Max ~10 repos per request (default 5). Per spec.
- All config via `.env`; required new var `OPENROUTER_API_KEY`. Per spec.

---

### Task 1: Config — add OPENROUTER_API_KEY

**Files:**
- Modify: `config.py`
- Modify: `.env.example`

**Interfaces:** None (foundational). Produces `config.OPENROUTER_API_KEY` consumed by Task 2.

- [ ] **Step 1: Edit `config.py`** — add the new var after `DISCORD_TOKEN`:

```python
import os

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
```

- [ ] **Step 2: Edit `.env.example`** — add the new var:

```
# Discord bot token from https://discord.com/developers/applications
DISCORD_TOKEN=your_discord_bot_token_here
# OpenRouter API key from https://openrouter.ai/keys (used for /suggest)
OPENROUTER_API_KEY=your_openrouter_api_key_here
```

- [ ] **Step 3: Verify import**

Run: `cd repo-radar && .venv/bin/python -c "import config; print(config.OPENROUTER_API_KEY == '')"`
Expected: `True` (no .env key set yet).

- [ ] **Step 4: Commit**

```bash
git add config.py .env.example
git commit -m "chore: add OPENROUTER_API_KEY config"
```

---

### Task 2: LLM client (TDD)

**Files:**
- Create: `llm_client.py`
- Create: `tests/test_llm_client.py`

**Interfaces:**
- Consumes: `config.OPENROUTER_API_KEY`.
- Produces:
  - `MODEL: str` (value `"openrouter/tencent/hy3:free"`)
  - `LLMError` exception class
  - `suggest_queries(interest: str) -> list[str]` — raises `LLMError` on missing key / non-200 / network error / invalid-or-empty JSON.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_llm_client.py
import json
from unittest import mock

import llm_client


def _fake_resp(status, content):
    fake = mock.Mock()
    fake.status_code = status
    fake.json.return_value = {
        "choices": [{"message": {"content": content}}]
    }
    return fake


def test_suggest_queries_valid_array():
    resp = _fake_resp(200, '["pdf tools", "document automation"]')
    with mock.patch("llm_client.requests.post", return_value=resp):
        queries = llm_client.suggest_queries("professional PDF tools")
    assert queries == ["pdf tools", "document automation"]


def test_suggest_queries_fenced_json():
    resp = _fake_resp(200, '```json\n["ai agent skills", "llm orchestration"]\n```')
    with mock.patch("llm_client.requests.post", return_value=resp):
        queries = llm_client.suggest_queries("skills agent")
    assert queries == ["ai agent skills", "llm orchestration"]


def test_suggest_queries_non_200():
    resp = _fake_resp(500, "error")
    with mock.patch("llm_client.requests.post", return_value=resp):
        try:
            llm_client.suggest_queries("x")
            assert False, "expected LLMError"
        except llm_client.LLMError:
            pass


def test_suggest_queries_invalid_json():
    resp = _fake_resp(200, "not json at all")
    with mock.patch("llm_client.requests.post", return_value=resp):
        try:
            llm_client.suggest_queries("x")
            assert False, "expected LLMError"
        except llm_client.LLMError:
            pass


def test_suggest_queries_missing_key():
    with mock.patch("config.OPENROUTER_API_KEY", ""):
        try:
            llm_client.suggest_queries("x")
            assert False, "expected LLMError"
        except llm_client.LLMError:
            pass


def test_suggest_queries_empty_array():
    resp = _fake_resp(200, "[]")
    with mock.patch("llm_client.requests.post", return_value=resp):
        try:
            llm_client.suggest_queries("x")
            assert False, "expected LLMError"
        except llm_client.LLMError:
            pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd repo-radar && .venv/bin/python -m pytest tests/test_llm_client.py -v`
Expected: FAIL (module `llm_client` does not exist).

- [ ] **Step 3: Write minimal implementation**

```python
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


def _extract_json(text: str):
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text.strip()
    return json.loads(candidate)


def suggest_queries(interest: str) -> list[str]:
    if not config.OPENROUTER_API_KEY:
        raise LLMError("OPENROUTER_API_KEY is not set")
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
        raise LLMError(f"network error: {e}")
    if resp.status_code != 200:
        raise LLMError(f"OpenRouter returned status {resp.status_code}")
    try:
        content = resp.json()["choices"][0]["message"]["content"]
        data = _extract_json(content)
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        raise LLMError(f"invalid response: {e}")
    if not isinstance(data, list) or not data:
        raise LLMError("response was not a non-empty list")
    if not all(isinstance(q, str) for q in data):
        raise LLMError("response was not a list of strings")
    return [q for q in data][:5]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd repo-radar && .venv/bin/python -m pytest tests/test_llm_client.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add llm_client.py tests/test_llm_client.py
git commit -m "feat: add OpenRouter LLM client for interest-to-query conversion"
```

---

### Task 3: `/suggest` command + auto mode

**Files:**
- Modify: `main.py`

**Interfaces:**
- Consumes: `llm_client.suggest_queries`, `llm_client.LLMError`, `github_client.search_repositories`, `github_client.GitHubRateLimitError`, `github_client.GitHubAPIError`, `build_embed`.
- Produces: runnable bot with `/suggest <interest> [count]` and an `on_message` auto-mode listener.

- [ ] **Step 1: Add imports and a shared helper at the top of `main.py` (after existing imports)**

Add after `import github_client`:
```python
import llm_client
```

Add this helper after `build_embed`:
```python
TRIGGER_WORDS = ("recommend", "suggest", "find me", "repos for", "show me")


async def gather_suggestions(interest: str, count: int = 5) -> list[dict]:
    """Turn an interest into GitHub repo dicts via the LLM + Search API."""
    queries = llm_client.suggest_queries(interest)
    repos: list[dict] = []
    for q in queries:
        repos.extend(github_client.search_repositories(q))
        if len(repos) >= count:
            break
    return repos[:count]
```

- [ ] **Step 2: Add the `/suggest` slash command (after the existing `search` command)**

```python
@bot.tree.command(name="suggest", description="Recommend GitHub repos for a natural-language interest")
@app_commands.describe(
    interest="What you're interested in, e.g. 'professional PDF tools' or 'trending skills agent'",
    count="Number of repos to show (default 5, max 10)",
)
async def suggest(
    interaction: discord.Interaction,
    interest: str,
    count: int = 5,
) -> None:
    count = max(1, min(count, 10))
    await interaction.response.defer()
    try:
        repos = await gather_suggestions(interest, count)
    except llm_client.LLMError as exc:
        await interaction.followup.send(f"Suggestion error: {exc}")
        return
    except github_client.GitHubRateLimitError:
        await interaction.followup.send("GitHub rate limit reached, try again later.")
        return
    except github_client.GitHubAPIError as exc:
        await interaction.followup.send(f"GitHub error: {exc}")
        return

    if not repos:
        await interaction.followup.send(
            "No repositories found. Try a different interest."
        )
        return
    for repo in repos:
        await interaction.followup.send(embed=build_embed(repo))
```

- [ ] **Step 3: Add the `on_message` auto-mode listener (after the `search` command, before `if __name__`)**

```python
@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author == bot.user:
        return
    if message.content.startswith("/"):
        return
    text = message.content
    mentioned = bot.user in message.mentions
    has_trigger = any(word in text.lower() for word in TRIGGER_WORDS)
    if not (mentioned or has_trigger):
        return

    interest = text
    if mentioned:
        interest = text.replace(f"<@{bot.user.id}>", "").replace(
            f"<@!{bot.user.id}>", ""
        )
    interest = interest.strip()
    if not interest:
        return

    await message.channel.send("🔎 Looking for repos based on your interest...")
    try:
        repos = await gather_suggestions(interest)
    except llm_client.LLMError as exc:
        await message.channel.send(f"Suggestion error: {exc}")
        return
    except github_client.GitHubRateLimitError:
        await message.channel.send("GitHub rate limit reached, try again later.")
        return
    except github_client.GitHubAPIError as exc:
        await message.channel.send(f"GitHub error: {exc}")
        return

    if not repos:
        await message.channel.send("No repositories found. Try a different interest.")
        return
    for repo in repos:
        await message.channel.send(embed=build_embed(repo))
```

- [ ] **Step 4: Verify imports / syntax**

Run: `cd repo-radar && .venv/bin/python -c "import main; print('ok')"`
Expected: `ok`.

- [ ] **Step 5: Run the full test suite**

Run: `cd repo-radar && .venv/bin/python -m pytest -q`
Expected: all PASS (prior 12 + new 6).

- [ ] **Step 6: Commit**

```bash
git add main.py
git commit -m "feat: add /suggest command and auto-mode interest suggestions"
```

---

### Task 4: README

**Files:**
- Modify: `README.md`

**Interfaces:** Documents the new feature for users.

- [ ] **Step 1: Update `README.md`** — add to the Commands section and Notes:

```markdown
- `/suggest <interest> [count]` — recommend repos from a natural-language
  interest, e.g. `/suggest professional PDF tools`. Requires `OPENROUTER_API_KEY`.
- **Auto mode:** mention the bot or include words like "recommend"/"suggest"/
  "find me"/"repos for"/"show me" in a message and it will suggest repos.

## Environment

Requires a second env var for suggestions:

- `OPENROUTER_API_KEY` — get one at https://openrouter.ai/keys (free tier works
  with the `openrouter/tencent/hy3:free` model).
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document /suggest command and auto mode"
```
