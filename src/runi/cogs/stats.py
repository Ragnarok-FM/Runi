from typing import TYPE_CHECKING

from discord.ext import commands

if TYPE_CHECKING:
    from runi.main import RuniClient


class Stats(commands.Cog):
    def __init__(self, bot: 'RuniClient'):
        self.bot = bot

    @commands.hybrid_command(name="maxsubstats", description="Show the maximum values for each substat")
    async def maxsubstats(self, ctx: commands.Context):
        embed = self.bot.embed_renderer.render("max_substats", {})
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="health_formula", description="Show the health formula")
    async def health_formula(self, ctx: commands.Context):
        embed = self.bot.embed_renderer.render("health_formula", {})
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="damage_formula", description="Show the damage formula")
    async def damage_formula(self, ctx: commands.Context):
        embed = self.bot.embed_renderer.render("damage_formula", {})
        await ctx.send(embed=embed)

async def setup(bot: 'RuniClient'):
    await bot.add_cog(Stats(bot))