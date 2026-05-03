TEMPLATES = {
    "profile": {
        "title": "🧙 {username}'s Profile",
        "thumbnail": "{avatar}",
        "fields": [
            ("Level", "{level}", True),
            ("Total XP", "{xp:,}", True),
            ("Runes 💎", "{runeshards:,}", True),
            ("Progress to Level {next_level}", "`{bar}` {xp_into_level:,} / {xp_span:,} XP", False),
            ("Daily Streak", "{daily_streak} 🔥", True),
            ("Items Owned", "{item_count}", True)
        ],
        "color": "blurple",
        "footer": "Runi • Profile"
    },

    "rank": {
        "title": "⚡ {username}'s Rank",
        "thumbnail": "{avatar}",
        "fields": [
            ("Level", "{level}", True),
            ("Total XP", "{xp:,}", True),
            ("Progress to Level {next_level}", "`{bar}` {xp_into_level:,} / {xp_span:,} XP", False),
        ],
        "color": "blurple",
        "footer": "Runi • XP System"        
    },

    "xp_leaderboard": {
        "title": "🏆 XP Leaderboard",
        "description": "{content}",
        "color": "blurple",
        "footer": "Runi • XP System | Earn {xp_per_message} XP per message (cooldown: {cooldown}s)"
    }
}