# Discord GitHub Repo Reviewer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Discord bot that reviews a GitHub repo posted as a link (auto-detected) or via `/review <url>`, using an LLM (OpenRouter) and replying with a summary embed.

**Architecture:** A `discord.py` bot detects `github.com/owner/repo` links in messages and exposes `/review`. It clones the repo to a temp dir, reads a capped slice of source files into one context string, sends it to OpenRouter for a structured JSON review, and renders an embed. Errors at every stage produce a friendly embed and never crash the bot.

**Tech Stack:** Python 3.11+, `discord.py`, `python-dotenv`, `httpx`, `pytest`, `git` (subprocess).

## Global Constraints
- Default LLM model: `tencent/hy3:free` (OpenRouter).
- Config from `.env`: `DISCORD_TOKEN`, `OPENROUTER_API_KEY`, optional `GITHUB_TOKEN`.
- Source file cap: 50 files / 40 KB total concatenated context; truncate remainder with a notice.
- Discord embed field values must be ≤ 1024 chars; trim and mark truncation.
- No new heavy deps beyond `discord.py`, `python-dotenv`, `httpx`, `pytest`.

---

### Task 1: Project setup

**Files:**
- Create: `requirements.txt`
- Create: `README.md`
- Modify: `.gitignore` (append if needed)

**Interfaces:** none yet.

- [ ] **Step 1: Write `requirements.txt`**
```
discord.py>=2.3
python-dotenv>=1.0
httpx>=0.27
pytest>=8.0
```

- [ ] **Step 2: Ensure `.gitignore` ignores deps/test artifacts**
Append if missing:
```
.venv/
__pycache__/
.env
.pytest_cache/
```

- [ ] **Step 3: Write `README.md`**
```markdown
# repo-reviewer

Discord bot that reviews a GitHub repo from a posted link or `/review <url>`.

## Setup
1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in tokens.
4. `python bot.py`

## Usage
- Post any `https://github.com/owner/repo` link in a channel the bot sees.
- Or run `/review <url>`.
```

- [ ] **Step 4: Commit**
```bash
git add requirements.txt README.md .gitignore
git commit -m "chore: project setup and deps"
```

---

### Task 2: Repo URL parsing + fetch with size cap

**Files:**
- Create: `fetch.py`
- Create: `tests/test_fetch.py`

**Interfaces:**
- Consumes: none
- Produces:
  - `parse_repo_url(text: str) -> tuple[str, str, str | None] | None` — returns `(owner, repo, branch)` or `None`.
  - `fetch_repo(url: str, token: str | None = None, max_files: int = 50, max_bytes: int = 40000) -> tuple[str, bool]` — returns `(context, truncated)`.

**Skip rules:** skip dirs `.git`, `node_modules`, `venv`, `.venv`, `__pycache__`, `dist`, `build`, `.idea`, `.vscode`, `target`, `vendor`; skip files with binary-ish extensions (`.png .jpg .jpeg .gif .ico .svg .pdf .zip .gz .tar .tgz .exe .dll .so .o .woff .woff2 .ttf .mp4 .mov .pyc`); skip files > 200 KB.

- [ ] **Step 1: Write the failing tests**
```python
# tests/test_fetch.py
import pytest
from fetch import parse_repo_url, fetch_repo


def test_parse_basic():
    assert parse_repo_url("check https://github.com/owner/repo out") == ("owner", "repo", None)


def test_parse_branch():
    assert parse_repo_url("https://github.com/owner/repo/tree/main") == ("owner", "repo", "main")


def test_parse_none():
    assert parse_repo_url("not a repo link") is None


def test_fetch_truncates_large(tmp_path):
    # build a fake "repo" with many files
    repo = tmp_path / "repo"
    repo.mkdir()
    for i in range(80):
        (repo / f"f{i}.txt").write_text("x" * 2000)
    ctx, truncated = fetch_repo(str(repo), max_files=5, max_bytes=5000)
    assert truncated is True
    assert len(ctx) <= 5000 + 200
```

- [ ] **Step 2: Run tests to verify they fail**
Run: `pytest tests/test_fetch.py -v`
Expected: FAIL (`ImportError: cannot import name 'parse_repo_url'`).

- [ ] **Step 3: Write `fetch.py`**
```python
import os
import re
import subprocess
import tempfile

