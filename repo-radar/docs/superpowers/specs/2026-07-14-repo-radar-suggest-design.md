# Repo Radar — Interest-Based Repo Suggestions (Design)

**Date:** 2026-07-14
**Status:** Approved

## Goal
Extend the Repo Radar Discord bot so a user can get GitHub repo recommendations
based on a natural-language interest (e.g. "professional PDF tools",
"trending skills agent") instead of raw search keywords. The interest is turned
into GitHub search queries by an LLM, then resolved to real repos via the
existing GitHub Search API client.

## Decisions (from brainstorming)
- **LLM:** Use OpenRouter with the free model `openrouter/tencent/hy3:free`.
- **Trigger:** Both an on-demand command and a passive auto mode.
- **No channel-history scanning.** The interest comes from the user's own text
  (command argument or a message that looks like an interest request), not from
  reading the last N messages.
- **History depth:** N/A (we do not fetch channel history).

## Architecture
- **config.py** — load `OPENROUTER_API_KEY` from `.env` (new required var for
  this feature).
- **llm_client.py** (new) — wraps the OpenRouter chat completions API.
- **main.py** — new `/suggest` slash command + an `on_message` listener for
  auto mode. Both reuse `github_client.search_repositories` and `build_embed`.

## Components

### `llm_client.py`
- Constant `MODEL = "openrouter/tencent/hy3:free"`.
- `suggest_queries(interest: str) -> list[str]`:
  - POST `https://openrouter.ai/api/v1/chat/completions`
  - Headers: `Authorization: Bearer <OPENROUTER_API_KEY>`,
    `Content-Type: application/json`, `HTTP-Referer` / `X-Title` optional.
  - Body: model, a system prompt instructing the model to return ONLY a JSON
    array of 1–5 concise GitHub search query strings derived from the user's
    interest, and the user message = the interest text.
  - Parse the model's content robustly: strip ```json fenced blocks if present,
    then `json.loads`. Expect a list of strings.
  - Returns `list[str]` of queries.
- Custom exception `LLMError(Exception)` raised for: missing API key, non-200
  API response, network error, or content that is not a valid JSON array of
  strings.

### `/suggest <interest> [count]` (slash command)
- `interest: str` (required, free text).
- `count: int = 5` (optional, max ~10).
- Flow:
  1. `await interaction.response.defer()`
  2. `queries = llm_client.suggest_queries(interest)`
  3. For queries in order, call `github_client.search_repositories(q)`,
     collect results until `count` repos gathered.
  4. Post each as a repo card via `build_embed` (reuse existing helper).
- Errors (friendly messages, no crash):
  - No `OPENROUTER_API_KEY` → "Set OPENROUTER_API_KEY in .env to use suggestions."
  - `LLMError` → "Could not understand that interest. Try rephrasing."
  - No queries returned → "No search ideas generated; try a different interest."
  - `GitHubRateLimitError` → existing "GitHub rate limit reached" message.
  - `GitHubAPIError` → existing friendly message.

### Auto mode (`on_message` listener)
- Activates only when a message **looks like an interest request**:
  - The bot is @mentioned, OR
  - The message contains a trigger phrase: `recommend`, `suggest`, `find me`,
    `repos for`, `show me` (case-insensitive).
- Never responds to:
  - Its own messages.
  - Slash commands (messages starting with `/`).
  - Messages that do not match the above trigger rules.
- When triggered: extract the interest text (the message content, minus any
  mention), run the same flow as `/suggest` (default count 5), and reply to the
  message (not defer — use `message.channel.send` or followup-style reply).
- Anti-spam: the conservative trigger rules above keep the channel from being
  flooded.

## Data Flow
interest text → `llm_client.suggest_queries` → `list[str]` queries
→ `github_client.search_repositories` (per query) → normalized repo dicts
→ `build_embed` → Discord message(s).

## Error Handling
- LLM missing key / failure / bad JSON → `LLMError` surfaced as a friendly
  message (no crash).
- GitHub failures reuse the existing `GitHubRateLimitError` / `GitHubAPIError`
  handling.
- Empty/malformed LLM output → friendly "try a different interest" message.

## Testing
- `tests/test_llm_client.py` (mock `requests.post`):
  - Valid JSON array in content → parsed into `list[str]`.
  - Fenced ```json block → still parsed.
  - Non-200 response → `LLMError`.
  - Content not valid JSON → `LLMError`.
  - Missing API key → `LLMError`.
- No live network in tests; reuse existing `github_client` tests (unchanged).

## Out of Scope (YAGNI)
- No channel-history scanning / summarization.
- No persistent memory of user interests.
- No user accounts, no DB.
- No choosing a different LLM model at runtime (model is fixed to hy3:free).

## Files Touched
- Modify: `config.py` (add `OPENROUTER_API_KEY`)
- Modify: `.env.example` (document `OPENROUTER_API_KEY`)
- Create: `llm_client.py`
- Create: `tests/test_llm_client.py`
- Modify: `main.py` (add `/suggest` command + `on_message` auto mode)
- Modify: `README.md` (document new feature + env var)
