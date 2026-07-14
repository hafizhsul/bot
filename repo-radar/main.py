import discord
from discord import app_commands
from discord.ext import commands

import github_client
import llm_client
from config import DISCORD_TOKEN

intents = discord.Intents.default()
bot = commands.Bot(
    command_prefix="/",
    intents=intents,
    activity=discord.Activity(type=discord.ActivityType.watching, name="GitHub trends"),
)


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


@bot.event
async def on_ready() -> None:
    await bot.tree.sync()
    print(f"Repo Radar online as {bot.user} (id: {bot.user.id})")


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
        repos = github_client.search_repositories(query, sort="updated")
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


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN is not set. Add it to your .env file.")
    bot.run(DISCORD_TOKEN)
