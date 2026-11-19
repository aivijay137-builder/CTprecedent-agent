"""Combines the chosen packs: base, then area, then indication. The more specific one wins when both define the same named item.
The result ("effective pack") is plain data that the engine reads; it carries the parts switches the design lead set."""
DEFAULT_PARTS = {"addon": True, "ranking": True, "hard_filter": True, "era": False}  # era is off by default: its breakpoints are unreviewed drafts (EVALS D20)
FIELD_HINT_LIMIT = 8  # measure hints per pack added to the add-on text


def _by_name(*lists) -> list[dict]:
    out: dict[str, dict] = {}
    for items in lists:
        for it in items or []:
            out[it["name"]] = it          # a later (more specific) pack replaces an earlier item of the same name
    return list(out.values())


def _field_hints(pack: dict) -> str:
    fs = (pack.get("extraction_fields") or [])[:FIELD_HINT_LIMIT]
    if not fs:
        return ""
    bits = [f"{f['name']} ({f['unit']})" if f.get("unit") else f["name"] for f in fs]
    return "Measures often stated in these trials: " + ", ".join(bits) + "."


def addon_text(area: dict | None, indication: dict | None) -> str:
    """Area notes first, indication notes last (the later text is the more specific)."""
    parts = []
    for tag, p in (("AREA", area), ("INDICATION", indication)):
        if p:
            parts.append(f"{tag} NOTES ({p.get('label', p['id'])}): {p['prompt_addon'].strip()} {_field_hints(p)}".strip())
    return "\n\n".join(parts)


def merge(packs: dict, area_id: str | None, indication_id: str | None, parts: dict | None = None) -> dict | None:
    """The effective pack, or None when no pack is chosen (the base prompt alone)."""
    area, ind = (packs.get(area_id) if area_id else None), (packs.get(indication_id) if indication_id else None)
    if not area and not ind:
        return None
    base = packs.get("_base") or {}
    chosen = [p for p in (area, ind) if p]
    sw = {**DEFAULT_PARTS, **(parts or {})}
    split = (ind or {}).get("intervention_split") or (area or {}).get("intervention_split")
    statuses = {p["status"] for p in chosen}
    return {
        "ids": [p["id"] for p in chosen],
        "label": " > ".join(p.get("label", p["id"]) for p in chosen),
        "versions": {p["id"]: p["version"] for p in chosen},
        "status": statuses.pop() if len(statuses) == 1 else "mixed",
        "parts": sw,
        "addon_text": addon_text(area, ind),
        "subtypes": _by_name(base.get("subtypes"), *(p.get("subtypes") for p in chosen)),
        "archetypes": _by_name(base.get("trial_archetypes"), *(p.get("trial_archetypes") for p in chosen)),
        "eras": _by_name(base.get("era_breakpoints"), *(p.get("era_breakpoints") for p in chosen)),
        "intervention_split": split,
    }


def addon_for(effective: dict | None) -> str:
    """The text appended to the base prompt: empty when no pack is chosen or the add-on switch is off."""
    return effective["addon_text"] if effective and effective["parts"].get("addon") else ""
