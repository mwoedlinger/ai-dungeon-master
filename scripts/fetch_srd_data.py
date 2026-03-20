"""Bulk-download SRD data from dnd5eapi.co and populate the local cache.

Run this once to pre-populate the cache for offline play:
    python scripts/fetch_srd_data.py

Categories downloaded: monsters, spells, equipment, classes, races, conditions,
skills, features. Each entity is cached as an individual JSON file under
src/data/srd/cache/{category}/{index}.json.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    print("httpx required: pip install 'dungeon-weaver[fetch]'")
    sys.exit(1)

API_BASE = "https://www.dnd5eapi.co/api/2014"
CACHE_DIR = Path(__file__).parent.parent / "src" / "data" / "srd" / "cache"

CATEGORIES = [
    "monsters",
    "spells",
    "equipment",
    "magic-items",
    "classes",
    "races",
    "conditions",
    "skills",
    "features",
]


def fetch(endpoint: str, client: httpx.Client) -> dict:
    resp = client.get(f"{API_BASE}/{endpoint}")
    resp.raise_for_status()
    return resp.json()


def fetch_category(category: str, client: httpx.Client) -> int:
    """Download all entries for a category. Returns count."""
    cat_dir = CACHE_DIR / category
    cat_dir.mkdir(parents=True, exist_ok=True)

    # Get index
    index_data = fetch(category, client)
    results = index_data.get("results", [])

    # Cache the index itself
    index_dir = CACHE_DIR / "_indexes"
    index_dir.mkdir(parents=True, exist_ok=True)
    entries = [{"index": r["index"], "name": r["name"]} for r in results]
    (index_dir / f"{category}.json").write_text(json.dumps(entries, indent=2))

    count = 0
    for i, entry in enumerate(results):
        index = entry["index"]
        cache_path = cat_dir / f"{index}.json"

        # Skip if already cached
        if cache_path.exists():
            count += 1
            continue

        try:
            data = fetch(f"{category}/{index}", client)
            cache_path.write_text(json.dumps(data, indent=2))
            count += 1
        except Exception as e:
            print(f"  WARN: failed to fetch {category}/{index}: {e}")

        # Progress indicator
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{len(results)}...")

        # Small delay to be nice to the API
        time.sleep(0.05)

    return count


def main() -> None:
    print(f"Fetching SRD data from {API_BASE}")
    print(f"Cache directory: {CACHE_DIR}\n")

    with httpx.Client(timeout=30.0) as client:
        for category in CATEGORIES:
            print(f"Fetching {category}...")
            count = fetch_category(category, client)
            print(f"  {count} entries cached\n")

    print("Done! SRD cache populated for offline use.")


if __name__ == "__main__":
    main()
