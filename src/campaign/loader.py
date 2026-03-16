"""Load SRD data and campaign files (JSON or YAML directory).

SRD lookups are delegated to src.data.srd_client, which provides:
  - Local file cache + remote API (dnd5eapi.co) for 300+ monsters, 300+ spells
  - Backward-compatible fallback to legacy static JSON files
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from src.campaign.campaign_db import (
    CampaignData,
    CampaignIndex,
    EntityRef,
)
from src.data.srd_client import (
    get_monster_template,
    get_spell,
    load_srd_data,
)
from src.models.monster import Monster
from src.models.spells import SpellData

# Re-export for backward compat (other modules import from here)
__all__ = ["get_monster_template", "get_spell", "load_srd_data", "load_campaign", "validate_campaign"]

# Mapping from subdirectory name to entity type
_DIR_TO_TYPE = {
    "locations": "location",
    "npcs": "npc",
    "factions": "faction",
    "plot_hooks": "plot_hook",
    "encounters": "encounter",
}


# ---------------------------------------------------------------------------
# Campaign loading
# ---------------------------------------------------------------------------

def load_campaign(path: str | Path) -> CampaignData:
    """Load a campaign from a JSON file or a YAML directory.

    Detects format automatically:
    - If path is a file ending in .json → legacy single-file JSON.
    - If path is a directory → new YAML directory format.
    """
    path = Path(path)

    if path.is_dir():
        return _load_campaign_directory(path)

    # Legacy JSON file
    data = json.loads(path.read_text())
    return CampaignData.from_dict(data)


def _load_campaign_directory(campaign_dir: Path) -> CampaignData:
    """Load a directory-based YAML campaign and build an index."""
    campaign_file = campaign_dir / "campaign.yaml"
    if not campaign_file.exists():
        raise FileNotFoundError(
            f"Campaign directory missing campaign.yaml: {campaign_dir}"
        )

    meta = yaml.safe_load(campaign_file.read_text())
    index = CampaignIndex(
        title=meta.get("title", ""),
        setting_overview=meta.get("setting_overview", ""),
        starting_location_id=meta.get("starting_location_id", ""),
    )

    # Scan subdirectories for entity files
    for subdir_name, entity_type in _DIR_TO_TYPE.items():
        subdir = campaign_dir / subdir_name
        if not subdir.is_dir():
            continue
        for yaml_file in sorted(subdir.glob("*.yaml")):
            raw = yaml.safe_load(yaml_file.read_text())
            if raw is None:
                continue
            entity_id = raw.get("id", yaml_file.stem)
            entity_name = raw.get("name", raw.get("title", entity_id))
            ref = EntityRef(
                entity_type=entity_type,
                entity_id=entity_id,
                file_path=yaml_file,
                name=entity_name,
            )
            index.refs[(entity_type, entity_id)] = ref

    return CampaignData(index=index)


# ---------------------------------------------------------------------------
# Cross-reference validation
# ---------------------------------------------------------------------------

def validate_campaign(campaign: CampaignData) -> list[str]:
    """Validate all cross-references in a campaign. Returns list of errors."""
    errors: list[str] = []

    # Collect all known IDs by type
    location_ids = set()
    npc_ids = set()

    if campaign._legacy:
        location_ids = set(campaign._locations.keys())
        npc_ids = set(campaign._key_npcs.keys())
    elif campaign._index:
        location_ids = set(campaign._index.ids_of_type("location"))
        npc_ids = set(campaign._index.ids_of_type("npc"))

    # Validate locations
    for loc_id in location_ids:
        loc = campaign.get_location(loc_id)
        if not loc:
            continue
        for conn_id in loc.connected_to:
            if conn_id not in location_ids:
                errors.append(
                    f"Location {loc_id!r}: connected_to references unknown location {conn_id!r}"
                )
        if loc.parent and loc.parent not in location_ids:
            errors.append(
                f"Location {loc_id!r}: parent references unknown location {loc.parent!r}"
            )

    # Validate no cycles in parent hierarchy
    for loc_id in location_ids:
        visited: set[str] = set()
        current = loc_id
        while current:
            if current in visited:
                errors.append(
                    f"Location {loc_id!r}: cycle detected in parent hierarchy"
                )
                break
            visited.add(current)
            loc = campaign.get_location(current)
            current = loc.parent if loc else None

    # Validate NPCs
    for npc_id in npc_ids:
        npc = campaign.get_npc(npc_id)
        if not npc:
            continue
        if npc.location and npc.location not in location_ids:
            errors.append(
                f"NPC {npc_id!r}: location references unknown location {npc.location!r}"
            )

    # Validate plot hooks
    for hook in campaign.plot_hooks:
        if hook.trigger_location and hook.trigger_location not in location_ids:
            errors.append(
                f"PlotHook {hook.id!r}: trigger_location references unknown location {hook.trigger_location!r}"
            )
        for npc_ref in hook.connected_npcs:
            if npc_ref not in npc_ids:
                errors.append(
                    f"PlotHook {hook.id!r}: connected_npcs references unknown NPC {npc_ref!r}"
                )

    # Validate encounter monster_ids against SRD data
    for loc_id, encounters in campaign.encounter_tables.items():
        if loc_id not in location_ids:
            errors.append(
                f"Encounter table references unknown location {loc_id!r}"
            )
        for enc in encounters:
            for mid in enc.monster_ids:
                try:
                    get_monster_template(mid)
                except KeyError:
                    errors.append(
                        f"Encounter at {loc_id!r}: monster_id {mid!r} not found in SRD data"
                    )

    # Validate starting_location_id
    if campaign.starting_location_id and campaign.starting_location_id not in location_ids:
        errors.append(
            f"starting_location_id references unknown location {campaign.starting_location_id!r}"
        )

    return errors
