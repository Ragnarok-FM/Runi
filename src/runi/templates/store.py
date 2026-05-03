TEMPLATES = {
    "store": {
        "title": "🛒 Runeshard Store",
        "description": "{description}",
        "color": "gold",
        "footer": "Runi • Economy"
    },

    "store_purchase_failed": {
        "title": "❌ Purchase Failed",
        "description": "{description}",
        "color": "red",
        "footer": "Runi • Economy"
    },

    "store_purchase_success": {
        "title": "✅ Purchase Successful!",
        "description": "You bought **{name}** for {price:,} Runes.",
        "fields": [
            ("Remaining Balance", "{balance:,} Runes", True)
        ],
        "color": "gold",
        "footer": "Runi • Economy"
    },

    "inventory": {
        "title": "🎒 {username}'s Inventory",
        "description": "{content}",
        "color": "blurple",
        "footer": "Runi • Profile",
    },

    "store_gift_success": {
        "title": "🎁 Gift Sent!",
        "description": "{sender} gifted **{item}** to {receiver}!",
        "footer": "Runi • Economy",
        "color": "gold"
    },

    "store_gift_error": {
        "title": "{title}",
        "description": "{description}",
        "color": "red",
        "footer": "Runi • Economy"
    },

    "store_add_item": {
        "title": "✅ Item Added",
        "description": "**{name}** (ID: `#{id}`) added to the store for {price:,} Runes.",
        "color": "green",
        "footer": "Runi • Economy"
    },

    "store_remove_item_success": {
        "title": "🗑️ Item Removed",
        "description": "Item `#{id}` has been removed from the store.",
        "color": "green",
        "footer": "Runi • Economy"
    },

    "store_remove_item_not_found": {
        "title": "❌ Not Found",
        "description": "No active item with ID `#{id}` was found.",
        "color": "red",
        "footer": "Runi • Economy"
    }
}