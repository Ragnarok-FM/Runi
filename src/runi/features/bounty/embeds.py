EMBEDS = {
    "bounty_started": {
        "title": "🎯 Bounties Started!",
        "description": "{description}",
        "thumbnail": "{avatar}",
        "color": "gold",
        "footer": "Runi • Bounty | New bounties in {wait}"
    },

    "bounty_board": {
        "title": "🎯 {username}'s Bounties",
        "description": "{description}",
        "thumbnail": "{avatar}",
        "color": "gold",
        "footer": "Runi • Bounty | New bounties in {wait}"
    },

    "bounty_complete": {
        "title": "🎯 Bounty Complete!",
        "description": "You completed a {tier_label} bounty!\n> {text}",
        "fields": [
            ("Reward", "+{reward:,} :Runes:", True),
            ("Balance", "{balance:,} :Runes:", True),
        ],
        "color": "gold",
        "footer": "Runi • Bounty | {done}/{total} bounties completed today"
    },

    "bounty_set_complete": {
        "title": "🏆 All Bounties Complete!",
        "description": "You finished every bounty today and earned the completion bonus!",
        "fields": [
            ("Bonus", "+{bonus:,} :Runes:", True),
            ("Balance", "{balance:,} :Runes:", True),
        ],
        "color": "gold",
        "footer": "Runi • Bounty | New bounties in {wait}"
    },

    "bounty_not_started": {
        "title": "❌ No Bounties Yet",
        "description": "{description}",
        "color": "red",
        "footer": "Runi • Bounty"
    },

    "bounty_info": {
        "title": "🎯 How Bounties Work",
        "description": (
            "Use `/bounty start` once per day to get three bounties, "
            "then track them with `/bounty status`. "
            "Rewards are paid out automatically when you complete a bounty."
        ),
        "fields": [
            ("Tiers", "{tiers}", False),
            ("🏆 Completion Bonus", "Complete all three to earn an extra **{bonus_rate}** of the set's rewards.", False),
            ("Rules", (
                "• Coinflip and slots rounds only count with a bet of **{min_bet}+** :Runes:\n"
                "• Chat bounties count messages that earn XP\n"
                "• Bounties reset at 00:00 UTC, together with `/daily`"
            ), False),
        ],
        "color": "gold",
        "footer": "Runi • Bounty"
    },
}
