"""Load SRD data and campaign files."""
from __future__ import annotations

import json
from pathlib import Path

from src.campaign.campaign_db import CampaignData
from src.models.monster import Monster
from src.models.spells import SpellData

_DATA_DIR = Path(__file__).parent.parent / "data" / "srd"

# Module-level caches populated by load_srd_data()
_spells: dict[str, SpellData] = {}
_monsters: dict[str, dict] = {}  # raw dicts, instantiated fresh each time
_classes: dict[str, dict] = {}
_items: dict = {}


def load_srd_data() -> None:
    """Load all SRD data into module-level caches."""
    global _spells, _monsters, _classes, _items

    spells_path = _DATA_DIR / "spells.json"
    if spells_path.exists():
        raw = json.loads(spells_path.read_text())
        _spells = {s["name"].lower(): SpellData.model_validate(s) for s in raw}

    monsters_path = _DATA_DIR / "monsters.json"
    if monsters_path.exists():
        raw = json.loads(monsters_path.read_text())
        _monsters = {m["id"]: m for m in raw}

    classes_path = _DATA_DIR / "classes.json"
    if classes_path.exists():
        _classes = json.loads(classes_path.read_text())

    items_path = _DATA_DIR / "items.json"
    if items_path.exists():
        _items = json.loads(items_path.read_text())


def get_spell(name: str) -> SpellData | None:
    """Look up a spell by name (case-insensitive)."""
    return _spells.get(name.lower())


def get_monster_template(monster_id: str) -> Monster:
    """Create a fresh Monster instance from the SRD template."""
    raw = _monsters.get(monster_id)
    if raw is None:
        raise KeyError(f"Monster template not found: {monster_id!r}")
    # Deep copy via JSON round-trip to ensure fresh mutable instance
    return Monster.model_validate(json.loads(json.dumps(raw)))


def get_class_data(class_name: str) -> dict:
    """Return class data dict (hit_die, spell_slots_by_level, etc.)."""
    return _classes.get(class_name, {})


def load_campaign(path: str | Path) -> CampaignData:
    """Load a campaign JSON file."""
    data = json.loads(Path(path).read_text())
    return CampaignData.model_validate(data)
