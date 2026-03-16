"""Multi-pass campaign generator — builds rich, interconnected campaigns via LLM.

Pipeline:
  Pass 1: Concept & Lore Foundation (free-form creative seed)
  Pass 2: Location Graph (structured, validated connectivity)
  Pass 3: NPCs & Factions (varied archetypes, interconnected)
  Pass 4: Plot Hooks & Secrets Web (layered mystery)
  Pass 5: Encounters per location (SRD monsters filtered by CR)
  Final:  Validation + fix-up → CampaignData JSON
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

# Allow running as script from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.campaign.campaign_db import CampaignData
from src.dm.backends import PROVIDERS, create_backend
from src.dm.backends.base import LLMBackend


# ---------------------------------------------------------------------------
# Tonal preamble — shared across all passes
# ---------------------------------------------------------------------------

TONE_PREAMBLE = """\
You are designing a D&D 5e campaign for a player who values:
- Layered mysteries with multiple interpretations
- NPCs who feel like real people with their own lives and agendas
- Lore that rewards close attention and re-examination
- Moral ambiguity and difficult choices over clear good-vs-evil
- Atmosphere, sensory detail, and a sense of place
- The feeling of uncovering something ancient and strange
- Moments of genuine warmth, humor, and humanity alongside the darkness

Avoid:
- Chosen-one narratives or destined heroes
- Generic dragon-slaying or "clear the dungeon" plots
- Exposition dumps — truth should be discovered, not told
- Making every NPC suspicious or deceptive (some people are just... people)
- Video-game quest log structure ("collect 5 items, return for reward")
- Predictable twists — if the reader can guess it from the setup, dig deeper"""


# ---------------------------------------------------------------------------
# NPC archetype prompts — randomly selected per NPC to ensure variety
# ---------------------------------------------------------------------------

NPC_ARCHETYPES = [
    # Straightforward & warm
    """This NPC is genuinely kind and mostly transparent. They say what they mean.
Their complexity comes from their situation, not deception — they're caught between
loyalties, or burdened by a promise, or grieving something they can't name.
Give them a distinctive speech pattern or habit. Their 'secret' is personal,
not conspiratorial — something sad or tender they don't share easily.""",

    # Knowledgeable but guarded
    """This NPC knows more than they let on — not because they're scheming, but because
they've learned that knowledge can be dangerous. They answer questions honestly but
incompletely. They'll reveal more once they trust the party. Their 'tell' is that
they change the subject when certain topics come up. Give them expertise in
something specific and unusual.""",

    # Unreliable & self-serving
    """This NPC lies or misleads to serve their own interests. They're not evil — just
pragmatic and self-preserving. They'll help the party if it aligns with their goals.
They have a specific, concrete thing they want, and everything they say is shaped
by that want. Give them charm and a believable cover story. Their lie should be
specific and discoverable.""",

    # True believer
    """This NPC genuinely believes something that may or may not be true. They're not
lying — they're wrong, or they're right and nobody believes them. Their conviction
is unshakeable and it makes them either invaluable or dangerous depending on whether
they're correct. Give them passion and specificity in their belief.""",

    # Bureaucratic & obstructive
    """This NPC follows rules and procedures. They're not hostile — they're doing their
job. They represent an institution or authority. They can be helpful if the party
works within the system, infuriating if they don't. They have institutional
knowledge that's valuable but buried in procedure. Give them a routine and a
pet peeve.""",

    # Haunted survivor
    """This NPC has been through something terrible related to the central mystery.
They're not fully recovered. They have fragmentary, visceral memories that
contain genuine clues but are tangled with trauma and possibly unreliable.
They don't want to talk about it but might if they feel safe. Give them
a physical manifestation of their experience (a scar, a tic, insomnia).""",

    # Cheerful outsider
    """This NPC is new to the area or somehow outside the local power structures.
They see things clearly because they're not entangled in local politics and
history. They're observant and opinionated. They have no secrets related to
the main mystery but they've noticed things that locals have become blind to.
Give them a reason for being here and an outside perspective.""",

    # Ambitious pragmatist
    """This NPC wants power, influence, or resources — and they're competent enough
to get them. They're neither good nor evil, just driven. They'll deal with the
party as equals if respected. They have genuine useful resources and connections.
Their moral flexibility is both their strength and their danger. Give them a
specific plan they're executing.""",
]


