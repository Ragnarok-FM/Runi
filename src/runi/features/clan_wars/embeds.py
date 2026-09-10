EMBEDS = {
    # The main live panel. "description" is built dynamically in clan_wars.py
    # (per-member rows + clan totals), this template just supplies the shell.
    "clan_war_panel": {
        "title": "⚔️ Clan Wars — Resource Tracker",
        "description": "{content}",
        "color": "gold",
        "footer": "Runi • Clan Wars | Page {page} of {total_pages} • Auto-updates every {refresh_minutes}m • {timestamp_label}"
    },

    "clan_war_no_role": {
        "title": "❌ Not Eligible",
        "description": "You need the Clan Wars participant role to submit resources.",
        "color": "red",
        "footer": "Runi • Clan Wars"
    },

    "clan_war_submitted": {
        "title": "✅ Submitted",
        "description": "**{resource}** updated to **{amount:,}**.",
        "color": "green",
        "footer": "Runi • Clan Wars"
    },

    "clan_war_invalid_amount": {
        "title": "❌ Invalid Amount",
        "description": "Please enter a whole number of 0 or greater.",
        "color": "red",
        "footer": "Runi • Clan Wars"
    },

    "clan_war_panel_created": {
        "title": "✅ Panel Created",
        "description": "The Clan Wars panel has been posted in this channel.",
        "color": "green",
        "footer": "Runi • Clan Wars"
    },

    "clan_war_no_panel": {
        "title": "❌ No Panel Found",
        "description": "No Clan Wars panel is set up yet. An admin needs to run `/resourcepanel setup` first.",
        "color": "red",
        "footer": "Runi • Clan Wars"
    },

    "clan_war_rate_updated": {
        "title": "✅ Rate Updated",
        "description": "**{resource}** is now worth **{points:,}** points per unit.\nThe panel has been refreshed to reflect the change.",
        "color": "green",
        "footer": "Runi • Clan Wars"
    },

    "clan_war_reset": {
        "title": "🔄 New War Cycle Started",
        "description": "All submitted resources have been cleared for a fresh clan war cycle.",
        "color": "gold",
        "footer": "Runi • Clan Wars"
    },

    "clan_war_invalid_resource": {
        "title": "❌ Unknown Resource",
        "description": "`{resource}` isn't a recognized resource. Valid options: {valid_resources}.",
        "color": "red",
        "footer": "Runi • Clan Wars"
    }
}
