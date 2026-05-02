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

        embed = discord.Embed(
            title="🛒 Runeshard Store",
            description="Spend your Runes on items and exclusive roles!\nUse `/buy <item id>` to purchase.",
            color=discord.Color(0xF1C40F),
        )

        if not items:
            embed.description = "The store is empty right now — check back later!"
        else:
            # Group by type
            groups: dict[str, list] = {}
            for item in items:
                groups.setdefault(item["type"], []).append(item)

            for item_type, group in groups.items():
                label = TYPE_LABELS.get(item_type, item_type.capitalize())
                lines = []
                for item in group:
                    lines.append(
                        f"`#{item['item_id']}` **{item['name']}** — {item['price']:,} Runes\n"
                        f"  {item['description']}"
                    )
                embed.add_field(name=label, value="\n".join(lines), inline=False)

        embed.set_footer(text="Runi • Store")
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

            embed = discord.Embed(
                title="❌ Purchase Failed",
                description=desc,
                color=discord.Color(0xF1C40F),
            )
            embed.set_footer(text="Runi • Store")
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

        embed = discord.Embed(
            title="✅ Purchase Successful!",
            description=f"You bought **{item['name']}** for {item['price']:,} Runes.",
            color=discord.Color(0xF1C40F),
        )
        embed.add_field(name="Remaining Balance", value=f"{result['balance']:,} Runes")
        embed.set_footer(text="Runi • Store")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /inventory ─────────────────────────────────────────────────────────────
    @app_commands.guild_only()
    @app_commands.command(name="inventory", description="View your purchased items.")
    async def inventory(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        assert guild is not None
        items = await self.bot.db.get_inventory(interaction.user.id, guild.id)

        embed = discord.Embed(
            title=f"🎒 {interaction.user.display_name}'s Inventory",
            color=discord.Color(0xF1C40F),
        )

        if not items:
            embed.description = "Your inventory is empty — visit `/store` to get started!"
        else:
            lines = []
            for item in items:
                label = TYPE_LABELS.get(item["type"], item["type"].capitalize())
                lines.append(f"{label}: **{item['name']}** — {item['description']}")
            embed.description = "\n".join(lines)

        embed.set_footer(text="Runi • Store")
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
            embed = discord.Embed(
                title="❌ Nice Try",
                description="You can't gift an item to yourself!",
                color=discord.Color(0xF1C40F),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if result["reason"] == "not_owned":
            embed = discord.Embed(
                title="❌ Item Not Found",
                description="You don't own that item. Check `/inventory` for your items.",
                color=discord.Color(0xF1C40F),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if result["reason"] == "already_owned":
            embed = discord.Embed(
                title="❌ Already Owned",
                description=f"{member.display_name} already owns **{result['item']['name']}**!",
                color=discord.Color(0xF1C40F),
            )
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

        embed = discord.Embed(
            title="🎁 Gift Sent!",
            description=f"{interaction.user.display_name} gifted **{item['name']}** to {member.mention}!",
            color=discord.Color(0xF1C40F),
        )
        embed.set_footer(text="Runi • Store")
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
        embed = discord.Embed(
            title="✅ Item Added",
            description=f"**{name}** (ID: `#{item_id}`) added to the store for {price:,} Runes.",
            color=discord.Color(0xF1C40F),
        )
        embed.set_footer(text="Runi • Store")
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
            embed = discord.Embed(
                title="🗑️ Item Removed",
                description=f"Item `#{item_id}` has been removed from the store.",
                color=discord.Color(0xF1C40F),
            )
        else:
            embed = discord.Embed(
                title="❌ Not Found",
                description=f"No active item with ID `#{item_id}` was found.",
                color=discord.Color(0xF1C40F),
            )
        embed.set_footer(text="Runi • Store")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Error handler ──────────────────────────────────────────────────────────
    @gift.error
    @additem.error
    @removeitem.error
    async def admin_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ You need Administrator permissions to use this command.",
                ephemeral=True,
            )


async def setup(bot: 'RuniClient'):
    await bot.add_cog(Store(bot))
