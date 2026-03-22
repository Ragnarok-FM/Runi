from discord import app_commands
from discord.ext import commands
import discord
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ..main import RuniClient


class Stats(commands.Cog):
    def __init__(self, bot: 'RuniClient'):
        self.bot = bot

    async def _send_maxsubstats(self, send):
        embed = self.bot.embed_renderer.render("max_substats", {})
        await send(embed=embed)

    @app_commands.command(name="maxsubstats", description="Show the maximum values for each substat")
    async def maxsubstats_slash(self, interaction: discord.Interaction):
        await self._send_maxsubstats(interaction.response.send_message)

    @commands.command(name="maxsubstats")
    async def maxsubstats_prefix(self, ctx: commands.Context):
        await self._send_maxsubstats(ctx.send)


async def setup(bot: 'RuniClient'):
    await bot.add_cog(Stats(bot))