import aiosqlite
import time

from runi.config import XP_PER_MESSAGE, XP_COOLDOWN_SECONDS, XP_FOR_LEVEL


class Database:
    def __init__(self, path: str):
        self.path = path

    # ── Schema ─────────────────────────────────────────────────────────────────
    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id     INTEGER NOT NULL,
                    guild_id    INTEGER NOT NULL,
                    xp          INTEGER NOT NULL DEFAULT 0,
                    level       INTEGER NOT NULL DEFAULT 0,
                    last_xp_ts  REAL    NOT NULL DEFAULT 0,
                    runeshards  INTEGER NOT NULL DEFAULT 0,
                    last_work   REAL    NOT NULL DEFAULT 0,
                    last_daily  REAL    NOT NULL DEFAULT 0,
                    daily_streak INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, guild_id)
                )
            """)
            # Store items catalogue
            await db.execute("""
                CREATE TABLE IF NOT EXISTS store_items (
                    item_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id    INTEGER NOT NULL,
                    name        TEXT    NOT NULL,
                    description TEXT    NOT NULL DEFAULT '',
                    price       INTEGER NOT NULL,
                    type        TEXT    NOT NULL DEFAULT 'item',
                    role_id     INTEGER,
                    available   INTEGER NOT NULL DEFAULT 1
                )
            """)
            # Items owned by users
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_inventory (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NOT NULL,
                    guild_id    INTEGER NOT NULL,
                    item_id     INTEGER NOT NULL,
                    purchased_at REAL   NOT NULL,
                    FOREIGN KEY (item_id) REFERENCES store_items(item_id)
                )
            """)
            await db.commit()

    # ── Internal helper ────────────────────────────────────────────────────────
    async def _ensure_user(self, db, user_id: int, guild_id: int):
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, guild_id) VALUES (?, ?)",
            (user_id, guild_id),
        )

    async def _fetch_user(self, db, user_id: int, guild_id: int) -> dict:
        await self._ensure_user(db, user_id, guild_id)
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        ) as cur:
            row = await cur.fetchone()
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))

    # ── XP / Leveling ──────────────────────────────────────────────────────────
    async def add_xp(self, user_id: int, guild_id: int) -> dict:
        """
        Awards XP for a message (subject to cooldown).
        Returns {"leveled_up": bool, "new_level": int}.
        """
        now = time.time()
        async with aiosqlite.connect(self.path) as db:
            user = await self._fetch_user(db, user_id, guild_id)

            # Cooldown check
            if now - user["last_xp_ts"] < XP_COOLDOWN_SECONDS:
                return {"leveled_up": False, "new_level": user["level"]}

            new_xp = user["xp"] + XP_PER_MESSAGE
            new_level = user["level"]
            leveled_up = False

            # Check for level-up(s)
            while new_xp >= XP_FOR_LEVEL(new_level + 1):
                new_level += 1
                leveled_up = True

            await db.execute(
                """UPDATE users
                   SET xp = ?, level = ?, last_xp_ts = ?
                   WHERE user_id = ? AND guild_id = ?""",
                (new_xp, new_level, now, user_id, guild_id),
            )
            await db.commit()

        return {"leveled_up": leveled_up, "new_level": new_level}

    async def get_user(self, user_id: int, guild_id: int) -> dict:
        async with aiosqlite.connect(self.path) as db:
            return await self._fetch_user(db, user_id, guild_id)

    async def get_leaderboard(self, guild_id: int, limit: int = 10) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                """SELECT user_id, xp, level
                   FROM users
                   WHERE guild_id = ?
                   ORDER BY level DESC, xp DESC
                   LIMIT ?""",
                (guild_id, limit),
            ) as cur:
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in await cur.fetchall()]

    # ── Economy ────────────────────────────────────────────────────────────────
    async def do_work(self, user_id: int, guild_id: int) -> dict:
        """
        Attempt a /work action.
        Returns {"success": bool, "earned": int, "balance": int, "wait_seconds": float}
        """
        from .config import WORK_COOLDOWN_SECONDS, WORK_MIN, WORK_MAX
        import random

        now = time.time()
        async with aiosqlite.connect(self.path) as db:
            user = await self._fetch_user(db, user_id, guild_id)
            elapsed = now - user["last_work"]

            if elapsed < WORK_COOLDOWN_SECONDS:
                return {
                    "success": False,
                    "wait_seconds": WORK_COOLDOWN_SECONDS - elapsed,
                }

            earned = random.randint(WORK_MIN, WORK_MAX)
            new_balance = user["runeshards"] + earned

            await db.execute(
                """UPDATE users
                   SET runeshards = ?, last_work = ?
                   WHERE user_id = ? AND guild_id = ?""",
                (new_balance, now, user_id, guild_id),
            )
            await db.commit()

        return {"success": True, "earned": earned, "balance": new_balance}

    async def do_daily(self, user_id: int, guild_id: int) -> dict:
        """
        Attempt a /daily action.
        Returns {"success": bool, "earned": int, "balance": int,
                 "streak": int, "wait_seconds": float}
        """
        from .config import (
            DAILY_COOLDOWN_SECONDS,
            DAILY_BASE,
            DAILY_STREAK_BONUS,
            DAILY_STREAK_MAX,
            DAILY_STREAK_RESET_WINDOW,
        )

        now = time.time()
        async with aiosqlite.connect(self.path) as db:
            user = await self._fetch_user(db, user_id, guild_id)
            elapsed = now - user["last_daily"]

            if elapsed < DAILY_COOLDOWN_SECONDS:
                return {
                    "success": False,
                    "wait_seconds": DAILY_COOLDOWN_SECONDS - elapsed,
                }

            # Streak logic: reward extends streak; gap beyond reset window breaks it
            if elapsed < DAILY_STREAK_RESET_WINDOW:
                new_streak = min(user["daily_streak"] + 1, DAILY_STREAK_MAX)
            else:
                new_streak = 1  # streak broken, restart

            # Payout scales with streak
            earned = DAILY_BASE + DAILY_STREAK_BONUS * (new_streak - 1)
            new_balance = user["runeshards"] + earned

            await db.execute(
                """UPDATE users
                   SET runeshards = ?, last_daily = ?, daily_streak = ?
                   WHERE user_id = ? AND guild_id = ?""",
                (new_balance, now, new_streak, user_id, guild_id),
            )
            await db.commit()

        return {
            "success": True,
            "earned": earned,
            "balance": new_balance,
            "streak": new_streak,
        }

    async def get_balance(self, user_id: int, guild_id: int) -> int:
        user = await self.get_user(user_id, guild_id)
        return user["runeshards"]

    async def get_rich_list(self, guild_id: int, limit: int = 10) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                """SELECT user_id, runeshards, daily_streak
                   FROM users
                   WHERE guild_id = ?
                   ORDER BY runeshards DESC
                   LIMIT ?""",
                (guild_id, limit),
            ) as cur:
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in await cur.fetchall()]

    async def transfer_runes(self, from_id: int, to_id: int, guild_id: int, amount: int) -> dict:
        """
        Transfer Runes from one user to another.
        Returns {"success": bool, "reason": str, "from_balance": int, "to_balance": int}
        Reasons: "ok" | "insufficient_funds" | "self_transfer"
        """
        if from_id == to_id:
            return {"success": False, "reason": "self_transfer"}
        async with aiosqlite.connect(self.path) as db:
            sender = await self._fetch_user(db, from_id, guild_id)
            if sender["runeshards"] < amount:
                return {"success": False, "reason": "insufficient_funds", "balance": sender["runeshards"]}
            receiver = await self._fetch_user(db, to_id, guild_id)
            new_from = sender["runeshards"] - amount
            new_to = receiver["runeshards"] + amount
            await db.execute(
                "UPDATE users SET runeshards = ? WHERE user_id = ? AND guild_id = ?",
                (new_from, from_id, guild_id),
            )
            await db.execute(
                "UPDATE users SET runeshards = ? WHERE user_id = ? AND guild_id = ?",
                (new_to, to_id, guild_id),
            )
            await db.commit()
        return {"success": True, "reason": "ok", "from_balance": new_from, "to_balance": new_to}

    async def transfer_item(self, from_id: int, to_id: int, guild_id: int, item_id: int) -> dict:
        """
        Transfer an owned item from one user to another.
        Returns {"success": bool, "reason": str, "item": dict}
        Reasons: "ok" | "not_owned" | "self_transfer" | "already_owned"
        """
        import time as _time
        if from_id == to_id:
            return {"success": False, "reason": "self_transfer"}
        async with aiosqlite.connect(self.path) as db:
            # Check sender owns the item
            async with db.execute(
                """SELECT i.id, s.name, s.description, s.type, s.role_id
                   FROM user_inventory i
                   JOIN store_items s ON s.item_id = i.item_id
                   WHERE i.user_id = ? AND i.guild_id = ? AND i.item_id = ?""",
                (from_id, guild_id, item_id),
            ) as cur:
                row = await cur.fetchone()
                if not row:
                    return {"success": False, "reason": "not_owned"}
                inv_id = row[0]
                item = {"name": row[1], "description": row[2], "type": row[3], "role_id": row[4], "item_id": item_id}

            # Check receiver doesn't already own it
            async with db.execute(
                "SELECT id FROM user_inventory WHERE user_id = ? AND guild_id = ? AND item_id = ?",
                (to_id, guild_id, item_id),
            ) as cur:
                if await cur.fetchone():
                    return {"success": False, "reason": "already_owned", "item": item}

            # Transfer ownership
            await db.execute(
                "UPDATE user_inventory SET user_id = ?, purchased_at = ? WHERE id = ?",
                (to_id, _time.time(), inv_id),
            )
            await db.commit()
        return {"success": True, "reason": "ok", "item": item}

    async def coinflip(self, user_id: int, guild_id: int, bet: int, choice: str) -> dict:
        """
        Flip a coin. choice should be 'heads' or 'tails'.
        Returns {"success": bool, "reason": str, "won": bool, "result": str, "balance": int, "change": int}
        """
        import random
        async with aiosqlite.connect(self.path) as db:
            user = await self._fetch_user(db, user_id, guild_id)
            if user["runeshards"] < bet:
                return {"success": False, "reason": "insufficient_funds", "balance": user["runeshards"]}
            result = random.choice(["heads", "tails"])
            won = result == choice
            change = bet if won else -bet
            new_balance = user["runeshards"] + change
            await db.execute(
                "UPDATE users SET runeshards = ? WHERE user_id = ? AND guild_id = ?",
                (new_balance, user_id, guild_id),
            )
            await db.commit()
        return {"success": True, "won": won, "result": result, "balance": new_balance, "change": abs(change)}

    # ── Store ──────────────────────────────────────────────────────────────────
    async def get_store_items(self, guild_id: int) -> list[dict]:
        """Return all available items in the store."""
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                """SELECT * FROM store_items
                   WHERE guild_id = ? AND available = 1
                   ORDER BY type, price""",
                (guild_id,),
            ) as cur:
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in await cur.fetchall()]

    async def get_store_item(self, item_id: int, guild_id: int) -> dict | None:
        """Return a single store item by ID."""
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT * FROM store_items WHERE item_id = ? AND guild_id = ? AND available = 1",
                (item_id, guild_id),
            ) as cur:
                row = await cur.fetchone()
                if not row:
                    return None
                cols = [d[0] for d in cur.description]
                return dict(zip(cols, row))

    async def purchase_item(self, user_id: int, guild_id: int, item_id: int) -> dict:
        """
        Attempt to purchase an item.
        Returns {"success": bool, "reason": str, "balance": int, "item": dict}
        Reasons: "ok" | "not_found" | "insufficient_funds" | "already_owned"
        """
        import time as _time
        async with aiosqlite.connect(self.path) as db:
            # Fetch item
            async with db.execute(
                "SELECT * FROM store_items WHERE item_id = ? AND guild_id = ? AND available = 1",
                (item_id, guild_id),
            ) as cur:
                row = await cur.fetchone()
                if not row:
                    return {"success": False, "reason": "not_found"}
                cols = [d[0] for d in cur.description]
                item = dict(zip(cols, row))

            # Check if already owned (for roles and unique items)
            async with db.execute(
                """SELECT id FROM user_inventory
                   WHERE user_id = ? AND guild_id = ? AND item_id = ?""",
                (user_id, guild_id, item_id),
            ) as cur:
                if await cur.fetchone():
                    return {"success": False, "reason": "already_owned", "item": item}

            # Fetch user balance
            user = await self._fetch_user(db, user_id, guild_id)
            if user["runeshards"] < item["price"]:
                return {
                    "success": False,
                    "reason": "insufficient_funds",
                    "balance": user["runeshards"],
                    "item": item,
                }

            # Deduct cost and record purchase
            new_balance = user["runeshards"] - item["price"]
            await db.execute(
                "UPDATE users SET runeshards = ? WHERE user_id = ? AND guild_id = ?",
                (new_balance, user_id, guild_id),
            )
            await db.execute(
                "INSERT INTO user_inventory (user_id, guild_id, item_id, purchased_at) VALUES (?, ?, ?, ?)",
                (user_id, guild_id, item_id, _time.time()),
            )
            await db.commit()

        return {"success": True, "reason": "ok", "balance": new_balance, "item": item}

    async def get_inventory(self, user_id: int, guild_id: int) -> list[dict]:
        """Return all items owned by a user."""
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                """SELECT s.item_id, s.name, s.description, s.price, s.type, s.role_id,
                          i.purchased_at
                   FROM user_inventory i
                   JOIN store_items s ON s.item_id = i.item_id
                   WHERE i.user_id = ? AND i.guild_id = ?
                   ORDER BY i.purchased_at DESC""",
                (user_id, guild_id),
            ) as cur:
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in await cur.fetchall()]

    async def add_store_item(
        self,
        guild_id: int,
        name: str,
        description: str,
        price: int,
        item_type: str = "item",
        role_id: int | None = None,
    ) -> int:
        """Add a new item to the store. Returns the new item_id."""
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                """INSERT INTO store_items (guild_id, name, description, price, type, role_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (guild_id, name, description, price, item_type, role_id),
            )
            await db.commit()
            
            item_id = cur.lastrowid
            if item_id is None: 
                raise RuntimeError("Failed to insert store item")
            return item_id

    async def remove_store_item(self, item_id: int, guild_id: int) -> bool:
        """Soft-delete an item from the store. Returns True if found."""
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "UPDATE store_items SET available = 0 WHERE item_id = ? AND guild_id = ?",
                (item_id, guild_id),
            )
            await db.commit()
            return cur.rowcount > 0
