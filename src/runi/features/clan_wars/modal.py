from typing import TYPE_CHECKING

import discord
from discord import ui

from .resources import RESOURCES

if TYPE_CHECKING:
    from runi.main import RuniClient


class ResourceSubmitModal(ui.Modal):
    """
    A single-field modal for submitting one clan war resource amount.
    Reused for all 8 resources — the field's label/placeholder are set
    per-instance based on `resource_key`.
    """

    amount = ui.TextInput(
        label="Amount",
        placeholder="Enter a whole number (e.g. 12500)",
        style=discord.TextStyle.short,
        max_length=12,
        required=True,
    )

    def __init__(self, bot: 'RuniClient', resource_key: str, refresh_panel):
        meta = RESOURCES[resource_key]
        super().__init__(title=f"Submit {meta['label']}")
        self.bot = bot
        self.resource_key = resource_key
        self.meta = meta
        self.amount.label = f"{meta['label']} — total amount"
        self._refresh_panel = refresh_panel

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.amount.value.strip().replace(",", "")

        if not raw.isdigit():
            embed = self.bot.embed_renderer.render("clan_war_invalid_amount", {})
            await interaction.response.send_message(embed=embed, ephemeral=True, delete_after=6)
            return

        value = int(raw)
        guild = interaction.guild
        assert guild is not None

        await self.bot.db.submit_clan_war_resource(
            guild.id, interaction.user.id, self.resource_key, value
        )

        embed = self.bot.embed_renderer.render("clan_war_submitted", {
            "resource": self.meta["label"],
            "amount": value,
        })
        await interaction.response.send_message(embed=embed, ephemeral=True, delete_after=6)

        # Refresh the live panel to reflect the new submission immediately.
        await self._refresh_panel(guild.id)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        from runi.utils import log
        log.error(f"ResourceSubmitModal error ({self.resource_key}): {error}")
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "Something went wrong submitting that. Please try again.", ephemeral=True
            )
