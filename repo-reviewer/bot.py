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
    msg = await channel.send("⏳ Meng-clone repositori…")
    try:
        context, truncated = fetch_repo(repo_url, token=os.getenv("GITHUB_TOKEN"))
    except Exception as e:
        await msg.edit(content=None, embed=error_embed(f"Gagal mengambil repo: {e}"))
        return
    if not context.strip():
        await msg.edit(content=None, embed=error_embed("Tidak ada file sumber yang bisa dibaca."))
        return
    await msg.edit(content="🤖 Menganalisis dengan LLM…")
    try:
        review = review_repo(context, os.getenv("OPENROUTER_API_KEY"))
    except Exception as e:
        await msg.edit(content=None, embed=error_embed(f"Kesalahan LLM: {e}"))
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
        await ctx.send(embed=error_embed("URL repositori GitHub tidak valid. Format: github.com/owner/repo"))
        return
    repo_url = f"https://github.com/{parsed[0]}/{parsed[1]}"
    await handle_review(ctx.channel, repo_url)


bot.run(os.getenv("DISCORD_TOKEN"))
