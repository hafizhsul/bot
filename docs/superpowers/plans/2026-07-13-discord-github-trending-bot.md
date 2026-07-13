# Discord GitHub Trending Bot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Discord bot that surfaces trending/popular GitHub repos and lets users search, presenting results as rich repo cards (embeds).

**Architecture:** A `discord.py` bot registers two slash commands (`/trending`, `/search`). Each command calls a `github_client` wrapper around the official GitHub Search API (unauthenticated, 60 req/hr), which returns normalized repo dicts. `main.py` turns those dicts into Discord embeds and replies. No database or persistent storage.

**Tech Stack:** Python 3.11+, `discord.py` (>=2.3.0), `requests` (>=2.31.0), `python-dotenv`, `pytest` for tests.

## Global Constraints

- No GitHub token: unauthenticated GitHub Search API, 60 requests/hour hard limit.
- On HTTP 403 → treat as rate limit, show friendly message (do not crash).
- On other non-200 → show friendly GitHub error message (do not crash).
- Max 5 repo cards per command invocation.
- `/trending` period must be one of: `day`, `week` (default), `month`.
- All config via `.env`; required var `DISCORD_TOKEN`.
- No database, no scraping, no unofficial APIs (per spec).

---

### Task 1: Project scaffold (deps, config, env example)

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `config.py`

**Interfaces:** None (foundational).
**Produces:** `config.DISCORD_TOKEN` (str) consumed by Task 3; dependency list for install.

- [ ] **Step 1: Create `requirements.txt`**

```
discord.py>=2.3.0
requests>=2.31.0
python-dotenv>=1.0.0
pytest>=7.4.0
```

- [ ] **Step 2: Create `.env.example`**

```
# Discord bot token from https://discord.com/developers/applications
DISCORD_TOKEN=your_discord_bot_token_here
```

- [ ] **Step 3: Create `config.py`**

```python
import os

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
```

- [ ] **Step 4: Install dependencies**

Run: `pip install -r requirements.txt`
Expected: packages install without error.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .env.example config.py
git commit -m "chore: scaffold project deps and config"
```

---

### Task 2: GitHub Search API client (TDD)

**Files:**
- Create: `github_client.py`
- Create: `tests/test_github_client.py`

**Interfaces:**
- Consumes: nothing external beyond `requests`.
- Produces:
  - `build_trending_query(language: str | None, period: str) -> str` (raises `ValueError` on bad period)
  - `build_search_query(query: str, language: str | None, min_stars: int | None) -> str`
  - `search_repositories(query: str, per_page: int = 5) -> list[dict]` (raises `GitHubRateLimitError` on 403, `GitHubAPIError` otherwise non-200)
  - `GitHubRateLimitError`, `GitHubAPIError` exception classes

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_github_client.py
import github_client
from unittest import mock


def test_build_trending_query_default_week():
    q = github_client.build_trending_query(None, "week")
    assert "pushed:>" in q
    assert "language:" not in q


def test_build_trending_query_with_language():
    q = github_client.build_trending_query("python", "day")
    assert "language:python" in q
    assert "pushed:>" in q


def test_build_trending_query_invalid_period():
    try:
        github_client.build_trending_query(None, "year")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_build_search_query():
    q = github_client.build_search_query("game engine", "rust", 100)
    assert "game engine" in q
    assert "language:rust" in q
    assert "stars:>=100" in q


def test_parse_item():
    item = {
        "full_name": "octocat/hello",
        "html_url": "https://github.com/octocat/hello",
        "description": "A repo",
        "stargazers_count": 42,
        "language": "Python",
        "forks_count": 3,
        "updated_at": "2026-01-01T00:00:00Z",
        "owner": {"avatar_url": "http://img"},
    }
    p = github_client._parse_item(item)
    assert p["name"] == "octocat/hello"
    assert p["url"] == "https://github.com/octocat/hello"
    assert p["stars"] == 42
    assert p["language"] == "Python"
    assert p["forks"] == 3
    assert p["updated_at"] == "2026-01-01T00:00:00Z"
    assert p["avatar"] == "http://img"


def test_search_repositories_success():
    fake = mock.Mock()
    fake.status_code = 200
    fake.json.return_value = {
        "items": [
            {
                "full_name": "a/b",
                "html_url": "u",
                "description": "d",
                "stargazers_count": 1,
                "language": "Python",
                "forks_count": 0,
                "updated_at": "x",
                "owner": {"avatar_url": "y"},
            }
        ]
    }
    with mock.patch("github_client.requests.get", return_value=fake):
        items = github_client.search_repositories("q")
    assert len(items) == 1
    assert items[0]["name"] == "a/b"


def test_search_repositories_rate_limit():
    fake = mock.Mock()
    fake.status_code = 403
    with mock.patch("github_client.requests.get", return_value=fake):
        try:
            github_client.search_repositories("q")
            assert False, "expected GitHubRateLimitError"
        except github_client.GitHubRateLimitError:
            pass


def test_search_repositories_api_error():
    fake = mock.Mock()
    fake.status_code = 500
    with mock.patch("github_client.requests.get", return_value=fake):
        try:
            github_client.search_repositories("q")
            assert False, "expected GitHubAPIError"
        except github_client.GitHubAPIError:
            pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_github_client.py -v`
