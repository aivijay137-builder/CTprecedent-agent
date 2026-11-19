"""Reads the pack files (YAML) from PACKS_DIR (default: Prompts/packs). Nothing is cached across file changes."""
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
REQUIRED = ("id", "level", "version", "status", "routing", "prompt_addon")
_cache: dict = {}


def packs_dir() -> Path:
    p = os.environ.get("PACKS_DIR")
    return Path(p) if p else ROOT / "Prompts" / "packs"


def _files(d: Path) -> list[Path]:
    return [d / "_base.yaml"] + sorted((d / "areas").glob("*.yaml")) + sorted((d / "indications").glob("*.yaml"))


def available() -> bool:
    """True when pack files exist on this machine. The live site has none yet, so it shows no pack options."""
    d = packs_dir()
    return (d / "_base.yaml").exists() and any((d / "areas").glob("*.yaml"))


def load_all() -> dict[str, dict]:
    """{pack id: pack}. Raises ValueError naming the file when a pack is missing a required key."""
    d = packs_dir()
    files = [f for f in _files(d) if f.exists()]
    stamp = tuple((str(f), f.stat().st_mtime_ns) for f in files)
    if _cache.get("stamp") == stamp:
        return _cache["packs"]
    out = {}
    for f in files:
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        missing = [k for k in REQUIRED if k not in data]
        if missing:
            raise ValueError(f"{f.name}: missing {missing}")
        out[data["id"]] = data
    _cache.update(stamp=stamp, packs=out)
    return out


def summary(packs: dict) -> list[dict]:
    """What the screen needs to list the packs: id, level, label, version, status."""
    return [{"id": p["id"], "level": p["level"], "label": p.get("label", p["id"]), "version": p["version"], "status": p["status"], "parent": p["routing"].get("parent")}
            for p in packs.values() if p["level"] != "base"]