SKIP_DIRS = {
    ".git", "node_modules", "venv", ".venv", "__pycache__", "dist",
    "build", ".idea", ".vscode", "target", "vendor",
}
SKIP_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".pdf", ".zip",
    ".gz", ".tar", ".tgz", ".exe", ".dll", ".so", ".o", ".woff",
    ".woff2", ".ttf", ".mp4", ".mov", ".pyc",
}
MAX_FILE_BYTES = 200_000
URL_RE = re.compile(r"github\.com/([\w.\-]+)/([\w.\-]+)(?:/tree/([\w.\-]+))?")


def parse_repo_url(text: str):
    m = URL_RE.search(text)
    if not m:
        return None
    owner, repo, branch = m.group(1), m.group(2), m.group(3)
    repo = repo.removesuffix(".git")
    return owner, repo, branch


def _clone(url: str, token: str | None, branch: str | None) -> str:
    dest = tempfile.mkdtemp(prefix="repo-review-")
    auth_url = url
    if token:
        auth_url = url.replace("https://", f"https://{token}@", 1)
    cmd = ["git", "clone", "--depth", "1"]
    if branch:
        cmd += ["--branch", branch]
    cmd += [auth_url, dest]
    subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    return dest


def _read_context(root: str, max_files: int, max_bytes: int) -> tuple[str, bool]:
    parts: list[str] = []
    total = 0
    count = 0
    truncated = False
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in sorted(filenames):
            if count >= max_files:
                truncated = True
                break
            ext = os.path.splitext(fn)[1].lower()
            if ext in SKIP_EXTS:
                continue
            path = os.path.join(dirpath, fn)
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            if size > MAX_FILE_BYTES or size == 0:
                continue
            rel = os.path.relpath(path, root)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    body = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            snippet = f"\n# === {rel} ===\n{body}\n"
            if total + len(snippet) > max_bytes:
                truncated = True
                break
            parts.append(snippet)
            total += len(snippet)
            count += 1
        if truncated:
            break
    return "".join(parts), truncated


def fetch_repo(url: str, token: str | None = None, max_files: int = 50,
               max_bytes: int = 40000) -> tuple[str, bool]:
    branch = None
    parsed = parse_repo_url(url)
    if parsed:
        branch = parsed[2]
    dest = _clone(url, token, branch)
    try:
        context, truncated = _read_context(dest, max_files, max_bytes)
    finally:
        subprocess.run(["rm", "-rf", dest], check=False)
    return context, truncated
```

- [ ] **Step 4: Run tests to verify they pass**
Run: `pytest tests/test_fetch.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add fetch.py tests/test_fetch.py
git commit -m "feat: parse repo URL and clone+cap context fetch"
```

---

### Task 3: OpenRouter LLM review call

**Files:**
- Create: `llm.py`

**Interfaces:**
- Consumes: none
- Produces:
  - `review_repo(context: str, api_key: str, model: str = "tencent/hy3:free", timeout: float = 60.0) -> dict` — returns parsed JSON review with keys `score`, `summary`, `pros`, `cons`, `risks`, `suggestions`.

- [ ] **Step 1: Write `llm.py`**
```python
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
```

- [ ] **Step 2: Smoke test against the API (optional, needs key)**
Run: `OPENROUTER_API_KEY=... python -c "from llm import review_repo; print(review_repo('print(1)', '<key>'))"`
Expected: prints a dict with the six keys.

- [ ] **Step 3: Commit**
```bash
git add llm.py
git commit -m "feat: OpenRouter LLM review client"
```

---

### Task 4: Embed formatter with 1024-char field limit

**Files:**
- Create: `format.py`
- Create: `tests/test_format.py`

**Interfaces:**
- Consumes: `review_repo` output shape (dict).
- Produces:
  - `build_embed(review: dict, repo_url: str, truncated: bool) -> discord.Embed`
  - `error_embed(message: str) -> discord.Embed`

- [ ] **Step 1: Write the failing test**
```python
# tests/test_format.py
from format import _trim, build_embed, error_embed


def test_trim_under_1024():
    assert _trim("x" * 50, 1024) == "x" * 50


def test_trim_over_1024():
    out = _trim("y" * 2000, 1024)
    assert len(out) <= 1024
    assert out.endswith("…")


def test_build_embed_has_fields():
    e = build_embed(
        {"score": 7, "summary": "ok", "pros": ["a"], "cons": ["b"],
         "risks": ["c"], "suggestions": ["d"]},
        "https://github.com/o/r", False,
    )
    assert e.title
    for f in e.fields:
        assert len(f.value) <= 1024


def test_error_embed():
    e = error_embed("boom")
    assert "boom" in e.description
