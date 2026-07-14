# Discord GitHub Repo Reviewer — Design

Date: 2026-07-14

## Goal
A Discord bot that reviews a GitHub repository when a user posts a repo link
(any message) or runs `/review <url>`. The review is produced by an LLM via
OpenRouter and shown as a Discord embed.

## Stack
- Python 3.11+
- `discord.py` — Discord client + slash commands
- `python-dotenv` — load `.env`
- `httpx` — OpenRouter calls (OpenAI-compatible chat completions)
- `git` via subprocess — clone repos (no GitPython needed)
- `pytest` — tests (already set up in this repo)

## Components
- `bot.py` — Discord client. Auto-detects `github.com/<owner>/<repo>` in any
  message; also exposes `/review <url>` slash command. Orchestrates flow.
- `fetch.py` — clone repo to a temp dir, walk source files, skip `.git`,
  `node_modules`, vendored dirs, and binary files. Cap at ~50 files / ~40 KB
  total concatenated; truncate remainder with a notice.
- `llm.py` — OpenRouter client. System prompt: "you are a senior code reviewer".
  Returns structured review as JSON: `score` (0-10), `summary`, `pros`,
  `cons`, `risks`, `suggestions`.
- `format.py` — turn LLM JSON into a Discord embed; keep every field under
  2000 chars, split if needed.

## Config (`.env`, already present)
- `DISCORD_TOKEN`
- `OPENROUTER_API_KEY`
- `GITHUB_TOKEN` (optional; enables private repos, raises rate limit)

## Flow
1. Detect repo URL (message scan or `/review`).
2. Parse `owner/repo` (+ optional branch).
3. `fetch.py` clones + reads files → context string.
4. `llm.py` calls OpenRouter with context → review JSON.
5. `format.py` builds embed → bot replies.

## Error handling
- Bad/non-GitHub URL → short error embed.
- Clone failure / not found → error embed.
- Repo exceeds size cap → truncate + notice in embed.
- LLM timeout/error → friendly error embed; never crash the bot.
- Unknown command / no URL → help hint.

## Testing
- `tests/test_fetch.py` — URL parsing + size-cap behavior (no network: use a
  local temp tree fixture).
- `tests/test_format.py` — embed field truncation under 2000 chars.

## Out of scope (YAGNI)
- Persistence / history
- Multi-repo batch
- Per-user settings
- Caching across reviews
