from discord import app_commands
from discord.ext import commands
import discord


class Ping(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send_pong(self, send):
        await send("Pong!")

    @app_commands.command(name="ping", description="Check if the bot is alive")
    async def ping_slash(self, interaction: discord.Interaction):
        await self._send_pong(interaction.response.send_message)

    @commands.command(name="ping")
    async def ping_prefix(self, ctx: commands.Context):
        await self._send_pong(ctx.send)


async def setup(bot: commands.Bot):
    await bot.add_cog(Ping(bot))