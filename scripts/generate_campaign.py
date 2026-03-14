"""Generate a campaign JSON from a theme using an LLM backend."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Allow running as script from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.campaign.campaign_db import CampaignData
from src.dm.backends import PROVIDERS, create_backend

SRD_MONSTER_IDS = [
    "goblin", "goblin_boss", "orc", "skeleton", "zombie", "wolf",
    "bandit", "twig_blight", "bugbear", "ghoul", "giant_spider",
    "cultist", "guard", "thug", "scout",
]

SYSTEM_PROMPT = """\
You are a D&D 5e campaign designer. Generate a complete campaign as a single JSON object.

The JSON must conform EXACTLY to this schema:

{{
  "title": "<string>",
  "setting_overview": "<string — 2-3 paragraphs>",
  "starting_location_id": "<string — id of the first location>",
  "locations": {{
    "<location_id>": {{
      "id": "<same as key>",
      "name": "<string>",
      "description": "<string — 2-4 vivid sentences>",
      "connected_to": ["<other location_ids>"]
    }}
  }},
  "factions": [
    {{
      "name": "<string>",
      "description": "<string>",
      "goals": "<string>",
      "allies": ["<strings>"],
      "enemies": ["<strings>"]
    }}
  ],
  "key_npcs": {{
    "<npc_id>": {{
      "name": "<string>",
      "location": "<location_id>",
      "personality": "<string — specific behavioral details>",
      "goals": "<string>",
      "secret": "<string>",
      "disposition": "friendly" | "neutral" | "hostile"
    }}
  }},
  "plot_hooks": [
    {{
      "id": "<string>",
      "title": "<string>",
      "description": "<string>",
      "trigger_location": "<location_id or null>",
      "connected_npcs": ["<npc_ids>"]
    }}
  ],
  "encounter_tables": {{
    "<location_id>": [
      {{
        "description": "<string — what the encounter looks like>",
        "monster_ids": ["<from allowed list, may repeat>"],
        "difficulty": "easy" | "medium" | "hard" | "deadly",
        "trigger": "random" | "scripted"
      }}
    ]
  }}
}}

RULES:
- Generate exactly {num_locations} locations. Each must connect to at least one other location.
- The location graph must be fully connected (every location reachable from starting_location_id).
- Use ONLY these SRD monster IDs in monster_ids: {monster_ids}
- Include at least 3 factions, 4 NPCs, 3 plot hooks, and encounter tables for at least 3 locations.
- Location IDs and NPC IDs must be lowercase_snake_case.
- Output ONLY the JSON object — no markdown fences, no commentary."""


def extract_json(text: str) -> dict:
    """Parse JSON from LLM output, handling markdown fences."""
    text = text.strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting from ```json ... ``` blocks
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())
    # Try finding first { to last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return json.loads(text[start : end + 1])
    raise ValueError("Could not extract JSON from LLM response")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a D&D campaign from a theme")
    parser.add_argument("theme", help="Creative theme for the campaign")
    parser.add_argument("--provider", default="anthropic", choices=PROVIDERS)
    parser.add_argument("--model", default=None, help="Override model name")
    parser.add_argument("--output", default="campaigns/generated_campaign.json")
    parser.add_argument("--locations", type=int, default=6, help="Target number of locations")
    args = parser.parse_args()

    backend = create_backend(args.provider, args.model)
    system = SYSTEM_PROMPT.format(
        num_locations=args.locations,
        monster_ids=", ".join(SRD_MONSTER_IDS),
    )
    user_msg = {"role": "user", "content": f"Generate a campaign with this theme: {args.theme}"}

    print(f"Generating campaign with {args.provider}...")
    response = backend.compress(system, [user_msg], max_tokens=4096)

    data = extract_json(response)
    campaign = CampaignData.model_validate(data)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(campaign.model_dump(), indent=2) + "\n")
    print(f"Campaign '{campaign.title}' written to {out_path}")
    print(f"  {len(campaign.locations)} locations, {len(campaign.key_npcs)} NPCs, "
          f"{len(campaign.factions)} factions, {len(campaign.plot_hooks)} plot hooks")


if __name__ == "__main__":
    main()
