from pathlib import Path
from typing import TYPE_CHECKING

from discord import app_commands
from discord.ext import commands

from runi.features.ascension.ascension_table import AscensionTable

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

CLOCKWINDERS_CSV = DATA_DIR / "clockwinders.csv"
EGGSHELLS_CSV = DATA_DIR / "eggshells.csv"
SKILL_TICKETS_CSV = DATA_DIR / "skill_tickets.csv"

if TYPE_CHECKING:
    from runi.main import RuniClient


class Ascension(commands.Cog):
    def __init__(self, bot: 'RuniClient'):
        self.bot = bot
        
        self.clockwinders_table = AscensionTable(CLOCKWINDERS_CSV)
        self.clockwinders_table.load()

        self.eggshells_table = AscensionTable(EGGSHELLS_CSV)
        self.eggshells_table.load()

        self.skill_tickets_table = AscensionTable(SKILL_TICKETS_CSV)
        self.skill_tickets_table.load()

    @commands.hybrid_group(name="ascension", description="Ascension resource calculations")
    async def ascension(self, ctx):
        pass

    @ascension.command(name="mounts", description="Calculate the number of Clockwinders needed to reach a 7.2% Legendary chance.")
    @app_commands.describe(discount="Discount percentage", drop="Extra drop chance")
    @app_commands.choices(
        discount=[app_commands.Choice(name=str(i), value=i) for i in range(1, 26)],
        drop=[app_commands.Choice(name=str(i), value=i) for i in range(2, 51, 2)],
    )
    async def clockwinders(self, ctx: commands.Context, discount: int, drop: int):
        value = self.clockwinders_table.get(discount, drop)

        await ctx.send(
            f"**Clockwinders for 7.2% Legendary:** {value:,} <:FM_Clockwinder:1501325934673002496>\n"
            f"-# {discount}% discount • {drop}% drop chance"
        )

    @ascension.command(name="pets", description="Calculate the number of Eggshells needed to reach a 7.2% Legendary chance.")
    @app_commands.describe(drop="Extra drop chance")
    @app_commands.choices(
        drop=[app_commands.Choice(name=str(i), value=i) for i in range(2, 51, 2)],
    )
    async def eggshells(self, ctx: commands.Context, drop: int):
        value = self.eggshells_table.get(drop)

        await ctx.send(
            f"**Eggshells for 7.2% Legendary:** {value:,} <:FM_Eggshell:1502032930988621914>\n"
            f"-# {drop}% drop chance"
        )

    @ascension.command(name="skills", description="Calculate the number of Skill Tickets needed to reach a 2% Legendary chance.")
    @app_commands.describe(discount="Discount percentage")
    @app_commands.choices(
        discount=[app_commands.Choice(name=str(i), value=i) for i in range(1, 26)],
    )
    async def skilltickets(self, ctx: commands.Context, discount: int):
        value = self.skill_tickets_table.get(discount)

        await ctx.send(
            f"**Skill Tickets for 2% Legendary:** {value:,} <:FM_SkillTicket:1502034730831446159>\n"
            f"-# {discount}% discount"
        )


async def setup(bot: 'RuniClient'):
    await bot.add_cog(Ascension(bot))