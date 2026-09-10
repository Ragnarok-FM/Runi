# Resource definitions for the Clan Wars panel.
#
# `emoji` refers to a custom application emoji name (registered via
# EmojiRegistry) — e.g. "Hammers" maps to a :Hammers: token that
# embed_renderer.py will substitute with the real emoji mention.
# Make sure emojis with these exact names exist as application emojis,
# otherwise they'll fall back to plain ":name:" text (see emojis.py).

RESOURCES = {
    "hammers": {
        "label": "Hammers",
        "emoji": "Hammers",
        "style": "primary",   # blue
        "has_points": False,
        "default_rate": 0,
    },
    "clockwinders": {
        "label": "Clockwinders",
        "emoji": "Clockwinders",
        "style": "primary",
        "has_points": True,
        "default_rate": 600,
    },
    "eggshells": {
        "label": "Eggshells",
        "emoji": "Eggshells",
        "style": "primary",
        "has_points": False,
        "default_rate": 0,
    },
    "skill_tickets": {
        "label": "Skill Tickets",
        "emoji": "SkillTickets",
        "style": "primary",
        "has_points": True,
        "default_rate": 125,
    },
    "mount_merges": {
        "label": "Mount Merges",
        "emoji": "MountMerges",
        "style": "success",   # green
        "has_points": True,
        "default_rate": 600,
    },
    "pet_merges": {
        "label": "Pet Merges",
        "emoji": "PetMerges",
        "style": "success",
        "has_points": True,
        "default_rate": 1250,
    },
    "tech_potions": {
        "label": "Tech Potions",
        "emoji": "TechPotions",
        "style": "success",
        "has_points": False,
        "default_rate": 0,
    },
    "gems_for_tech": {
        "label": "Gems for Tech",
        "emoji": "GemsForTech",
        "style": "success",
        "has_points": False,
        "default_rate": 0,
    },
}

# Convenience lookups
DEFAULT_RATES = {key: meta["default_rate"] for key, meta in RESOURCES.items()}
SCORING_RESOURCES = [key for key, meta in RESOURCES.items() if meta["has_points"]]

# Role allowed to submit resources via the panel buttons
PARTICIPANT_ROLE_ID = 1447639376157868289

MEMBERS_PER_PAGE = 10
STALE_AFTER_SECONDS = 7 * 24 * 60 * 60  # 7 days
AUTO_REFRESH_SECONDS = 10 * 60  # 10 minutes
