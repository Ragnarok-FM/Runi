from discord import app_commands
from discord.ext import commands
import discord
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ..main import RuniClient


class Stats(commands.Cog):
    def __init__(self, bot: 'RuniClient'):
        self.bot = bot

    @app_commands.command(name="maxsubstats", description="Show the maximum values for each substat")
    async def maxsubstats(self, interaction: discord.Interaction):
        embed = self.bot.embed_renderer.render("max_substats", {})
        await interaction.response.send_message(embed=embed)


async def setup(bot: 'RuniClient'):
    await bot.add_cog(Stats(bot))