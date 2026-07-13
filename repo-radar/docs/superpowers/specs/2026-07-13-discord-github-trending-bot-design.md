# Discord GitHub Trending Bot — Design

**Date:** 2026-07-13
**Status:** Approved

## Goal
A Discord bot that acts as an assistant to discover "interesting" GitHub repositories by
surfacing trending/popular repos and allowing keyword search, presented as rich repo cards.

## Decisions (from brainstorming)
- **Search mode:** Trending / discover (not keyword-only, not recommendations).
- **Stack:** Python 3.11+ using `discord.py` (slash commands) and `requests`.
- **Interaction:** Slash commands that return repo cards (embeds).
- **Data source:** Official GitHub Search API (no scraping, no unofficial APIs).
- **Auth:** No GitHub token. Unauthenticated rate limit = 60 requests/hour.

## Architecture
- **main.py** — bot bootstrap, registers slash commands, wires handlers.
- **github_client.py** — wrapper around GitHub Search API (search_repositories).
- **config.py** — loads environment config from `.env` (DISCORD_TOKEN).
- **requirements.txt** — pinned dependencies.
- **.env.example** — documents required env vars.
- **README.md** — setup + run instructions.

No database or persistent storage required.

## Commands
- `/trending [language] [period]`
  - Lists repos created/pushed within `period` (day | week | month, default week),
    sorted by stars descending.
  - Example: `/trending python week`.
- `/search <query> [language] [min_stars]`
  - Keyword search via GitHub Search API.
  - Example: `/search game engine language:rust min_stars:100`.

## Repo Card (Embed)
Each result is a Discord embed with:
- **Title:** repo full name (links to GitHub URL)
- **Description**
- **⭐ Stars**, **Language**, **Forks**, **Updated** date
- Owner avatar (thumbnail)
- Up to **5** results per command invocation.

## Data Flow
1. User issues slash command in Discord.
2. Handler builds a GitHub Search API query:
   `GET https://api.github.com/search/repositories?q=<q>&sort=stars&order=desc`
   - `/trending`: `q = language:X pushed:>YYYY-MM-DD` (date derived from period)
   - `/search`: `q = <query> [language:X] [stars:>=N]`
3. `github_client` performs the request, returns parsed items.
4. Handler builds embeds and replies.

## Error Handling
- Network/HTTP error → friendly user-facing message, no crash.
- Empty results → "No repos found" message.
- Rate limit (HTTP 403 with rate-limit headers) → "GitHub rate limit reached, try again later."
- Invalid period argument → corrected usage hint.

## Testing
- `pytest` test for `github_client` parsing using mocked HTTP responses
  (verify correct field extraction and embed-building inputs).
- Manual smoke test: run bot, invoke `/trending` in a test Discord server.

## Out of Scope (YAGNI)
- Daily auto-posting.
- Watchlists / saved repos.
- GitHub authentication / token support.
- Web UI.
