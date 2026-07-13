# Repo Radar

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
