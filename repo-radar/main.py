import discord
from discord import app_commands
from discord.ext import commands

import github_client
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


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN is not set. Add it to your .env file.")
    bot.run(DISCORD_TOKEN)
