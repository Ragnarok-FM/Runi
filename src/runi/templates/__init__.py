from runi.templates.stats import TEMPLATES as STATS

def merge_templates(*dicts):
    merged = {}
    for d in dicts:
        overlap = set(merged.keys()) & set(d.keys())
        if overlap:
            raise ValueError(f"Duplicate template keys detected: {overlap}")
        
        merged.update(d)

    return merged


templates = merge_templates(
    STATS
)