def truncate(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    
    return text[:limit - 3] + "..."


class SafeDict(dict):
    def __missing__(self, key):
        return f"{{{key}}}"