# ---------------------------------------------------------------------------
# Pass 1: Concept & Lore Foundation
# ---------------------------------------------------------------------------

PASS1_SYSTEM = TONE_PREAMBLE + """

## Your Task — Pass 1: Concept & Lore Foundation

Given a theme from the user, create the creative foundation for a campaign.

Output a JSON object with these fields:
{{
  "title": "Campaign title — evocative, not generic",
  "setting_overview": "2-3 paragraphs. Establish the place, the mood, what's wrong. Write it like the back cover of a novel — hook the reader. Include specific sensory details.",
  "central_mystery": "What is actually going on? The deep truth. 2-3 sentences.",
  "mystery_layers": [
    "Surface: What people believe / what's obvious",
    "Intermediate: What investigation reveals — complicates the picture",
    "Deep: The actual truth — should recontextualize everything"
  ],
  "thematic_motifs": ["motif1", "motif2", "motif3"],
  "world_wound": "What's broken in this place? What tension exists before the players arrive? 2-3 sentences.",
  "tone_notes": "Specific tonal guidance: lighting, weather, sounds, emotional register. Not generic — this campaign specifically."
}}

Output ONLY valid JSON, no markdown fences or commentary."""


# ---------------------------------------------------------------------------
# Pass 2: Location Graph
# ---------------------------------------------------------------------------

PASS2_SYSTEM = TONE_PREAMBLE + """

## Your Task — Pass 2: Location Graph

Given the campaign concept, design the locations. Each location should serve a
narrative purpose — not just be a place on a map.

Output a JSON object:
{{
  "starting_location_id": "<id>",
  "locations": {{
    "<location_id>": {{
      "id": "<same as key>",
      "name": "<evocative name>",
      "description": "3-5 vivid sentences. Sensory-first: what do you see, hear, smell? Then mood, then history.",
      "connected_to": ["<other location_ids>"],
      "narrative_role": "introduction|investigation|revelation|confrontation|sanctuary|crossroads|threshold",
      "atmosphere": "1-2 sentence sensory snapshot",
      "hidden_detail": "Something not immediately obvious that rewards investigation"
    }}
  }}
}}

RULES:
- Generate exactly {num_locations} locations.
- Every location must connect to at least one other. The graph must be fully connected.
- The starting location should feel like a natural arrival point.
- Include at least one location that feels safe and at least one that feels deeply wrong.
- Location IDs must be lowercase_snake_case.
- Output ONLY valid JSON."""


# ---------------------------------------------------------------------------
# Pass 3: NPCs & Factions
# ---------------------------------------------------------------------------

PASS3_SYSTEM = TONE_PREAMBLE + """

## Your Task — Pass 3: NPCs & Factions

Design the people who inhabit this world. CRITICAL: not everyone is hiding
something sinister. Some people are straightforward, kind, or simply going
about their lives. Variety in character types is essential.

For each NPC, you'll receive a specific archetype prompt — follow it closely.

Output a JSON object:
{{
  "key_npcs": {{
    "<npc_id>": {{
      "name": "<full name>",
      "location": "<location_id where they're usually found>",
      "personality": "Specific behavioral details: how they speak, move, react. Not adjective lists.",
      "goals": "What they want — concrete and personal",
      "secret": "Something about them that isn't public knowledge. Can be personal, conspiratorial, or mundane — depends on the character.",
      "disposition": "friendly|neutral|hostile",
      "wants_from_party": "What would motivate them to interact with the players",
      "knows_about": ["<npc_ids or faction names they have information about>"]
    }}
  }},
  "factions": [
    {{
      "name": "<faction name>",
      "description": "What this group is and does",
      "goals": "What they want",
      "public_face": "How they present themselves",
      "allies": ["<faction or NPC names>"],
      "enemies": ["<faction or NPC names>"]
    }}
  ]
}}

NPC ARCHETYPES (assign one to each NPC):
{npc_archetypes}

RULES:
- Generate at least {num_npcs} NPCs across different locations.
- Generate at least 3 factions.
- Every NPC's location must be a valid location_id from the location graph.
- NPC IDs must be lowercase_snake_case.
- The knows_about field creates an information web — talking to NPC A should
  give clues about NPC B or a faction. Not every NPC needs to know about others.
- Output ONLY valid JSON."""


