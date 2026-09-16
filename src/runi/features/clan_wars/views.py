from typing import TYPE_CHECKING

import discord
from discord import ui

from .resources import RESOURCES, PARTICIPANT_ROLE_ID, REQUIRE_PARTICIPANT_ROLE
from .modal import ResourceSubmitModal

if TYPE_CHECKING:
    from runi.main import RuniClient


class PanelView(ui.View):
    """
    Persistent view attached to the live Clan Wars panel message.

    One instance of this view is registered globally at bot startup via
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
            if REQUIRE_PARTICIPANT_ROLE:
                if not isinstance(member, discord.Member) or not any(r.id == PARTICIPANT_ROLE_ID for r in member.roles):
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
            guild = interaction.guild
            assert guild is not None

            cog = self.bot.get_cog("ClanWars")
            cog.shift_page(guild.id, direction)
            await interaction.response.defer()
            await cog.refresh_panel(guild.id)

        return callback
