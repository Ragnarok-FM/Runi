import re
from typing import TYPE_CHECKING

import discord
from discord import ui

from .resources import RESOURCES

if TYPE_CHECKING:
    from runi.main import RuniClient


# Matches an optional comma-grouped integer or decimal, with an optional
# trailing k/K (thousands) suffix, e.g. "12500", "12,500", "12.5k", "12K".
_AMOUNT_PATTERN = re.compile(r'^(\d+(?:\.\d+)?)\s*([kK])?$')


def _parse_amount(raw: str) -> int | None:
    """
    Parses a submitted amount string into a non-negative int, accepting
    plain numbers (with optional commas) and k-suffixed shorthand matching
    the in-game display convention (e.g. "20k" -> 20000, "23.5k" -> 23500).
    Returns None if the input doesn't match a valid amount.
    """
    cleaned = raw.strip().replace(",", "")
    if not cleaned:
        return None

    match = _AMOUNT_PATTERN.match(cleaned)
    if not match:
        return None

    number_str, suffix = match.groups()
    try:
        number = float(number_str)
    except ValueError:
        return None

    if suffix:
        number *= 1000

    value = round(number)
    if value < 0:
        return None

    return value


class ResourceSubmitModal(ui.Modal):
    """
    A single-field modal for submitting one clan war resource amount.
    Reused for all 8 resources — the field's label/placeholder are set
    per-instance based on `resource_key`.
    """

    amount = ui.TextInput(
        label="Amount",
        placeholder="e.g. 12500, 12,500, or 12.5k",
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
        value = _parse_amount(self.amount.value)

        if value is None:
            embed = self.bot.embed_renderer.render("clan_war_invalid_amount", {})
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        guild = interaction.guild
        assert guild is not None

        await self.bot.db.submit_clan_war_resource(
            guild.id, interaction.user.id, self.resource_key, value
        )

        embed = self.bot.embed_renderer.render("clan_war_submitted", {
            "resource": self.meta["label"],
            "amount": value,
        })
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Refresh the live panel to reflect the new submission immediately.
        await self._refresh_panel(guild.id)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        from runi.utils import log
        log.error(f"ResourceSubmitModal error ({self.resource_key}): {error}")
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "Something went wrong submitting that. Please try again.", ephemeral=True
            )
