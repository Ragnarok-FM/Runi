import os
import pkgutil
import discord
from discord.ext import commands
from dotenv import load_dotenv
from runi import log, cogs

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
        super().__init__(command_prefix=commands.when_mentioned_or("!"), intents=intents)

        self.guild_ids = guild_ids

    async def setup_hook(self):
        for module in pkgutil.walk_packages(cogs.__path__, cogs.__name__ + "."):
            if module.ispkg:
                continue

            await self.load_extension(module.name)

        for guild_id in self.guild_ids:
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)

    async def on_ready(self):
        log.info(f"Logged on as {self.user}!")

    async def on_guild_join(self, guild):
        if guild.id not in self.guild_ids:
            log.warn(f"Unauthorized guild: {guild.name} ({guild.id}) - leaving")
            await guild.leave()

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        raise error

def main():
    load_dotenv()

    token = os.environ.get("DISCORD_TOKEN")
    if not token or not token.strip():
        raise RuntimeError("DISCORD_TOKEN not set")

    guild_ids = get_guild_ids()

    client = RuniClient(guild_ids)
    client.run(token.strip())


if __name__ == "__main__":
    main()