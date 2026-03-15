#!/usr/bin/env python3
"""Migrate a monolithic JSON campaign to the YAML directory format.

Usage:
    python scripts/migrate_campaign.py campaigns/shattered_crown.json campaigns/shattered_crown/
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml


def _str_representer(dumper: yaml.Dumper, data: str) -> yaml.Node:
    """Use block scalar style for multiline strings."""
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


yaml.add_representer(str, _str_representer)


def migrate(src: Path, dst: Path) -> None:
    data = json.loads(src.read_text())

    dst.mkdir(parents=True, exist_ok=True)

    # campaign.yaml — metadata only
    meta = {
        "title": data["title"],
        "setting_overview": data["setting_overview"],
        "starting_location_id": data.get("starting_location_id", ""),
    }
    (dst / "campaign.yaml").write_text(yaml.dump(meta, sort_keys=False, width=120))

    # locations/
    loc_dir = dst / "locations"
    loc_dir.mkdir(exist_ok=True)
    for loc_id, loc in data.get("locations", {}).items():
        loc_data = dict(loc)
        # Determine parent from structure: if this location's only
        # connected_to entry also connects back, and one is clearly
        # "inside" the other (e.g., tavern inside village), set parent.
        # For the automated migration we add parent: null explicitly.
        loc_data.setdefault("parent", None)
        fname = f"{loc_id}.yaml"
        (loc_dir / fname).write_text(yaml.dump(loc_data, sort_keys=False, width=120))

    # npcs/
    npc_dir = dst / "npcs"
    npc_dir.mkdir(exist_ok=True)
    for npc_id, npc in data.get("key_npcs", {}).items():
        npc_data = {"id": npc_id, **npc}
        fname = f"{npc_id}.yaml"
        (npc_dir / fname).write_text(yaml.dump(npc_data, sort_keys=False, width=120))

    # factions/
    fac_dir = dst / "factions"
    fac_dir.mkdir(exist_ok=True)
    for fac in data.get("factions", []):
        fac_id = fac["name"].lower().replace(" ", "_")
        fac_data = {"id": fac_id, **fac}
        fname = f"{fac_id}.yaml"
        (fac_dir / fname).write_text(yaml.dump(fac_data, sort_keys=False, width=120))

    # plot_hooks/
    hook_dir = dst / "plot_hooks"
    hook_dir.mkdir(exist_ok=True)
    for hook in data.get("plot_hooks", []):
        fname = f"{hook['id']}.yaml"
        (hook_dir / fname).write_text(yaml.dump(dict(hook), sort_keys=False, width=120))

    # encounters/
    enc_dir = dst / "encounters"
    enc_dir.mkdir(exist_ok=True)
    for loc_id, encounters in data.get("encounter_tables", {}).items():
        enc_data = {
            "location_id": loc_id,
            "encounters": encounters,
        }
        fname = f"{loc_id}.yaml"
        (enc_dir / fname).write_text(yaml.dump(enc_data, sort_keys=False, width=120))

    print(f"Migrated {src} → {dst}")

    # Validate by loading back through the new loader
    from src.campaign.loader import load_campaign, validate_campaign

    campaign = load_campaign(dst)
    errors = validate_campaign(campaign)
    if errors:
        print("Validation warnings:")
        for err in errors:
            print(f"  • {err}")
    else:
        print("Validation passed — all cross-references OK.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate JSON campaign to YAML directory")
    parser.add_argument("source", help="Path to source JSON campaign file")
    parser.add_argument("destination", help="Path to destination campaign directory")
    args = parser.parse_args()

    src = Path(args.source)
    dst = Path(args.destination)

    if not src.exists():
        print(f"Source not found: {src}", file=sys.stderr)
        sys.exit(1)

    migrate(src, dst)


if __name__ == "__main__":
    main()
