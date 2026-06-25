EMBEDS = {
    # ── /bounty – main progress view ──────────────────────────────────────────
    "bounty_board": {
        "title": "📋 Daily Bounty Board",
        "description": (
            "Complete all 3 bounties before the reset for a bonus reward!\n"
            "Resets {reset_timestamp}"
        ),
        "fields": [
            # Slots are injected dynamically; these act as a schema reminder.
            # The Bounty cog adds fields at render-time rather than using
            # the template fields list, because the number of slots is fixed
            # but their content is fully dynamic.
        ],
        "color": "gold",
        "footer": "Runi • Daily Bounties | {completed_count}/3 completed"
    },

    # ── /bounty – first-time generation confirmation ───────────────────────────
    "bounty_assigned": {
        "title": "📋 New Bounties Assigned!",
        "description": (
            "Your daily bounties have been rolled. Good luck, adventurer!\n"
            "Resets {reset_timestamp}"
        ),
        "color": "blurple",
        "footer": "Runi • Daily Bounties | Use /bounty to track progress"
    },

    # ── Individual bounty reward claimed ──────────────────────────────────────
    "bounty_reward_claimed": {
        "title": "✅ Bounty Complete!",
        "description": "You completed **{description}**!",
        "fields": [
            ("Rarity", "{rarity_display}", True),
            ("Reward", "+{reward:,} Runes", True),
        ],
        "color": "green",
        "footer": "Runi • Daily Bounties"
    },

    # ── Full-house bonus (all 3 bounties done) ─────────────────────────────────
    "bounty_full_house": {
        "title": "🏆 Full House Bonus!",
        "description": (
            "Incredible! You completed **all 3 daily bounties**!\n"
            "Here's your bonus reward: **+{bonus:,} Runes**!"
        ),
        "color": "gold",
        "footer": "Runi • Daily Bounties"
    },

    # ── Legendary item award ───────────────────────────────────────────────────
    "bounty_legendary_item": {
        "title": "🌟 Legendary Reward!",
        "description": (
            "You completed a **Legendary** bounty and unlocked an extraordinary reward!\n\n"
            "**{item_name}** has been added to your inventory."
        ),
        "color": "gold",
        "footer": "Runi • Daily Bounties | Check /inventory"
    },

    # ── Error: no bounties yet (shouldn't surface normally) ───────────────────
    "bounty_none": {
        "title": "📋 No Active Bounties",
        "description": "Run `/bounty` to roll your daily bounties!",
        "color": "blurple",
        "footer": "Runi • Daily Bounties"
    },
}