Expected: FAIL (module `github_client` does not exist).

- [ ] **Step 3: Write minimal implementation**

```python
# github_client.py
from datetime import datetime, timedelta

import requests

API_URL = "https://api.github.com/search/repositories"

PERIOD_DAYS = {"day": 1, "week": 7, "month": 30}


class GitHubRateLimitError(Exception):
    """Raised when GitHub returns HTTP 403 (rate limit exceeded)."""


class GitHubAPIError(Exception):
    """Raised when GitHub returns a non-200, non-403 status."""


def build_trending_query(language: str | None, period: str) -> str:
    if period not in PERIOD_DAYS:
        raise ValueError("period must be one of: day, week, month")
    since = (datetime.utcnow() - timedelta(days=PERIOD_DAYS[period])).strftime(
        "%Y-%m-%d"
    )
    query = f"pushed:>{since}"
    if language:
        query += f" language:{language}"
    return query


def build_search_query(
    query: str, language: str | None, min_stars: int | None
) -> str:
    q = query
    if language:
        q += f" language:{language}"
    if min_stars:
        q += f" stars:>={min_stars}"
    return q


def _parse_item(item: dict) -> dict:
    return {
        "name": item["full_name"],
        "url": item["html_url"],
        "description": item.get("description") or "No description",
        "stars": item["stargazers_count"],
        "language": item.get("language") or "Unknown",
        "forks": item["forks_count"],
        "updated_at": item["updated_at"],
        "avatar": item["owner"]["avatar_url"],
    }


def search_repositories(query: str, per_page: int = 5) -> list[dict]:
    params = {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": per_page,
    }
    headers = {"Accept": "application/vnd.github+json"}
    resp = requests.get(API_URL, params=params, headers=headers, timeout=10)
    if resp.status_code == 403:
        raise GitHubRateLimitError()
    if resp.status_code != 200:
        raise GitHubAPIError(f"GitHub API returned status {resp.status_code}")
    data = resp.json()
    return [_parse_item(i) for i in data.get("items", [])]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_github_client.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add github_client.py tests/test_github_client.py
git commit -m "feat: add GitHub Search API client with tests"
```

---

### Task 3: Discord bot with slash commands and repo cards

**Files:**
- Create: `main.py`
- Modify: (none)

**Interfaces:**
- Consumes: `github_client.build_trending_query`, `github_client.build_search_query`, `github_client.search_repositories`, `github_client.GitHubRateLimitError`, `github_client.GitHubAPIError`; `config.DISCORD_TOKEN`.
- Produces: runnable bot (`python main.py`) exposing `/trending` and `/search`.

- [ ] **Step 1: Create `main.py`**

