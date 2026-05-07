import asyncio
import os
import pkgutil

import discord
from discord.ext import commands
from dotenv import load_dotenv

from runi import cogs
from runi.database import Database
from runi.utils import log, colors
from runi.utils.embed_renderer import EmbedRenderer
from runi.utils.paths import BOT_DATA_DB_PATH


def get_guild_ids() -> set[int]:
    env = os.environ.get("ENV", "dev").strip().lower()

    if env == "dev":
        guild_id = os.environ.get("GUILD_ID_DEV")
    elif env == "prod":
        guild_id = os.environ.get("GUILD_ID_PROD")
    else:
        raise RuntimeError(f"Invalid ENV value: {env}")

    if not guild_id:
        raise RuntimeError(f"Guild ID not set for ENV={env}")

    return {int(guild_id)}


class RuniClient(commands.Bot):
    def __init__(self, guild_ids: set[int]):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix=commands.when_mentioned_or("!"), intents=intents)

        self.guild_ids = guild_ids
        self.embed_renderer = EmbedRenderer()
        self.db = Database(str(BOT_DATA_DB_PATH))
        
    async def setup_hook(self):
        for module in pkgutil.walk_packages(cogs.__path__, cogs.__name__ + "."):
            if module.ispkg:
                continue

            await self.load_extension(module.name)

        for guild_id in self.guild_ids:
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            try:
                synced = await self.tree.sync(guild=guild)
                log.info(f"Synced {len(synced)} slash commands to guild {guild_id}.")
            except Exception as e:
                log.error(f"Failed to sync commands: {e}")

    async def on_ready(self):
        await self.db.init()
        log.info(f"Logged on as {self.user}!")

    async def on_guild_join(self, guild):
        if guild.id not in self.guild_ids:
            log.warn(f"Unauthorized guild: {guild.name} ({guild.id}) - leaving")
            await guild.leave()

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        raise error

    async def on_message(self, message):
        if message.author.bot:
            return
        
        # TODO: Move this to a cog and use embed templates for responses
        content = message.content.lower().strip()
        if "good morning" in content:
            await message.channel.send(f"And good morning to you too, my fellow descendant!")
        elif "hello" in content:
            await message.channel.send(f"Greetings, peasant!")

        result = await self.db.add_xp(message.author.id, message.guild.id)

        if result["leveled_up"]:
            embed = discord.Embed(
                title="⚡ Level Up!",
                description=(
                    f"**{message.author.display_name}** has reached **Level {result['new_level']}**!"
                ),
                color=colors.get_color("red")
            )
            embed.set_thumbnail(url=message.author.display_avatar.url)
            embed.set_footer(text="Runi • XP System")
            await message.channel.send(embed=embed)


        await self.process_commands(message)


async def main():
    load_dotenv()

    token = os.environ.get("DISCORD_TOKEN")
    if not token or not token.strip():
        raise RuntimeError("DISCORD_TOKEN environment variable not set.")

    guild_ids = get_guild_ids()

    client = RuniClient(guild_ids)
    await client.start(token.strip())

def run():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down bot...")

if __name__ == "__main__":
    run()