```

- [ ] **Step 2: Run tests to verify they fail**
Run: `pytest tests/test_format.py -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Write `format.py`**
```python
import discord

FIELD_LIMIT = 1024


def _trim(text: str, limit: int = FIELD_LIMIT) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _join(items) -> str:
    if not items:
        return "—"
    if isinstance(items, str):
        return items
    return "\n".join(f"• {i}" for i in items)


def build_embed(review: dict, repo_url: str, truncated: bool) -> discord.Embed:
    e = discord.Embed(
        title=f"Repo Review: {repo_url}",
        color=discord.Color.blurple(),
    )
    score = review.get("score", "N/A")
    e.add_field(name="Score (0-10)", value=str(score), inline=True)
    if truncated:
        e.add_field(name="Note", value="Context truncated (repo too large)", inline=True)
    e.add_field(name="Summary", value=_trim(_join(review.get("summary"))), inline=False)
    e.add_field(name="Pros", value=_trim(_join(review.get("pros"))), inline=False)
    e.add_field(name="Cons", value=_trim(_join(review.get("cons"))), inline=False)
    e.add_field(name="Risks", value=_trim(_join(review.get("risks"))), inline=False)
    e.add_field(name="Suggestions", value=_trim(_join(review.get("suggestions"))), inline=False)
    return e


def error_embed(message: str) -> discord.Embed:
    return discord.Embed(
        title="Review failed",
        description=_trim(message),
        color=discord.Color.red(),
    )
```

- [ ] **Step 4: Run tests to verify they pass**
Run: `pytest tests/test_format.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add format.py tests/test_format.py
git commit -m "feat: Discord embed formatter with field limits"
```

---

### Task 5: Bot wiring

**Files:**
- Create: `bot.py`

**Interfaces:**
- Consumes: `parse_repo_url`, `fetch_repo` (fetch.py), `review_repo` (llm.py), `build_embed`, `error_embed` (format.py).

- [ ] **Step 1: Write `bot.py`**
```python
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from fetch import parse_repo_url, fetch_repo
from llm import review_repo
from format import build_embed, error_embed

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)


async def handle_review(channel, repo_url: str):
    msg = await channel.send("⏳ Cloning repository…")
    try:
        context, truncated = fetch_repo(repo_url, token=os.getenv("GITHUB_TOKEN"))
    except Exception as e:
        await msg.edit(content=None, embed=error_embed(f"Failed to fetch repo: {e}"))
        return
    if not context.strip():
        await msg.edit(content=None, embed=error_embed("No readable source files found."))
        return
    await msg.edit(content="🤖 Analyzing with LLM…")
    try:
        review = review_repo(context, os.getenv("OPENROUTER_API_KEY"))
    except Exception as e:
        await msg.edit(content=None, embed=error_embed(f"LLM error: {e}"))
        return
    await msg.edit(content=None, embed=build_embed(review, repo_url, truncated))


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    parsed = parse_repo_url(message.content)
    if parsed:
        url = f"https://github.com/{parsed[0]}/{parsed[1]}"
        await handle_review(message.channel, url)
    await bot.process_commands(message)


@bot.command()
async def review(ctx, url: str):
    parsed = parse_repo_url(url)
    if not parsed:
        await ctx.send(embed=error_embed("Invalid GitHub repo URL. Expected github.com/owner/repo"))
        return
    repo_url = f"https://github.com/{parsed[0]}/{parsed[1]}"
    await handle_review(ctx.channel, repo_url)


bot.run(os.getenv("DISCORD_TOKEN"))
```

- [ ] **Step 2: Syntax-check the bot**
Run: `python -m py_compile bot.py && echo OK`
Expected: `OK`.

- [ ] **Step 3: Run full test suite**
Run: `pytest -q`
Expected: all pass.

- [ ] **Step 4: Commit**
```bash
git add bot.py
git commit -m "feat: wire Discord bot with auto-detect and /review command"
```

---

### Task 6: Manual integration check

**Files:** none (verification only).

- [ ] **Step 1: Install and configure**
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill DISCORD_TOKEN, OPENROUTER_API_KEY, optional GITHUB_TOKEN
```

- [ ] **Step 2: Run the bot**
Run: `python bot.py`
Expected: bot starts, no traceback.

- [ ] **Step 3: Verify in Discord**
- Post `https://github.com/pallets/flask` in a channel the bot sees → bot replies with a review embed.
- Run `/review https://github.com/psf/requests` → same.
- Post a non-repo link → no review triggered.
- (Optional) Post a huge repo → embed shows "Context truncated" note.

- [ ] **Step 4: Commit nothing** (verification only). If fixes needed, commit them with descriptive messages.
