from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from runi.main import RuniClient
from runi.services.ascension.ascension_table import AscensionTable
from runi.utils.paths import CLOCKWINDERS_CSV, EGGSHELLS_CSV, SKILL_TICKETS_CSV


class Ascension(commands.Cog):
    def __init__(self, bot: 'RuniClient'):
        self.bot = bot
        
        self.clockwinders_table = AscensionTable(CLOCKWINDERS_CSV)
        self.clockwinders_table.load()

        self.eggshells_table = AscensionTable(EGGSHELLS_CSV)
        self.eggshells_table.load()

        self.skill_tickets_table = AscensionTable(SKILL_TICKETS_CSV)
        self.skill_tickets_table.load()

    ascension = app_commands.Group(
        name="ascension",
        description="Ascension resource calculations"
    )

    @ascension.command(name="clockwinders", description="Calculate the number of Clockwinders needed to reach a 7.2% Legendary chance.")
    @app_commands.describe(discount="Discount percentage", drop="Extra drop chance")
    @app_commands.choices(
        discount=[app_commands.Choice(name=str(i), value=i) for i in range(1, 26)],
        drop=[app_commands.Choice(name=str(i), value=i) for i in range(2, 51, 2)],
    )
    async def clockwinders(self, interaction: discord.Interaction, discount: int, drop: int):
        value = self.clockwinders_table.get(discount, drop)

        await interaction.response.send_message(
            f"**Clockwinders for 7.2% Legendary:** {value:,} <:FM_Clockwinder:1501325934673002496>\n"
            f"-# {discount}% discount • {drop}% drop chance"
        )

    @ascension.command(name="eggshells", description="Calculate the number of Eggshells needed to reach a 7.2% Legendary chance.")
    @app_commands.describe(drop="Extra drop chance")
    @app_commands.choices(
        drop=[app_commands.Choice(name=str(i), value=i) for i in range(2, 51, 2)],
    )
    async def eggshells(self, interaction: discord.Interaction, drop: int):
        value = self.eggshells_table.get(drop)

        await interaction.response.send_message(
            f"**Eggshells for 7.2% Legendary:** {value:,} <:FM_Eggshell:1502032930988621914>\n"
            f"-# {drop}% drop chance"
        )


    @ascension.command(name="skilltickets", description="Calculate the number of Skill Tickets needed to reach a 5.23% Legendary chance.")
    @app_commands.describe(discount="Discount percentage")
    @app_commands.choices(
        discount=[app_commands.Choice(name=str(i), value=i) for i in range(1, 26)],
    )
    async def skilltickets(self, interaction: discord.Interaction, discount: int):
        value = self.skill_tickets_table.get(discount)

        await interaction.response.send_message(
            f"**Skill Tickets for 5.23% Legendary:** {value:,} <:FM_SkillTicket:1502034730831446159>\n"
            f"-# {discount}% discount"
        )


async def setup(bot: 'RuniClient'):
    await bot.add_cog(Ascension(bot))