from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]

# Data directories and paths
DATA_DIR = BASE_DIR / "data"
DB_DIR = DATA_DIR / "db"
STATIC_DIR = DATA_DIR / "static"
BOT_DATA_DB_PATH = DB_DIR / "bot_data.db"
CLOCKWINDERS_CSV = STATIC_DIR / "clockwinders.csv"
EGGSHELLS_CSV = STATIC_DIR / "eggshells.csv"
SKILL_TICKETS_CSV = STATIC_DIR / "skill_tickets.csv"