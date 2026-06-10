from discord.ext import commands


class Ping(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="ping", description="Check if the bot is alive")
    async def ping(self, ctx: commands.Context):
        await ctx.send("Pong!")

async def setup(bot: commands.Bot):
    await bot.add_cog(Ping(bot))