# ---------------------------------------------------------------------------
# Pass 4: Plot Hooks & Secrets Web
# ---------------------------------------------------------------------------

PASS4_SYSTEM = TONE_PREAMBLE + """

## Your Task — Pass 4: Plot Hooks & Secrets Web

Design the adventure hooks. These should form an interconnected web, not a
checklist. Players pulling on one thread should naturally lead to others.

Output a JSON object:
{{
  "plot_hooks": [
    {{
      "id": "<snake_case>",
      "title": "<hook title>",
      "description": "What the players learn about this — the surface version",
      "trigger_location": "<location_id or null>",
      "connected_npcs": ["<npc_ids involved>"],
      "actual_situation": "What's really going on (DM eyes only)",
      "connects_to": ["<other plot hook IDs this feeds into>"],
      "clue_locations": ["<location_ids where evidence can be found>"]
    }}
  ],
  "revelation_sequence": [
    "First, players will likely notice...",
    "This leads them to discover...",
    "Which reveals that...",
    "The deep truth is..."
  ]
}}

RULES:
- Generate at least {num_hooks} plot hooks.
- At least 2 hooks must connect to other hooks via connects_to.
- All referenced NPC IDs and location IDs must exist.
- The revelation_sequence is a suggested pacing guide, not a railroad.
- Output ONLY valid JSON."""


# ---------------------------------------------------------------------------
# Pass 5: Encounters (per-location)
# ---------------------------------------------------------------------------

PASS5_SYSTEM = TONE_PREAMBLE + """

## Your Task — Pass 5: Encounters for "{location_name}"

Design encounters for this specific location. Encounters should feel like they
belong here — connected to the lore, not random monster placement.

Location context:
{location_context}

Campaign context:
{campaign_context}

Available SRD monsters (CR {cr_min}-{cr_max}):
{monster_list}

Output a JSON object:
{{
  "encounters": [
    {{
      "description": "What the encounter looks like — set the scene",
      "monster_ids": ["<SRD monster IDs from the list above, may repeat>"],
      "difficulty": "easy|medium|hard|deadly",
      "trigger": "random|scripted",
      "narrative_context": "Why these creatures are here — connect to the campaign's story"
    }}
  ]
}}

RULES:
- Generate 2-4 encounters for this location.
- Use ONLY monster IDs from the provided list.
- At least one encounter should be "scripted" (triggered by specific story events).
- Monster choices should make thematic sense for this location and campaign.
- Vary difficulty levels.
- Output ONLY valid JSON."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_json(text: str) -> dict:
    """Parse JSON from LLM output, handling markdown fences."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return json.loads(text[start : end + 1])
    raise ValueError("Could not extract JSON from LLM response")


