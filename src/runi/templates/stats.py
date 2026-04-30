TEMPLATES = {
    "max_substats": {
        "title": "Max substats",
        "description": (
            "All values marked with a * can exceed 100% visually but have no effect beyond it."
        ),
        "fields": [
            ("Attack Speed", "40%", True),
            ("Block Chance", "5%", True),
            ("Critical Chance", "12%*", True),
            ("Critical Damage", "100%", True),
            ("Damage", "15%", True),
            ("Double Chance", "40%*", True),
            ("Health", "15%", True),
            ("Health Regen", "6%", True),
            ("Lifesteal", "20%", True),
            ("Melee Damage", "50%", True),
            ("Ranged Damage", "15%", True),
            ("Skill Cooldown", "7%", True),
            ("Skill Damage", "30%", True),
        ]
    },
    "health_formula": {
        "title": "Health formula",
        "description": (
            "The health formula is as follows:"
        ),
        "fields": [
            ("Flat Health", "Player Base Health + Gear Base Health + Pet Base Health + Skill Passive Health", False),
            ("Additive Health", "Mount Health% + Health% substats", False),
            ("Skin Health", "Skins Health% + Skin Set Bonus (only with full set)", False),
            ("Total Health", "Flat Health x Additive Health x Skin Health", False)
        ]
    },
    "damage_formula": {
        "title": "Damage formula",
        "description": (
            "The damage formula is as follows:"
        ),
        "fields": [
            ("Flat Damage", "Player Base Damage + Gear Base Damage + Pet Base Damage + Skill Passive Damage", False),
            ("Additive Damage", "Mount Damage% + Damage% substats", False),
            ("Weapon Damage", "Melee or Ranged Damage% (when using the respective weapon)", False),
            ("Skin Damage", "Skins Damage% + Skin Set Bonus (only with full set)", False),
            ("Total Damage", "Flat Damage x Additive Damage x Weapon Damage x Skin Damage", False)
        ]
    }
}