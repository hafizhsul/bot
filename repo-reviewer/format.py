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


def _score_color(score) -> discord.Color:
    try:
        s = int(score)
    except (TypeError, ValueError):
        return discord.Color.blurple()
    if s >= 8:
        return discord.Color.green()
    if s >= 5:
        return discord.Color.gold()
    return discord.Color.red()


def build_embed(review: dict, repo_url: str, truncated: bool) -> discord.Embed:
    score = review.get("score", "N/A")
    e = discord.Embed(
        title=f"📦 Ulasan Repo: {repo_url}",
        color=_score_color(score),
    )
    e.add_field(name="⭐ Skor (0-10)", value=str(score), inline=True)
    if truncated:
        e.add_field(name="📝 Catatan", value="Konteks dipotong (repo terlalu besar)", inline=True)
    e.add_field(name="📋 Ringkasan", value=_trim(_join(review.get("summary"))), inline=False)
    e.add_field(name="✅ Kelebihan", value=_trim(_join(review.get("pros"))), inline=False)
    e.add_field(name="⚠️ Kekurangan", value=_trim(_join(review.get("cons"))), inline=False)
    e.add_field(name="🔥 Risiko", value=_trim(_join(review.get("risks"))), inline=False)
    e.add_field(name="💡 Saran", value=_trim(_join(review.get("suggestions"))), inline=False)
    return e


def error_embed(message: str) -> discord.Embed:
    return discord.Embed(
        title="❌ Ulasan Gagal",
        description=_trim(message),
        color=discord.Color.red(),
    )
