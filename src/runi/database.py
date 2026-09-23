import aiosqlite
import time
from pathlib import Path
from datetime import datetime, UTC, timedelta

from runi.config import XP_PER_MESSAGE, XP_COOLDOWN_SECONDS, XP_FOR_LEVEL


class Database:
    def __init__(self, path: str):
        self.path = path
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)

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
            # Highest gambling wins and losses
            await db.execute("""
                CREATE TABLE IF NOT EXISTS gambling_records (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id     INTEGER NOT NULL,
                    user_id      INTEGER NOT NULL,
                    display_name TEXT    NOT NULL,
                    game         TEXT    NOT NULL,
                    won          INTEGER NOT NULL,
                    amount       INTEGER NOT NULL,
                    message_url  TEXT    NOT NULL,
                    created_at   REAL    NOT NULL
                )
            """)

            # Clan Wars: registered clans within a guild (name + the Discord role
            # that identifies membership in that clan, plus an optional forum
            # channel where a new thread is created each weekly war cycle)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS clan_war_clans (
                    clan_id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id          INTEGER NOT NULL,
                    name              TEXT    NOT NULL,
                    role_id           INTEGER NOT NULL UNIQUE,
                    forum_channel_id  INTEGER
                )
            """)
            # Migration: add forum_channel_id to an already-existing clan_war_clans
            # table from before this column existed.
            try:
                await db.execute("ALTER TABLE clan_war_clans ADD COLUMN forum_channel_id INTEGER")
            except aiosqlite.OperationalError:
                pass  # column already exists

            # Clan Wars: per-member raw resource submissions (overwritten each submit)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS clan_war_resources (
                    guild_id    INTEGER NOT NULL,
                    user_id     INTEGER NOT NULL,
                    resource    TEXT    NOT NULL,
                    amount      INTEGER NOT NULL DEFAULT 0,
                    updated_at  REAL    NOT NULL DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id, resource)
                )
            """)
            # Migration: add clan_id to an already-existing clan_war_resources
            # table from before multi-clan support existed. Safe to run every
            # startup — the duplicate-column error is caught and ignored.
            try:
                await db.execute("ALTER TABLE clan_war_resources ADD COLUMN clan_id INTEGER")
            except Exception:
                pass

            # Clan Wars: admin-adjustable points-per-unit rate for each resource,
            # scoped per clan (each clan researches its own tech independently)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS clan_rates (
                    clan_id     INTEGER NOT NULL,
                    resource    TEXT    NOT NULL,
                    points      REAL    NOT NULL DEFAULT 0,
                    PRIMARY KEY (clan_id, resource)
                )
            """)
            # Clan Wars: location of each clan's own live panel message + cycle start
            await db.execute("""
                CREATE TABLE IF NOT EXISTS clan_panels (
                    clan_id           INTEGER PRIMARY KEY,
                    channel_id        INTEGER NOT NULL,
                    message_id        INTEGER NOT NULL,
                    cycle_started_at  REAL    NOT NULL DEFAULT 0
                )
            """)

            # Create indexes to optimize queries
            # Users table
            await db.execute("CREATE INDEX IF NOT EXISTS idx_users_guild_level_xp ON users(guild_id, level DESC, xp DESC)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_users_guild_runeshards ON users(guild_id, runeshards DESC)")

            # Store items table
            await db.execute("CREATE INDEX IF NOT EXISTS idx_store_items_guild_available ON store_items(guild_id, available)")

            # User inventory table
            await db.execute("CREATE INDEX IF NOT EXISTS idx_inventory_user_guild ON user_inventory(user_id, guild_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_inventory_user_guild_item ON user_inventory(user_id, guild_id, item_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_inventory_user_guild_item_join ON user_inventory(user_id, guild_id, item_id)")

            # Gambling records table
            await db.execute("CREATE INDEX IF NOT EXISTS idx_gambling_guild_won ON gambling_records(guild_id, won)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_gambling_guild_won_game ON gambling_records(guild_id, won, game)")

            # Clan war tables
            await db.execute("CREATE INDEX IF NOT EXISTS idx_clan_war_resources_clan ON clan_war_resources(clan_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_clan_war_clans_guild ON clan_war_clans(guild_id)")

            await db.commit()

    # ── Internal helper ────────────────────────────────────────────────────────
    async def _ensure_user(self, db, user_id: int, guild_id: int):
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, guild_id) VALUES (?, ?)",
            (user_id, guild_id),
        )

    async def _ensure_users_exist(self, db, guild_id: int, user_ids: list[int]):
        """
        Ensure all specified users have records in the database for a guild.
        """
        for user_id in user_ids:
            await self._ensure_user(db, user_id, guild_id)

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
            DAILY_BASE,
            DAILY_STREAK_BONUS,
            DAILY_STREAK_MAX,
        )

        now = datetime.now(UTC)
        today = now.date()
        now_ts = now.timestamp()

        async with aiosqlite.connect(self.path) as db:
            user = await self._fetch_user(db, user_id, guild_id)

            last_day = (
                datetime.fromtimestamp(user["last_daily"], UTC).date() if user["last_daily"] > 0
                else None
            )

            if last_day == today:
                next_midnight = datetime.combine(
                    today + timedelta(days=1),
                    datetime.min.time(),
                    tzinfo=UTC,
                )

                return {
                    "success": False,
                    "wait_seconds": (next_midnight - now).total_seconds(),
                }

            # Streak continues if the previous claim was yesterday (UTC).
            if last_day is None:
                new_streak = 1
            else:
                days_since = (today - last_day).days
                if days_since == 1:
                    new_streak = min(user["daily_streak"] + 1, DAILY_STREAK_MAX)
                else:
                    new_streak = 1

            # Payout scales with streak
            earned = DAILY_BASE + DAILY_STREAK_BONUS * (new_streak - 1)
            new_balance = user["runeshards"] + earned

            await db.execute(
                """UPDATE users
                   SET runeshards = ?, last_daily = ?, daily_streak = ?
                   WHERE user_id = ? AND guild_id = ?""",
                (new_balance, now_ts, new_streak, user_id, guild_id),
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

    async def add_gambling_record(
        self,
        guild_id: int,
        user_id: int,
        display_name: str,
        game: str,
        won: bool,
        amount: int,
        message_url: str,
    ):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO gambling_records (guild_id, user_id, display_name, game, won, amount, message_url, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (guild_id, user_id, display_name, game, int(won), amount, message_url, time.time())
            )

            await db.commit()


    async def get_gambling_records(self, guild_id: int, won: bool, game: str | None = None, limit: int = 10) -> list[dict]:
        query = "SELECT * FROM gambling_records WHERE guild_id = ? AND won = ?"
        params = [guild_id, int(won)]
        
        if game is not None:
            query += " AND game = ?"
            params.append(game)
        
        query += " ORDER BY amount DESC LIMIT ?"
        params.append(limit)
        
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(query, params) as cur:
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

    async def add_runes(self, user_id: int, guild_id: int, amount: int) -> dict:
        """
        Add Runes to a user.
        Returns {"success": bool, "balance": int}
        """
        async with aiosqlite.connect(self.path) as db:
            user = await self._fetch_user(db, user_id, guild_id)
            new_balance = user["runeshards"] + amount
            await db.execute(
                "UPDATE users SET runeshards = ? WHERE user_id = ? AND guild_id = ?",
                (new_balance, user_id, guild_id),
            )
            await db.commit()
        return {"success": True, "balance": new_balance}

    async def remove_runes(self, user_id: int, guild_id: int, amount: int) -> dict:
        """
        Remove Runes from a user.
        Returns {"success": bool, "reason": str, "balance": int}
        Reasons: "ok" | "insufficient_funds"
        """
        async with aiosqlite.connect(self.path) as db:
            user = await self._fetch_user(db, user_id, guild_id)
            if user["runeshards"] < amount:
                return {"success": False, "reason": "insufficient_funds", "balance": user["runeshards"]}
            new_balance = user["runeshards"] - amount
            await db.execute(
                "UPDATE users SET runeshards = ? WHERE user_id = ? AND guild_id = ?",
                (new_balance, user_id, guild_id),
            )
            await db.commit()
        return {"success": True, "reason": "ok", "balance": new_balance}

    async def add_runes_to_all(self, guild_id: int, user_ids: list[int], amount: int) -> dict:
        """
        Add Runes to specified users, creating records if they don't exist.
        Returns {"success": bool, "total_members": int, "total_distributed": int}
        """
        if not user_ids:
            return {"success": True, "total_members": 0, "total_distributed": 0}

        async with aiosqlite.connect(self.path) as db:
            await self._ensure_users_exist(db, guild_id, user_ids)

            await db.execute(
                "UPDATE users SET runeshards = runeshards + ? WHERE guild_id = ? AND user_id IN ({})".format(
                    ",".join("?" * len(user_ids))
                ),
                (amount, guild_id, *user_ids),
            )
            await db.commit()

        total_distributed = len(user_ids) * amount
        return {"success": True, "total_members": len(user_ids), "total_distributed": total_distributed}

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

        result = random.choice(["heads", "tails"])
        won = result == choice
        change = bet if won else -bet

        async with aiosqlite.connect(self.path) as db:
            user = await self._fetch_user(db, user_id, guild_id)
            if user["runeshards"] < bet:
                return {"success": False, "reason": "insufficient_funds", "balance": user["runeshards"]}
            
            new_balance = user["runeshards"] + change
            await db.execute(
                "UPDATE users SET runeshards = ? WHERE user_id = ? AND guild_id = ?",
                (new_balance, user_id, guild_id),
            )
            await db.commit()
        return {"success": True, "won": won, "result": result, "balance": new_balance, "change": abs(change)}

    async def spin_slots(self, user_id: int, guild_id: int, bet: int) -> dict:
        """
        Spin the slot machine.

        Returns:
        {
            "success": bool,
            "won": bool,
            "symbols": [str, str, str],
            "match_type": str,
            "payout": int,
            "balance": int,
            "change": int,
        }
        """
        import random

        symbols = {
            "🍒": 100,
            "🍋": 95,
            "🍊": 85,
            "🍇": 75,
            "🔔": 60,
            "⭐": 50,
            "💎": 40,
            "👑": 25,
            "💰": 15,
            "🃏": 8,  # Wild
        }

        paytable = {
            # Three of a kind
            ("🍒", 3): 4,
            ("🍋", 3): 5,
            ("🍊", 3): 7,
            ("🍇", 3): 9,
            ("🔔", 3): 13,
            ("⭐", 3): 20,
            ("💎", 3): 40,
            ("👑", 3): 80,
            ("💰", 3): 160,

            # Two of a kind
            ("🍒", 2): 0.8,
            ("🍋", 2): 0.9,
            ("🍊", 2): 1.1,
            ("🍇", 2): 1.3,
            ("🔔", 2): 1.9,
            ("⭐", 2): 2.7,
            ("💎", 2): 5.3,
            ("👑", 2): 10.6,
            ("💰", 2): 21.2,
        }

        symbol_names = tuple(symbols.keys())
        symbol_weights = tuple(symbols.values())
        wild = "🃏"

        async with aiosqlite.connect(self.path) as db:
            user = await self._fetch_user(db, user_id, guild_id)

            if user["runeshards"] < bet:
                return {
                    "success": False,
                    "balance": user["runeshards"],
                }

            result = random.choices(
                symbol_names,
                weights=symbol_weights,
                k=3,
            )

            won = False
            multiplier = 0
            match_type = ""

            if result.count(wild) == 3:
                won = True
                multiplier = 400
                match_type = "Three Wilds"

            else:
                for symbol in symbol_names:
                    if symbol == wild:
                        continue

                    matches = sum(
                        reel == symbol or reel == wild
                        for reel in result
                    )

                    payout = paytable.get((symbol, matches))
                    if payout is None:
                        continue

                    if payout > multiplier:
                        multiplier = payout

                        if matches == 3:
                            match_type = f"Three {symbol}"
                        else:
                            match_type = f"Two {symbol}"

            payout = int(bet * multiplier) if multiplier > 0 else 0
            net_change = payout - bet
            won = net_change > 0
            balance = user["runeshards"] + net_change

            await db.execute(
                "UPDATE users SET runeshards = ? WHERE user_id = ? AND guild_id = ?",
                (balance, user_id, guild_id),
            )
            await db.commit()

            return {
                "success": True,
                "won": won,
                "symbols": result,
                "match_type": match_type,
                "payout": payout,
                "balance": balance,
                "change": abs(net_change),
            }

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

    # ── Clan Wars: Clan Registry ─────────────────────────────────────────────

    async def register_clan(self, guild_id: int, name: str, role_id: int, forum_channel_id: int | None = None) -> tuple[int, bool]:
        """
        Registers a new clan, or updates an existing one if role_id is
        already registered — re-running /register with the same role
        updates the name and, if given, the forum channel (an already-set
        forum channel is left alone if forum_channel_id is None this time).
        Returns (clan_id, was_newly_created).
        """
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT clan_id FROM clan_war_clans WHERE role_id = ?", (role_id,)
            ) as cur:
                existing = await cur.fetchone()
            was_new = existing is None

            await db.execute(
                """INSERT INTO clan_war_clans (guild_id, name, role_id, forum_channel_id)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT (role_id) DO UPDATE SET
                       name = excluded.name,
                       forum_channel_id = COALESCE(excluded.forum_channel_id, clan_war_clans.forum_channel_id)""",
                (guild_id, name, role_id, forum_channel_id),
            )
            await db.commit()

            async with db.execute(
                "SELECT clan_id FROM clan_war_clans WHERE role_id = ?", (role_id,)
            ) as cur:
                row = await cur.fetchone()
                return row[0], was_new

    async def get_clan(self, clan_id: int) -> dict | None:
        """Returns {"clan_id", "guild_id", "name", "role_id", "forum_channel_id"} for one clan, or None."""
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT clan_id, guild_id, name, role_id, forum_channel_id FROM clan_war_clans WHERE clan_id = ?",
                (clan_id,),
            ) as cur:
                row = await cur.fetchone()
                if not row:
                    return None
                return {"clan_id": row[0], "guild_id": row[1], "name": row[2], "role_id": row[3], "forum_channel_id": row[4]}

    async def get_clans(self, guild_id: int) -> list[dict]:
        """Returns every registered clan for a guild as [{"clan_id", "name", "role_id", "forum_channel_id"}, ...]."""
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT clan_id, name, role_id, forum_channel_id FROM clan_war_clans WHERE guild_id = ?",
                (guild_id,),
            ) as cur:
                rows = await cur.fetchall()
        return [{"clan_id": r[0], "name": r[1], "role_id": r[2], "forum_channel_id": r[3]} for r in rows]

    # ── Clan Wars: Resource Tracking ──────────────────────────────────────────

    async def get_resource_rates(self, clan_id: int, defaults: dict[str, float]) -> dict[str, float]:
        """
        Returns {resource: points_per_unit} for a clan. Any resource missing
        a row falls back to the value in `defaults` (not persisted until changed).
        """
        rates = dict(defaults)
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT resource, points FROM clan_rates WHERE clan_id = ?",
                (clan_id,),
            ) as cur:
                async for resource, points in cur:
                    rates[resource] = points
        return rates

    async def set_resource_rate(self, clan_id: int, resource: str, points: float) -> None:
        """Set (or update) the points-per-unit rate for a resource, scoped to one clan."""
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO clan_rates (clan_id, resource, points)
                   VALUES (?, ?, ?)
                   ON CONFLICT (clan_id, resource) DO UPDATE SET points = excluded.points""",
                (clan_id, resource, points),
            )
            await db.commit()

    async def submit_clan_war_resource(self, guild_id: int, user_id: int, resource: str, amount: int, clan_id: int) -> None:
        """
        Overwrites a member's submitted amount for one resource, tagging it
        with their current clan_id (re-derived by the caller from their roles
        at submission time, so a role change takes effect on their next submit).
        """
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO clan_war_resources (guild_id, user_id, resource, amount, updated_at, clan_id)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT (guild_id, user_id, resource)
                   DO UPDATE SET amount = excluded.amount, updated_at = excluded.updated_at, clan_id = excluded.clan_id""",
                (guild_id, user_id, resource, amount, time.time(), clan_id),
            )
            await db.commit()

    async def get_clan_war_leaderboard(self, clan_id: int, defaults: dict[str, float], convert_per: dict[str, int]) -> dict:
        """
        Builds the full panel dataset for one clan.

        `convert_per` maps resource -> how many raw units make up 1
        point-earning unit (e.g. 50 Clockwinders = 1 Mount Summon). Use 1
        for resources with no conversion (points = amount * rate directly).

        Returns {
            "members": [
                {
                    "user_id": int,
                    "resources": {resource: amount, ...},
                    "converted": {resource: converted_unit_count, ...},
                    "points": float,
                    "updated_at": float,   # most recent submission across all resources
                },
                ...
            ],  # sorted by points DESC
            "totals": {resource: amount, ...},
            "totals_converted": {resource: converted_unit_count, ...},
            "total_points": float,   # exact sum of every member's points, never recalculated separately
            "rates": {resource: points_per_unit, ...},
        }
        """
        rates = await self.get_resource_rates(clan_id, defaults)

        members: dict[int, dict] = {}
        totals: dict[str, int] = {r: 0 for r in defaults}

        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT user_id, resource, amount, updated_at FROM clan_war_resources WHERE clan_id = ?",
                (clan_id,),
            ) as cur:
                rows = await cur.fetchall()

        for user_id, resource, amount, updated_at in rows:
            entry = members.setdefault(user_id, {
                "user_id": user_id,
                "resources": {r: 0 for r in defaults},
                "updated_at": 0.0,
            })
            entry["resources"][resource] = amount
            entry["updated_at"] = max(entry["updated_at"], updated_at)
            if resource in totals:
                totals[resource] += amount

        for entry in members.values():
            entry["converted"] = {
                r: entry["resources"].get(r, 0) // convert_per.get(r, 1) for r in defaults
            }
            entry["points"] = sum(
                entry["converted"][r] * rates.get(r, 0) for r in defaults
            )

        # Total points is always the exact sum of member points, never
        # recalculated independently from `totals` — this guarantees the
        # Clan Totals section can never disagree with the member rows.
        total_points = sum(entry["points"] for entry in members.values())

        totals_converted = {
            r: totals.get(r, 0) // convert_per.get(r, 1) for r in defaults
        }

        member_list = sorted(members.values(), key=lambda e: e["points"], reverse=True)

        return {
            "members": member_list,
            "totals": totals,
            "totals_converted": totals_converted,
            "total_points": total_points,
            "rates": rates,
        }

    async def reset_clan_war(self, clan_id: int) -> None:
        """Wipes all submitted resources for one clan, starting a fresh cycle."""
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM clan_war_resources WHERE clan_id = ?", (clan_id,))
            await db.execute(
                """INSERT INTO clan_panels (clan_id, channel_id, message_id, cycle_started_at)
                   VALUES (?, 0, 0, ?)
                   ON CONFLICT (clan_id) DO UPDATE SET cycle_started_at = excluded.cycle_started_at""",
                (clan_id, time.time()),
            )
            await db.commit()

    async def get_clan_war_panel(self, clan_id: int) -> dict | None:
        """Returns {"channel_id", "message_id", "cycle_started_at"} or None if never set up."""
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT channel_id, message_id, cycle_started_at FROM clan_panels WHERE clan_id = ?",
                (clan_id,),
            ) as cur:
                row = await cur.fetchone()
                if not row or row[1] == 0:
                    return None
                return {"channel_id": row[0], "message_id": row[1], "cycle_started_at": row[2]}

    async def get_clan_id_by_panel_message(self, channel_id: int, message_id: int) -> int | None:
        """Reverse lookup: given a panel message's location, which clan owns it?"""
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT clan_id FROM clan_panels WHERE channel_id = ? AND message_id = ?",
                (channel_id, message_id),
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else None

    async def set_clan_war_panel(self, clan_id: int, channel_id: int, message_id: int) -> None:
        """Records where a clan's live panel message lives, preserving cycle_started_at if already set."""
        now = time.time()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO clan_panels (clan_id, channel_id, message_id, cycle_started_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT (clan_id) DO UPDATE SET
                       channel_id = excluded.channel_id,
                       message_id = excluded.message_id""",
                (clan_id, channel_id, message_id, now),
            )
            await db.commit()
