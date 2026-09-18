import re
from typing import TYPE_CHECKING

import discord
from discord import ui

from .resources import RESOURCES, find_member_clan

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

    With a k-suffix, a comma is treated as a decimal separator (European
    style, e.g. "12,5k" -> 12500) rather than a thousands grouping, since
    that's overwhelmingly what someone means when combining a comma with
    a k-shorthand. Without a k-suffix, commas are still treated as plain
    thousands groupings (e.g. "12,500" -> 12500), unaffected by this.

    Returns None if the input doesn't match a valid amount.
    """
    raw = raw.strip()
    if not raw:
        return None

    has_k_suffix = raw[-1] in ("k", "K")

    if has_k_suffix and "," in raw:
        # Only the LAST comma is treated as the decimal point; any earlier
        # ones (a rare combination with k-shorthand) are dropped as
        # thousands groupings, e.g. "1,234,5k" -> "1234.5k" -> 1234500.
        head, _, tail = raw.rpartition(",")
        cleaned = head.replace(",", "") + "." + tail
    else:
        cleaned = raw.replace(",", "")

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
        member = interaction.user

        # Re-derive the member's clan fresh at submission time (not cached
        # from when the button was clicked), so a role change in between
        # takes effect immediately rather than on their next submission.
        clans = await self.bot.db.get_clans(guild.id)
        clan = find_member_clan(member, clans) if isinstance(member, discord.Member) else None

        if clan is None:
            embed = self.bot.embed_renderer.render("clan_war_no_role", {})
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await self.bot.db.submit_clan_war_resource(
            guild.id, interaction.user.id, self.resource_key, value, clan["clan_id"]
        )

        embed = self.bot.embed_renderer.render("clan_war_submitted", {
            "resource": self.meta["label"],
            "amount": value,
        })
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Refresh that clan's own live panel to reflect the new submission immediately.
        await self._refresh_panel(clan["clan_id"])

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        from runi.utils import log
        log.error(f"ResourceSubmitModal error ({self.resource_key}): {error}")
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "Something went wrong submitting that. Please try again.", ephemeral=True
            )
