from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from runi.main import RuniClient


class Stats(commands.Cog):
    def __init__(self, bot: 'RuniClient'):
        self.bot = bot

    @app_commands.command(name="maxsubstats", description="Show the maximum values for each substat")
    async def maxsubstats(self, interaction: discord.Interaction):
        embed = self.bot.embed_renderer.render("max_substats", {})
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="health_formula", description="Show the health formula")
    async def health_formula(self, interaction: discord.Interaction):
        embed = self.bot.embed_renderer.render("health_formula", {})
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="damage_formula", description="Show the damage formula")
    async def damage_formula(self, interaction: discord.Interaction):
        embed = self.bot.embed_renderer.render("damage_formula", {})
        await interaction.response.send_message(embed=embed)

async def setup(bot: 'RuniClient'):
    await bot.add_cog(Stats(bot))