from datetime import datetime


class Color:
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"


def _log(color: str, label: str, msg: str):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"{color}[{now}] [{label}] {msg}{Color.RESET}")


def info(msg: str):
    _log(Color.CYAN, "INFO", msg)


def success(msg: str):
    _log(Color.GREEN, "OK", msg)


def warn(msg: str):
    _log(Color.YELLOW, "WARN", msg)


def error(msg: str):
    _log(Color.RED, "ERROR", msg)