from runi.templates.general import TEMPLATES as GENERAL
from runi.templates.stats import TEMPLATES as STATS
from runi.templates.economy import TEMPLATES as ECONOMY
from runi.templates.leveling import TEMPLATES as LEVELING
from runi.templates.store import TEMPLATES as STORE

def merge_templates(*dicts):
    merged = {}
    for d in dicts:
        overlap = set(merged.keys()) & set(d.keys())
        if overlap:
            raise ValueError(f"Duplicate template keys detected: {overlap}")
        
        merged.update(d)

    return merged


templates = merge_templates(
    GENERAL,
    STATS,
    ECONOMY,
    LEVELING,
    STORE
)