def llm_call(
    backend: LLMBackend,
    system: str,
    user_content: str,
    max_tokens: int = 4096,
    max_retries: int = 3,
) -> str:
    """Make an LLM call with retry logic for transient connection errors."""
    import time

    for attempt in range(max_retries):
        try:
            return backend.generate(
                system=system,
                messages=[{"role": "user", "content": user_content}],
                max_tokens=max_tokens,
            )
        except Exception as e:
            err_str = str(e).lower()
            is_transient = any(k in err_str for k in (
                "connection", "timeout", "timed out", "remote", "reset",
                "chunked read", "incomplete", "eof", "broken pipe",
            ))
            if is_transient and attempt < max_retries - 1:
                wait = 2 ** attempt  # 1s, 2s, 4s
                print(f"  Connection error, retrying in {wait}s... ({attempt + 1}/{max_retries})")
                time.sleep(wait)
            else:
                raise


def get_srd_monsters_by_cr(cr_min: float, cr_max: float) -> list[dict]:
    """Load all SRD monsters and filter by CR range.

    Returns list of {index, name, cr, type} dicts.
    """
    from src.data.srd_client import get_index, _get_raw

    index = get_index("monsters")
    monsters: list[dict] = []
    for entry in index:
        mid = entry["index"]
        try:
            raw = _get_raw("monsters", mid)
            if raw is None:
                continue
            cr = raw.get("challenge_rating", 0)
            if cr_min <= cr <= cr_max:
                monsters.append({
                    "index": mid,
                    "name": raw["name"],
                    "cr": cr,
                    "type": raw.get("type", "unknown"),
                })
        except Exception:
            continue
    monsters.sort(key=lambda m: (m["cr"], m["name"]))
    return monsters


def validate_location_graph(locations: dict) -> list[str]:
    """Check that the location graph is fully connected."""
    errors: list[str] = []
    if not locations:
        return ["No locations defined"]

    # Check all connected_to references exist
    for lid, loc in locations.items():
        for cid in loc.get("connected_to", []):
            if cid not in locations:
                errors.append(f"Location '{lid}' connects to unknown '{cid}'")

    # BFS connectivity check
    start = next(iter(locations))
    visited: set[str] = set()
    queue = [start]
    while queue:
        node = queue.pop(0)
        if node in visited:
            continue
        visited.add(node)
        for cid in locations.get(node, {}).get("connected_to", []):
            if cid in locations:
                queue.append(cid)
    unreachable = set(locations) - visited
    if unreachable:
        errors.append(f"Unreachable locations: {unreachable}")

    return errors


def validate_cross_references(data: dict) -> list[str]:
    """Validate all cross-references in the assembled campaign."""
    errors: list[str] = []
    location_ids = set(data.get("locations", {}).keys())
    npc_ids = set(data.get("key_npcs", {}).keys())

    # NPC locations
    for nid, npc in data.get("key_npcs", {}).items():
        if npc.get("location") not in location_ids:
            errors.append(f"NPC '{nid}' references unknown location '{npc.get('location')}'")

    # Plot hook references
    hook_ids = {h["id"] for h in data.get("plot_hooks", [])}
    for hook in data.get("plot_hooks", []):
        if hook.get("trigger_location") and hook["trigger_location"] not in location_ids:
            errors.append(f"Hook '{hook['id']}' references unknown location '{hook['trigger_location']}'")
        for nid in hook.get("connected_npcs", []):
            if nid not in npc_ids:
                errors.append(f"Hook '{hook['id']}' references unknown NPC '{nid}'")
        for cid in hook.get("clue_locations", []):
            if cid not in location_ids:
                errors.append(f"Hook '{hook['id']}' references unknown clue location '{cid}'")

    # Encounter monster IDs
    from src.data.srd_client import get_index
    srd_monster_ids = {e["index"] for e in get_index("monsters")}
    for loc_id, encounters in data.get("encounter_tables", {}).items():
        for enc in encounters:
            for mid in enc.get("monster_ids", []):
                if mid not in srd_monster_ids:
                    errors.append(f"Encounter at '{loc_id}' uses unknown monster '{mid}'")

    return errors


# ---------------------------------------------------------------------------
# Multi-pass pipeline
# ---------------------------------------------------------------------------