```python
import discord
from discord import app_commands
from discord.ext import commands

import github_client
from config import DISCORD_TOKEN

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)


def build_embed(repo: dict) -> discord.Embed:
    embed = discord.Embed(
        title=repo["name"],
        url=repo["url"],
        description=repo["description"],
        color=discord.Color.blurple(),
    )
    embed.set_thumbnail(url=repo["avatar"])
    embed.add_field(name="\u2b50 Stars", value=str(repo["stars"]), inline=True)
    embed.add_field(name="\U0001f500 Forks", value=str(repo["forks"]), inline=True)
    embed.add_field(name="\U0001f4be Language", value=repo["language"], inline=True)
    embed.set_footer(text=f"Updated: {repo['updated_at']}")
    return embed


@bot.event
async def on_ready() -> None:
    await bot.tree.sync()
    print(f"Logged in as {bot.user} (id: {bot.user.id})")


@bot.tree.command(name="trending", description="Show trending GitHub repositories")
@app_commands.describe(
    language="Optional language filter, e.g. python",
    period="day, week (default), or month",
)
async def trending(
    interaction: discord.Interaction,
    language: str | None = None,
    period: str = "week",
) -> None:
    await interaction.response.defer()
    try:
        query = github_client.build_trending_query(language, period)
        repos = github_client.search_repositories(query)
    except ValueError:
        await interaction.followup.send(
            "Invalid period. Use day, week, or month."
        )
        return
    except github_client.GitHubRateLimitError:
        await interaction.followup.send(
            "GitHub rate limit reached, try again later."
        )
        return
    except github_client.GitHubAPIError as exc:
        await interaction.followup.send(f"GitHub error: {exc}")
        return

    if not repos:
        await interaction.followup.send("No repositories found.")
        return
    for repo in repos:
        await interaction.followup.send(embed=build_embed(repo))


@bot.tree.command(name="search", description="Search GitHub repositories")
@app_commands.describe(
    query="Search keywords",
    language="Optional language filter, e.g. rust",
    min_stars="Optional minimum star count",
)
async def search(
    interaction: discord.Interaction,
    query: str,
    language: str | None = None,
    min_stars: int | None = None,
) -> None:
    await interaction.response.defer()
    try:
        q = github_client.build_search_query(query, language, min_stars)
        repos = github_client.search_repositories(q)
    except github_client.GitHubRateLimitError:
        await interaction.followup.send(
            "GitHub rate limit reached, try again later."
        )
        return
    except github_client.GitHubAPIError as exc:
        await interaction.followup.send(f"GitHub error: {exc}")
        return

    if not repos:
        await interaction.followup.send("No repositories found.")
        return
    for repo in repos:
        await interaction.followup.send(embed=build_embed(repo))


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN is not set. Add it to your .env file.")
    bot.run(DISCORD_TOKEN)
```

- [ ] **Step 2: Verify it imports / no syntax errors**

Run: `python -c "import main"`
Expected: no output, no error (token check only runs under `bot.run`).

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add Discord bot with /trending and /search commands"
```

---

### Task 4: README and manual smoke test

**Files:**
- Create: `README.md`

**Interfaces:** Documents setup from Tasks 1–3.
**Produces:** end-user run instructions; final manual verification.

- [ ] **Step 1: Create `README.md`**

```markdown
# Discord GitHub Trending Bot

A Discord bot that surfaces trending and searchable GitHub repositories as rich cards.

## Setup

1. Create a Discord bot at https://discord.com/developers/applications
   and copy the token.
2. Invite the bot to your server with the `applications.commands` and
   `bot` scopes.
3. Copy `.env.example` to `.env` and set `DISCORD_TOKEN`.
4. Install dependencies:

   pip install -r requirements.txt

5. Run:

   python main.py

## Commands

- `/trending [language] [period]` — trending repos (period: day, week, month).
  Example: `/trending python week`
- `/search <query> [language] [min_stars]` — keyword search.
  Example: `/search game engine language:rust min_stars:100`

## Notes

- Uses the official GitHub Search API unauthenticated (60 requests/hour).
  If you hit the limit, wait or add a token later.
- Shows up to 5 results per command.
```

- [ ] **Step 2: Manual smoke test**

Run:
```bash
cp .env.example .env   # then edit .env and paste your real DISCORD_TOKEN
python main.py
```
In Discord, run `/trending python week` and `/search game engine language:rust`.
Expected: bot replies with up to 5 repo cards; rate-limit/empty states show friendly messages.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup and usage"
```
