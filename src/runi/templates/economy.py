TEMPLATES = {
    "work_success": {
        "title": "⚒️ Work Complete",
        "description": (
            "You worked hard and earned {earned:,} Runes 💎\n"
            "Balance: {balance:,} Runes"
        ),
        "color": "gold",
        "footer": "Runi • Economy | You can work again in {cooldown}."
    },

    "work_cooldown": {
        "title": "⏳ Still Tired",
        "description": (
            "You need to rest before working again.\n"
            "Come back in {wait}."
        ),
        "color": "red",
        "footer": "Runi • Economy",
    },

    "daily_claim": {
        "title": "🗓️ Daily Reward Claimed!",
        "fields": [
            ("Earned", "{earned:,} Runes 💎", True),
            ("Balance", "{balance:,} Runes", True),
            ("Streak — Day {streak}", "{streak_bar}", False),
        ],
        "color": "gold",
        "footer": "Runi • Economy | {footer}"
    },

    "daily_already_claimed": {
        "title": "⏳ Already Claimed",
        "description": (
            "You've already claimed today's reward.\n"
            "Come back in {wait}."
        ),
        "color": "red",
        "footer": "Runi • Economy"
    },

    "balance": {
        "title": "💎 {username}'s Wallet",
        "fields": [
            ("Runes", "{runeshards:,}", True),
            ("Daily Streak", "{daily_streak} 🔥", True),
        ],
        "thumbnail": "{avatar}",
        "color": "gold",
        "footer": "Runi • Economy"
    },

    "coinflip_invalid_bet": {
        "description": "Bet must be greater than 0.",
        "color": "red",
        "footer": "Runi • Economy",
    },

    "coinflip_result": {
        "title": "🪙 {result} — {outcome}",
        "description": "{description}",
        "fields": [
            ("Balance", "{balance:,} Runes", True)
        ],
        "color": "gold",
        "footer": "Runi • Economy"
    },

    "richlist": {
        "title": "💰 Runeshard Rich List",
        "description": "{content}",
        "color": "gold",
        "footer": "Runi • Economy"
    },

    "give_invalid_amount": {
        "description": "Amount must be greater than 0.",
        "color": "red",
        "footer": "Runi • Economy",
    },

    "give_self_transfer": {
        "title": "❌ Nice Try",
        "description": "You can't give Runes to yourself!",
        "color": "red",
        "footer": "Runi • Economy",
    },

    "give_success": {
        "title": "💸 Runes Sent!",
        "description": "{sender} gave **{amount:,} Runes** to {receiver}!",
        "fields": [
            ("Your new balance", "{balance:,} Runes", True)
        ],
        "color": "gold",
        "footer": "Runi • Economy"
    },

    "error_insufficient_funds": {
        "title": "❌ Not Enough Runes",
        "description": "You only have {balance:,} Runes.",
        "color": "red"
    }
}