class CampaignGenerator:
    """Multi-pass campaign generator."""

    def __init__(
        self,
        backend: LLMBackend,
        num_locations: int = 8,
        num_npcs: int = 6,
        num_hooks: int = 4,
        cr_range: tuple[float, float] = (0, 5),
        verbose: bool = False,
    ):
        self.backend = backend
        self.num_locations = num_locations
        self.num_npcs = num_npcs
        self.num_hooks = num_hooks
        self.cr_min, self.cr_max = cr_range
        self.verbose = verbose

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"  {msg}")

    def _call(self, system: str, user_content: str, max_tokens: int = 4096) -> dict:
        """LLM call → parse JSON, with retry on parse failure."""
        for attempt in range(3):
            raw = llm_call(self.backend, system, user_content, max_tokens)
            try:
                return extract_json(raw)
            except (json.JSONDecodeError, ValueError):
                if attempt < 2:
                    self._log(f"JSON parse failed (attempt {attempt + 1}/3), retrying...")
                else:
                    raise

    def generate(self, theme: str) -> dict:
        """Run the full multi-pass pipeline. Returns campaign dict."""

        # Pass 1: Concept
        print("Pass 1/5: Concept & Lore Foundation...")
        concept = self._pass1_concept(theme)
        self._log(f"Title: {concept.get('title', '?')}")

        # Pass 2: Locations
        print("Pass 2/5: Location Graph...")
        locations_data = self._pass2_locations(concept)
        self._log(f"Generated {len(locations_data.get('locations', {}))} locations")

        # Pass 3: NPCs & Factions
        print("Pass 3/5: NPCs & Factions...")
        people_data = self._pass3_npcs(concept, locations_data)
        self._log(f"Generated {len(people_data.get('key_npcs', {}))} NPCs, "
                  f"{len(people_data.get('factions', []))} factions")

        # Pass 4: Plot Hooks
        print("Pass 4/5: Plot Hooks & Secrets Web...")
        hooks_data = self._pass4_hooks(concept, locations_data, people_data)
        self._log(f"Generated {len(hooks_data.get('plot_hooks', []))} plot hooks")

        # Pass 5: Encounters (per-location)
        print("Pass 5/5: Encounters...")
        encounter_tables = self._pass5_encounters(concept, locations_data)
        self._log(f"Generated encounters for {len(encounter_tables)} locations")

        # Assemble
        campaign = self._assemble(concept, locations_data, people_data, hooks_data, encounter_tables)

        # Validate & fix
        print("Validating...")
        campaign = self._validate_and_fix(campaign)

        return campaign

    # ------------------------------------------------------------------
    # Individual passes
    # ------------------------------------------------------------------

    def _pass1_concept(self, theme: str) -> dict:
        return self._call(
            PASS1_SYSTEM,
            f"Create a campaign concept for this theme:\n\n{theme}",
            max_tokens=2000,
        )

    def _pass2_locations(self, concept: dict) -> dict:
        system = PASS2_SYSTEM.format(num_locations=self.num_locations)
        context = json.dumps(concept, indent=2)
        data = self._call(
            system,
            f"Campaign concept:\n{context}\n\nDesign the location graph.",
            max_tokens=4000,
        )
        # Validate connectivity
        errors = validate_location_graph(data.get("locations", {}))
        if errors:
            self._log(f"Location graph issues: {errors}")
            # Try to fix connectivity by adding edges
            locations = data.get("locations", {})
            all_ids = list(locations.keys())
            for lid in all_ids:
                if not locations[lid].get("connected_to"):
                    # Connect isolates to the starting location
                    start = data.get("starting_location_id", all_ids[0])
                    locations[lid]["connected_to"] = [start]
                    if lid not in locations[start].get("connected_to", []):
                        locations[start].setdefault("connected_to", []).append(lid)
        return data

    def _pass3_npcs(self, concept: dict, locations_data: dict) -> dict:
        location_ids = list(locations_data.get("locations", {}).keys())
        batch_size = 8  # max NPCs per LLM call to stay within output limits

        all_npcs: dict = {}
        all_factions: list = []
        remaining = self.num_npcs

        batch_num = 0
        while remaining > 0:
            batch_count = min(remaining, batch_size)
            batch_num += 1

            # Select random archetypes for this batch
            pool = NPC_ARCHETYPES * ((batch_count // len(NPC_ARCHETYPES)) + 1)
            archetypes = random.sample(pool, batch_count)
            archetype_text = "\n\n".join(
                f"NPC #{i+1}:\n{arch}" for i, arch in enumerate(archetypes)
            )

            system = PASS3_SYSTEM.format(
                npc_archetypes=archetype_text,
                num_npcs=batch_count,
            )

            # Tell later batches about existing NPCs to avoid duplicates
            existing_info = ""
            if all_npcs:
                existing_names = [n.get("name", "?") for n in all_npcs.values()]
                existing_info = (
                    f"\n\nAlready created NPCs (DO NOT duplicate): {existing_names}\n"
                    f"Already created factions: {[f.get('name', '?') for f in all_factions]}"
                )
                # Only generate factions on first batch
                system += "\n\nFactions have already been created. Output an empty factions list."

            context = (
                f"Campaign concept:\n{json.dumps(concept, indent=2)}\n\n"
                f"Available location IDs: {location_ids}"
                f"{existing_info}"
            )

            if self.num_npcs > batch_size:
                self._log(f"NPC batch {batch_num} ({batch_count} NPCs)...")

            data = self._call(system, context, max_tokens=4000)
            all_npcs.update(data.get("key_npcs", {}))
            if not all_factions:
                all_factions = data.get("factions", [])

            remaining -= batch_count

        return {"key_npcs": all_npcs, "factions": all_factions}

    def _pass4_hooks(self, concept: dict, locations_data: dict, people_data: dict) -> dict:
        system = PASS4_SYSTEM.format(num_hooks=self.num_hooks)
        location_ids = list(locations_data.get("locations", {}).keys())
        npc_ids = list(people_data.get("key_npcs", {}).keys())
        context = (
            f"Campaign concept:\n{json.dumps(concept, indent=2)}\n\n"
            f"Location IDs: {location_ids}\n\n"
            f"NPC IDs and summaries:\n"
        )
        for nid, npc in people_data.get("key_npcs", {}).items():
            context += f"  {nid}: {npc.get('name', '?')} at {npc.get('location', '?')} — {npc.get('goals', '')[:80]}\n"
        return self._call(system, context, max_tokens=3000)

    def _pass5_encounters(self, concept: dict, locations_data: dict) -> dict[str, list]:
        """Generate encounters per-location. Each location gets its own LLM call."""
        monsters = get_srd_monsters_by_cr(self.cr_min, self.cr_max)
        if not monsters:
            print(f"  Warning: no SRD monsters found in CR {self.cr_min}-{self.cr_max}")
            return {}

        monster_list = "\n".join(
            f"  {m['index']} (CR {m['cr']}, {m['type']})" for m in monsters
        )

        campaign_context = (
            f"Title: {concept.get('title', '')}\n"
            f"Mystery: {concept.get('central_mystery', '')}\n"
            f"Tone: {concept.get('tone_notes', '')}"
        )

        encounter_tables: dict[str, list] = {}
        locations = locations_data.get("locations", {})

        for loc_id, loc in locations.items():
            location_context = (
                f"Name: {loc.get('name', loc_id)}\n"
                f"Description: {loc.get('description', '')}\n"
                f"Narrative role: {loc.get('narrative_role', 'unknown')}\n"
                f"Atmosphere: {loc.get('atmosphere', '')}\n"
                f"Hidden detail: {loc.get('hidden_detail', '')}"
            )
            system = PASS5_SYSTEM.format(
                location_name=loc.get("name", loc_id),
                location_context=location_context,
                campaign_context=campaign_context,
                monster_list=monster_list,
                cr_min=self.cr_min,
                cr_max=self.cr_max,
            )
            self._log(f"Encounters for {loc.get('name', loc_id)}...")
            try:
                data = self._call(
                    system,
                    "Design encounters for this location.",
                    max_tokens=2000,
                )
                encounters = data.get("encounters", [])
                if encounters:
                    encounter_tables[loc_id] = encounters
            except Exception as e:
                self._log(f"  Failed for {loc_id}: {e}")

        return encounter_tables

    # ------------------------------------------------------------------
    # Assembly & validation
    # ------------------------------------------------------------------

    def _assemble(
        self,
        concept: dict,
        locations_data: dict,
        people_data: dict,
        hooks_data: dict,
        encounter_tables: dict[str, list],
    ) -> dict:
        """Assemble all passes into a single campaign dict."""
        # Clean locations — strip extra fields not in CampaignData schema
        clean_locations = {}
        for lid, loc in locations_data.get("locations", {}).items():
            clean_locations[lid] = {
                "id": lid,
                "name": loc.get("name", lid),
                "description": loc.get("description", ""),
                "connected_to": loc.get("connected_to", []),
            }

        # Clean NPCs — strip extra fields
        clean_npcs = {}
        for nid, npc in people_data.get("key_npcs", {}).items():
            clean_npcs[nid] = {
                "name": npc.get("name", nid),
                "location": npc.get("location", ""),
                "personality": npc.get("personality", ""),
                "goals": npc.get("goals", ""),
                "secret": npc.get("secret", ""),
                "disposition": npc.get("disposition", "neutral"),
            }

        # Clean factions
        clean_factions = []
        for faction in people_data.get("factions", []):
            clean_factions.append({
                "name": faction.get("name", ""),
                "description": faction.get("description", ""),
                "goals": faction.get("goals", ""),
                "allies": faction.get("allies", []),
                "enemies": faction.get("enemies", []),
            })

        # Clean plot hooks
        clean_hooks = []
        for hook in hooks_data.get("plot_hooks", []):
            clean_hooks.append({
                "id": hook.get("id", ""),
                "title": hook.get("title", ""),
                "description": hook.get("description", ""),
                "trigger_location": hook.get("trigger_location"),
                "connected_npcs": hook.get("connected_npcs", []),
            })

        # Clean encounter tables
        clean_encounters: dict[str, list] = {}
        for loc_id, encounters in encounter_tables.items():
            clean_encounters[loc_id] = []
            for enc in encounters:
                clean_encounters[loc_id].append({
                    "description": enc.get("description", ""),
                    "monster_ids": enc.get("monster_ids", []),
                    "difficulty": enc.get("difficulty", "medium"),
                    "trigger": enc.get("trigger", "random"),
                })

        return {
            "title": concept.get("title", "Untitled Campaign"),
            "setting_overview": concept.get("setting_overview", ""),
            "starting_location_id": locations_data.get("starting_location_id", ""),
            "locations": clean_locations,
            "key_npcs": clean_npcs,
            "factions": clean_factions,
            "plot_hooks": clean_hooks,
            "encounter_tables": clean_encounters,
        }

    def _validate_and_fix(self, campaign: dict, max_retries: int = 2) -> dict:
        """Validate and attempt to fix cross-reference errors."""
        for attempt in range(max_retries + 1):
            # Structural validation
            errors = validate_cross_references(campaign)
            graph_errors = validate_location_graph(campaign.get("locations", {}))
            all_errors = errors + graph_errors

            if not all_errors:
                self._log("Validation passed")
                break

            if attempt < max_retries:
                self._log(f"Validation errors ({len(all_errors)}), attempting fix...")
                campaign = self._auto_fix(campaign, all_errors)
            else:
                print(f"  Warning: {len(all_errors)} validation errors remaining:")
                for err in all_errors[:5]:
                    print(f"    - {err}")

        # Final: validate against Pydantic model
        try:
            CampaignData.from_dict(campaign)
            self._log("Pydantic validation passed")
        except Exception as e:
            print(f"  Warning: Pydantic validation issue: {e}")

        return campaign

    def _auto_fix(self, campaign: dict, errors: list[str]) -> dict:
        """Attempt programmatic fixes for common issues."""
        location_ids = set(campaign.get("locations", {}).keys())

        # Fix NPC locations
        for nid, npc in campaign.get("key_npcs", {}).items():
            if npc.get("location") not in location_ids:
                # Assign to starting location
                npc["location"] = campaign.get("starting_location_id", next(iter(location_ids), ""))

        # Fix plot hook locations
        for hook in campaign.get("plot_hooks", []):
            if hook.get("trigger_location") and hook["trigger_location"] not in location_ids:
                hook["trigger_location"] = None
            hook["clue_locations"] = [c for c in hook.get("clue_locations", []) if c in location_ids]

        # Fix encounter monster IDs by removing invalid ones
        from src.data.srd_client import get_index
        srd_monster_ids = {e["index"] for e in get_index("monsters")}
        for loc_id, encounters in campaign.get("encounter_tables", {}).items():
            for enc in encounters:
                enc["monster_ids"] = [m for m in enc.get("monster_ids", []) if m in srd_monster_ids]
            # Remove encounters with no valid monsters
            campaign["encounter_tables"][loc_id] = [
                e for e in encounters if e.get("monster_ids")
            ]

        return campaign


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_cr_range(s: str) -> tuple[float, float]:
    """Parse '1-5' or '0.25-3' into (min, max)."""
    parts = s.split("-")
    if len(parts) == 2:
        return float(parts[0]), float(parts[1])
    raise argparse.ArgumentTypeError(f"Invalid CR range: {s!r}. Use format: 1-5")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a D&D 5e campaign from a theme (multi-pass)",
    )
    parser.add_argument("theme", help="Creative theme or premise for the campaign")
    parser.add_argument("--provider", default="anthropic", choices=PROVIDERS)
    parser.add_argument("--model", default=None, help="Override model name")
    parser.add_argument("--output", default=None, help="Output path (default: campaigns/<title>.json)")
    parser.add_argument("--locations", type=int, default=8, help="Number of locations (default: 8)")
    parser.add_argument("--npcs", type=int, default=6, help="Number of NPCs (default: 6)")
    parser.add_argument("--hooks", type=int, default=4, help="Number of plot hooks (default: 4)")
    parser.add_argument("--cr-range", type=parse_cr_range, default=(0, 5),
                        help="Monster CR range (default: 0-5)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed progress")
    args = parser.parse_args()

    backend = create_backend(args.provider, args.model)

    generator = CampaignGenerator(
        backend=backend,
        num_locations=args.locations,
        num_npcs=args.npcs,
        num_hooks=args.hooks,
        cr_range=args.cr_range,
        verbose=args.verbose,
    )

    campaign_data = generator.generate(args.theme)

    # Determine output path
    if args.output:
        out_path = Path(args.output)
    else:
        # Derive from title
        title = campaign_data.get("title", "generated_campaign")
        slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:50]
        out_path = Path(f"campaigns/{slug}.json")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(campaign_data, indent=2) + "\n")

    # Summary
    print(f"\nCampaign '{campaign_data.get('title', '?')}' written to {out_path}")
    print(f"  {len(campaign_data.get('locations', {}))} locations")
    print(f"  {len(campaign_data.get('key_npcs', {}))} NPCs")
    print(f"  {len(campaign_data.get('factions', []))} factions")
    print(f"  {len(campaign_data.get('plot_hooks', []))} plot hooks")
    enc_count = sum(len(v) for v in campaign_data.get("encounter_tables", {}).values())
    print(f"  {enc_count} encounters across {len(campaign_data.get('encounter_tables', {}))} locations")


if __name__ == "__main__":
    main()
