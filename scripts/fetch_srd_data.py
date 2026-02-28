"""One-time script to fetch SRD data from Open5e API and write normalized JSON."""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    print("httpx required: pip install ai-dungeon-master[fetch]")
    sys.exit(1)

OUTPUT_DIR = Path(__file__).parent.parent / "src" / "data" / "srd"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://api.open5e.com/v1"

# Priority spells that need full mechanical data
RESOLVED_SPELLS = {
    "fire-bolt", "sacred-flame", "eldritch-blast", "minor-illusion", "mage-hand",
    "magic-missile", "shield", "cure-wounds", "healing-word", "thunderwave",
    "bless", "command", "mage-armor",
    "scorching-ray", "hold-person", "misty-step", "spiritual-weapon", "shatter",
    "fireball", "lightning-bolt", "counterspell", "revivify", "spirit-guardians",
}

MONSTER_FILTER = {
    "goblin", "goblin-boss", "orc", "skeleton", "zombie", "wolf",
    "bandit", "twig-blight", "bugbear", "ghoul", "giant-spider",
    "cultist", "guard", "thug", "scout",
}


def fetch_json(url: str) -> dict:
    resp = httpx.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_all(endpoint: str, limit: int = 500) -> list[dict]:
    url = f"{BASE_URL}/{endpoint}/?limit={limit}"
    data = fetch_json(url)
    results = data.get("results", [])
    while data.get("next"):
        data = fetch_json(data["next"])
        results.extend(data.get("results", []))
    return results


def main() -> None:
    print("Fetching spells...")
    spells_raw = fetch_all("spells", limit=500)
    print(f"  Got {len(spells_raw)} spells")

    print("Fetching monsters...")
    monsters_raw = fetch_all("monsters", limit=500)
    print(f"  Got {len(monsters_raw)} monsters")

    # Write raw data for inspection
    (OUTPUT_DIR / "_raw_spells.json").write_text(json.dumps(spells_raw, indent=2))
    (OUTPUT_DIR / "_raw_monsters.json").write_text(json.dumps(monsters_raw, indent=2))

    print("\nNote: Raw data written to src/data/srd/_raw_*.json")
    print("Manual normalization required to map to SpellData/Monster schemas.")
    print("See src/data/srd/spells.json for the target format.")


if __name__ == "__main__":
    main()
