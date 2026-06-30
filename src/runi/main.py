import asyncio
import importlib
import os
import pkgutil
from pathlib import Path

import discord
from discord import Message
from discord.ext import commands
from dotenv import load_dotenv

from runi import features
from runi.database import Database
from runi.utils import log, colors
from runi.utils.embed_renderer import EmbedRenderer
from runi.utils.emojis import EmojiRegistry
from runi.utils.paths import BOT_DATA_DB_PATH


def get_guild_ids(env: str = "DEV") -> set[int]:
    guild_id = os.environ.get(f"GUILD_ID_{env.upper()}")
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
        self.app_emojis = EmojiRegistry()

    async def setup_hook(self):
        features_root = Path(features.__path__[0])

        for feature_dir in features_root.iterdir():
            if not feature_dir.is_dir():
                continue

            pkg_name = f"{features.__name__}.{feature_dir.name}"
            for _, module_name, ispkg in pkgutil.iter_modules([str(feature_dir)], prefix=f"{pkg_name}."):
                if ispkg:
                    continue
                
                if module_name.rsplit('.', 1)[1].startswith("_"):
                    continue

                try:
                    module = importlib.import_module(module_name)
                except Exception as e:
                    log.error(f"Failed to import feature module {module_name}: {e}")
                    continue

                if not hasattr(module, "setup"):
                    continue

                try:
                    await self.load_extension(module_name)
                    log.info(f"Loaded feature extension {module_name}.")
                except Exception as e:
                    log.error(f"Failed to load feature extension {module_name}: {e}")

        await self.app_emojis.load(self)

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

        log.error(error);
        raise error

    async def on_message(self, message: Message):
        if message.author.bot:
            return
        
        # TODO: Move this to a cog and use embed templates for embed responses
        if self.user.mentioned_in(message):
            content = message.content.lower().strip()
            if "good morning" in content:
                await message.channel.send(f"And good morning to you too, {message.author.mention}!")
            elif "hello" in content:
                await message.channel.send(f"Hello {message.author.mention}!")

        await self.process_commands(message)


async def main():
    load_dotenv()

    env = os.environ.get("ENV", "DEV").strip()
    token = os.environ.get(f"DISCORD_TOKEN_{env.upper()}")
    if not token or not token.strip():
        raise RuntimeError(f"DISCORD_TOKEN_{env.upper()} environment variable not set.")

    guild_ids = get_guild_ids(env)

    client = RuniClient(guild_ids)
    try:
        await client.start(token.strip())
    except KeyboardInterrupt:
        log.info("Shutting down bot...")
        await client.close()

def run():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Shutting down bot...")

if __name__ == "__main__":
    run()