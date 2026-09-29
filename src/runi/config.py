# ══════════════════════════════════════════════════════════════════════════════
#  Bot Configuration
#  Edit these values to tune the bot's behaviour without touching any logic.
# ══════════════════════════════════════════════════════════════════════════════

# ── XP & Leveling ─────────────────────────────────────────────────────────────

# XP awarded per qualifying message
XP_PER_MESSAGE: int = 15

# Minimum seconds between XP awards for the same user (anti-spam)
XP_COOLDOWN_SECONDS: float = 60.0

# Formula: how much *total* XP is needed to reach a given level.
# Default uses a quadratic curve: level 1 = 100 XP, level 10 = 10 000 XP, etc.
def XP_FOR_LEVEL(level: int) -> int:
    return 100 * (level ** 2)


# ── Economy – /work ───────────────────────────────────────────────────────────

# Cooldown between /work uses (seconds).  3600 = 1 hour
WORK_COOLDOWN_SECONDS: float = 3600.0

# Random payout range (inclusive) for /work
WORK_MIN: int = 50
WORK_MAX: int = 150


# ── Economy – /daily ──────────────────────────────────────────────────────────


# Base payout for /daily (streak day 1)
DAILY_BASE: int = 300

# Extra Runes added per additional streak day
DAILY_STREAK_BONUS: int = 50

# Maximum streak that can be accumulated (caps the bonus)
DAILY_STREAK_MAX: int = 30

# ── Clan Wars ─────────────────────────────────────────────────────────────────
# (Paste at the bottom of runi/config.py. The two imports can stay here or be
#  moved to the top of the file — either works.)
 
from datetime import time as _time
from zoneinfo import ZoneInfo
 
# Weekly war cycle. The war runs Tuesday–Sunday and each in-game day resets at
# 02:00 local time, so the last war day ends at 02:00 Monday. The turnover
# (post final report, reset resources, open a new forum thread) runs one minute
# later, at 02:01 Monday, so members can submit right up to the reset.
# Uses a real IANA timezone (not a fixed UTC offset) so it stays correct across
# CET/CEST daylight-saving changes.
WAR_RESET_TIMEZONE = ZoneInfo("Europe/Stockholm")
WAR_RESET_WEEKDAY: int = 0          # Monday=0 … Sunday=6 (datetime.weekday())
WAR_RESET_TIME = _time(hour=2, minute=1, tzinfo=WAR_RESET_TIMEZONE)
 
# How often every clan's panel re-renders on its own (seconds). 600 = 10 minutes
CLAN_WARS_AUTO_REFRESH_SECONDS: int = 10 * 60
 
# A member's row gets a ⚠️ once their last submission is older than this (seconds)
CLAN_WARS_STALE_AFTER_SECONDS: int = 7 * 24 * 60 * 60
 
# Members shown per page on the live panel and in the weekly report
CLAN_WARS_MEMBERS_PER_PAGE: int = 10
 
# How long the clan picker in admin commands reuses the clan list before
# asking the database again (seconds). Autocomplete fires on every keystroke.
CLAN_WARS_CLAN_CACHE_SECONDS: float = 30.0