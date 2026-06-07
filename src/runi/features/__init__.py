import importlib
import pkgutil
from pathlib import Path


def merge_embeds(*embed_sets):
    merged = {}
    for embed_set in embed_sets:
        overlap = merged.keys() & embed_set.keys()
        if overlap:
            raise ValueError(f"Duplicate template keys detected: {', '.join(sorted(overlap))}")

        merged.update(embed_set)

    return merged


embeds = {}
features_root = Path(__file__).resolve().parent

for module_path in features_root.rglob("*.py"):
    if module_path.name.startswith("_"):
        continue
    if module_path.name == "__init__.py":
        continue
    if module_path.name != "embeds.py":
        continue

    relative_parts = module_path.relative_to(features_root).with_suffix("").parts
    module_name = ".".join((__name__,) + relative_parts)

    try:
        mod = importlib.import_module(module_name)
    except Exception:
        continue

    embed_set = getattr(mod, "EMBEDS", None)
    if embed_set:
        embeds = merge_embeds(embeds, embed_set)
