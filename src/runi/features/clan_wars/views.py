from typing import TYPE_CHECKING

import discord
from discord import ui

from .resources import RESOURCES, find_member_clan
from .modal import ResourceSubmitModal

if TYPE_CHECKING:
    from runi.main import RuniClient


class PanelView(ui.View):
    """
    Persistent view attached to every clan's live Clan Wars panel message.

    This one view class is shared by all clans' panels — the buttons are
    generic (not tied to a specific clan_id in their custom_id), because:
      - Resource submission routes to whichever clan the clicking member's
        own roles match (looked up fresh on every click), not to whichever
        panel they happened to click the button on.
      - Pagination looks up which clan owns the clicked message via a
        reverse DB lookup (channel_id + message_id -> clan_id), so no
        clan-specific custom_id is needed there either.

    One instance is registered globally at bot startup via
    `bot.add_view(PanelView(bot))` so the buttons keep working across
    restarts (requires timeout=None + fixed custom_id on every component —
    both satisfied below).
    """

    def __init__(self, bot: 'RuniClient'):
        super().__init__(timeout=None)
        self.bot = bot

        for key, meta in RESOURCES.items():
            style = discord.ButtonStyle.primary if meta["style"] == "primary" else discord.ButtonStyle.success
            button = ui.Button(
                label=meta["label"],
                style=style,
                custom_id=f"cw_resource:{key}",
            )
            button.callback = self._make_resource_callback(key)
            self.add_item(button)

        prev_button = ui.Button(label="◀ Previous", style=discord.ButtonStyle.secondary, custom_id="cw_page:prev", row=2)
        next_button = ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary, custom_id="cw_page:next", row=2)
        prev_button.callback = self._page_callback(-1)
        next_button.callback = self._page_callback(1)
        self.add_item(prev_button)
        self.add_item(next_button)

    def _make_resource_callback(self, resource_key: str):
        async def callback(interaction: discord.Interaction):
            member = interaction.user
            guild = interaction.guild
            assert guild is not None

            clans = await self.bot.db.get_clans(guild.id)
            clan = find_member_clan(member, clans) if isinstance(member, discord.Member) else None

            if clan is None:
                embed = self.bot.embed_renderer.render("clan_war_no_role", {})
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            cog = self.bot.get_cog("ClanWars")
            await interaction.response.send_modal(
                ResourceSubmitModal(self.bot, resource_key, refresh_panel=cog.refresh_panel)
            )

        return callback

    def _page_callback(self, direction: int):
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer()

            message = interaction.message
            if message is None:
                return

            clan_id = await self.bot.db.get_clan_id_by_panel_message(interaction.channel_id, message.id)
            if clan_id is None:
                # Panel message isn't registered to any clan (shouldn't normally
                # happen) — nothing sensible to paginate.
                return

            cog = self.bot.get_cog("ClanWars")
            cog.shift_page(clan_id, direction)
            await cog.refresh_panel(clan_id)

        return callback
