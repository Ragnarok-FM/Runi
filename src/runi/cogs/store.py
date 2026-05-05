from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from runi.main import RuniClient


# Item type labels for display
TYPE_LABELS = {
    "item":  "🎒 Item",
    "role":  "🎨 Role / Colour",
}


# TODO: Add validation, enforce parameters in some functions, and handle edge cases more gracefully (i.e. gifting role items when bot lacks permissions)
class Store(commands.Cog):
    def __init__(self, bot: 'RuniClient'):
        self.bot = bot

    # ── /store ─────────────────────────────────────────────────────────────────
    @app_commands.guild_only()
    @app_commands.command(name="store", description="Browse the Runeshard store.")
    async def store(self, interaction: discord.Interaction):
        await interaction.response.defer()

        guild_id = interaction.guild_id
        assert guild_id is not None
        items = await self.bot.db.get_store_items(guild_id)

        description = (
            "The store is empty right now — check back later!"
            if not items
            else "Spend your Runes on items and exclusive roles!\nUse `/buy <item id>` to purchase."
        )

        embed = self.bot.embed_renderer.render("store", {
            "description": description
        })

        if items:
            # Group by type
            groups: dict[str, list] = {}
            for item in items:
                groups.setdefault(item["type"], []).append(item)

            for item_type, group in groups.items():
                label = TYPE_LABELS.get(item_type, item_type.capitalize())

                lines = [
                    f"`#{i['item_id']}` **{i['name']}** — {i['price']:,} Runes\n  {i['description']}"
                    for i in group
                ]

                embed.add_field(name=label, value="\n".join(lines), inline=False)

        await interaction.followup.send(embed=embed)

    # ── /buy ───────────────────────────────────────────────────────────────────
    @app_commands.guild_only()
    @app_commands.command(name="buy", description="Purchase an item from the store.")
    @app_commands.describe(item_id="The item ID shown in /store.")
    async def buy(self, interaction: discord.Interaction, item_id: int):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        assert guild is not None
        result = await self.bot.db.purchase_item(
            interaction.user.id, guild.id, item_id
        )

        if not result["success"]:
            reason = result["reason"]

            if reason == "not_found":
                desc = "That item doesn't exist. Check `/store` for valid item IDs."
            elif reason == "already_owned":
                desc = f"You already own **{result['item']['name']}**!"
            elif reason == "insufficient_funds":
                desc = (
                    f"You need **{result['item']['price']:,} Runes** to buy "
                    f"**{result['item']['name']}** but only have "
                    f"**{result['balance']:,}**.\n"
                    f"Use `/work` and `/daily` to earn more!"
                )
            else:
                desc = "Something went wrong. Please try again."

            embed = self.bot.embed_renderer.render("store_purchase_failed", {
                "description": desc
            })
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        item = result["item"]

        # If it's a role item, assign the Discord role
        if item["type"] == "role" and item["role_id"]:
            role = guild.get_role(item["role_id"])
            if role:
                try:
                    assert isinstance(interaction.user, discord.Member)
                    await interaction.user.add_roles(role, reason="Store purchase")
                except discord.Forbidden:
                    pass  # Bot lacks permissions — purchased but role not assigned

        embed = self.bot.embed_renderer.render("store_purchase_success", {
            "name": item["name"],
            "price": item["price"],
            "balance": result["balance"]
        })
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /inventory ─────────────────────────────────────────────────────────────
    @app_commands.guild_only()
    @app_commands.command(name="inventory", description="View your purchased items.")
    async def inventory(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        assert guild is not None
        items = await self.bot.db.get_inventory(interaction.user.id, guild.id)

        if not items:
            content = "Your inventory is empty — visit `/store` to get started!"
        else:
            lines = [
                f"{TYPE_LABELS.get(i['type'], i['type'].capitalize())}: **{i['name']}** — {i['description']}"
                for i in items
            ]
            content = "\n".join(lines)

        embed = self.bot.embed_renderer.render("inventory", {
            "username": interaction.user.display_name,
            "content": content
        })
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Admin: /gift ──────────────────────────────────────────────────────────────────
    @app_commands.guild_only()
    @app_commands.command(name="gift", description="Gift an item from your inventory to another user.")
    @app_commands.describe(
        member="The user to gift the item to.",
        item_id="The item ID from your /inventory.",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def gift(self, interaction: discord.Interaction, member: discord.Member, item_id: int):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        assert guild is not None
        result = await self.bot.db.transfer_item(
            interaction.user.id, member.id, guild.id, item_id
        )

        if result["reason"] == "self_transfer":
            data = ("❌ Nice Try", "You can't gift an item to yourself!")
        elif result["reason"] == "not_owned":
            data = ("❌ Item Not Found", "You don't own that item. Check `/inventory` for your items.")
        elif result["reason"] == "already_owned":
            data = ("❌ Already Owned", f"{member.display_name} already owns **{result['item']['name']}**!")
        else:
            data = None

        if data:
            embed = self.bot.embed_renderer.render("store_gift_error", {
                "title": data[0],
                "description": data[1]
            })
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        item = result["item"]

        # If it's a role item, reassign the Discord role
        if item["type"] == "role" and item["role_id"]:
            role = guild.get_role(item["role_id"])
            if role:
                try:
                    assert isinstance(interaction.user, discord.Member)
                    await interaction.user.remove_roles(role, reason="Item gifted away")
                    await member.add_roles(role, reason="Item received as gift")
                except discord.Forbidden:
                    pass

        embed = self.bot.embed_renderer.render("store_gift_success", {
            "sender": interaction.user.display_name,
            "item": item["name"],
            "receiver": member.display_name
        })
        await interaction.followup.send(embed=embed)

    # ── Admin: /additem ────────────────────────────────────────────────────────
    @app_commands.guild_only()
    @app_commands.command(name="additem", description="[Admin] Add an item to the store.")
    @app_commands.describe(
        name="Item name",
        description="Short description shown in the store",
        price="Price in Runes",
        item_type="Type of item",
        role="The Discord role to assign (for role-type items only)",
    )
    @app_commands.choices(item_type=[
        app_commands.Choice(name="Item", value="item"),
        app_commands.Choice(name="Role / Colour", value="role"),
    ])
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def additem(
        self,
        interaction: discord.Interaction,
        name: str,
        description: str,
        price: int,
        item_type: app_commands.Choice[str],
        role: Optional[discord.Role] = None,
    ):
        guild_id = interaction.guild_id
        assert guild_id is not None

        role_id = role.id if role else None
        item_id = await self.bot.db.add_store_item(
            guild_id, name, description, price, item_type.value, role_id
        )
        embed = self.bot.embed_renderer.render("store_add_item", {
            "name": name,
            "id": item_id,
            "price": price,
        })

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Admin: /removeitem ─────────────────────────────────────────────────────
    @app_commands.guild_only()
    @app_commands.command(name="removeitem", description="[Admin] Remove an item from the store.")
    @app_commands.describe(item_id="The item ID to remove.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def removeitem(self, interaction: discord.Interaction, item_id: int):
        guild_id = interaction.guild_id
        assert guild_id is not None
        removed = await self.bot.db.remove_store_item(item_id, guild_id)
        if removed:
            embed = self.bot.embed_renderer.render("store_remove_item_success", {
                "id": item_id
            })
        else:
            embed = self.bot.embed_renderer.render("store_remove_item_not_found", {
                "id": item_id
            })

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Error handler ──────────────────────────────────────────────────────────
    @gift.error
    @additem.error
    @removeitem.error
    async def admin_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            embed = self.bot.embed_renderer.render("error_missing_admin_permissions", {})
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: 'RuniClient'):
    await bot.add_cog(Store(bot))
