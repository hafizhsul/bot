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
