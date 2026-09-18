EMBEDS = {
    # The main live panel. "description" is built dynamically in clan_wars.py
    # (per-member rows + clan totals), this template just supplies the shell.
    "clan_war_panel": {
        "title": "⚔️ {clan_name} — Resource Tracker",
        "description": "{content}",
        "color": "gold",
        "footer": "Runi • Clan Wars | Page {page} of {total_pages} • Auto-updates every {refresh_minutes}m • ⚠️ = Stale (7+ days) • {timestamp_label}"
    },

    "clan_war_no_role": {
        "title": "❌ Not Eligible",
        "description": "You're not part of any registered clan on this server, so you can't submit resources. Ask an admin to check your roles.",
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
        "description": "That doesn't look like a valid number. Try something like `12500`, `12,500`, or `12.5k`.",
        "color": "red",
        "footer": "Runi • Clan Wars"
    },

    "clan_war_panel_created": {
        "title": "✅ Panel Created",
        "description": "The **{clan_name}** Clan Wars panel has been posted in this channel.",
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
    },

    "clan_war_my_resources": {
        "title": "📋 Your Clan Wars Submissions",
        "description": "{content}",
        "color": "blurple",
        "footer": "Runi • Clan Wars"
    },

    "clan_war_no_submissions": {
        "title": "📋 No Submissions Yet",
        "description": "You haven't submitted any resources this cycle. Use the buttons on the Clan Wars panel to add yours!",
        "color": "red",
        "footer": "Runi • Clan Wars"
    },

    "clan_registered": {
        "title": "✅ Clan Registered",
        "description": "**{name}** is now registered, tied to {role}.\nMembers with that role can now submit resources, and you can run `/resourcepanel setup` to post their panel.",
        "color": "green",
        "footer": "Runi • Clan Wars"
    },

    "clan_role_already_registered": {
        "title": "❌ Role Already In Use",
        "description": "{role} is already tied to another registered clan. Each role can only identify one clan.",
        "color": "red",
        "footer": "Runi • Clan Wars"
    },

    "clan_not_found": {
        "title": "❌ Clan Not Found",
        "description": "That clan doesn't exist on this server. Use `/register` to add it first.",
        "color": "red",
        "footer": "Runi • Clan Wars"
    }
}
