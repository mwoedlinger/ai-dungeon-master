"""Campaign data models, index, and lazy-loading database."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from src.models.world import Location, QuestReward


# ---------------------------------------------------------------------------
# Entity models
# ---------------------------------------------------------------------------

class Faction(BaseModel):
    id: str = ""
    name: str
    description: str
    goals: str
    allies: list[str] = []
    enemies: list[str] = []


class NPCProfile(BaseModel):
    id: str = ""
    name: str
    location: str
    personality: str
    goals: str
    secret: str = ""
    disposition: Literal["friendly", "neutral", "hostile"] = "neutral"


class PlotHook(BaseModel):
    id: str
    title: str
    description: str
    trigger_location: str | None = None
    connected_npcs: list[str] = []
    rewards: QuestReward | None = None


class EncounterTemplate(BaseModel):
    description: str
    monster_ids: list[str]
    difficulty: Literal["easy", "medium", "hard", "deadly"]
    trigger: str = "random"


class EncounterTable(BaseModel):
    """Wrapper for a location's encounter list (used in directory-based campaigns)."""
    location_id: str
    encounters: list[EncounterTemplate]


# Map from entity type string to model class
ENTITY_MODELS: dict[str, type[BaseModel]] = {
    "location": Location,
    "npc": NPCProfile,
    "faction": Faction,
    "plot_hook": PlotHook,
    "encounter": EncounterTable,
}


# ---------------------------------------------------------------------------
# Campaign index (lightweight, built at startup)
# ---------------------------------------------------------------------------

@dataclass
class EntityRef:
    """Pointer to an entity on disk — no content loaded."""
    entity_type: str
    entity_id: str
    file_path: Path
    name: str


@dataclass
class CampaignIndex:
    """Lightweight index built by scanning a campaign directory."""
    title: str
    setting_overview: str
    starting_location_id: str
    refs: dict[tuple[str, str], EntityRef] = field(default_factory=dict)

    def ids_of_type(self, entity_type: str) -> list[str]:
        return [eid for (etype, eid) in self.refs if etype == entity_type]


# ---------------------------------------------------------------------------
# LRU cache
# ---------------------------------------------------------------------------

class _LRUCache:
    """Simple ordered-dict LRU cache with a max size."""

    def __init__(self, max_size: int = 50):
        self._max_size = max_size
        self._data: OrderedDict[tuple[str, str], BaseModel] = OrderedDict()

    def get(self, key: tuple[str, str]) -> BaseModel | None:
        if key in self._data:
            self._data.move_to_end(key)
            return self._data[key]
        return None

    def put(self, key: tuple[str, str], value: BaseModel) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        else:
            if len(self._data) >= self._max_size:
                self._data.popitem(last=False)
        self._data[key] = value

    def __contains__(self, key: tuple[str, str]) -> bool:
        return key in self._data


# ---------------------------------------------------------------------------
# CampaignData — unified interface for both legacy JSON and directory campaigns
# ---------------------------------------------------------------------------

class CampaignData:
    """Campaign database with lazy loading and hierarchical location support.

    Works in two modes:
    - Legacy: constructed from a flat dict (single JSON file). All data in memory.
    - Directory: constructed from a CampaignIndex. Entities loaded on demand.
    """

    def __init__(
        self,
        *,
        # Legacy fields (populated when loading from JSON)
        title: str = "",
        setting_overview: str = "",
        starting_location_id: str = "",
        locations: dict[str, Location] | None = None,
        factions: list[Faction] | None = None,
        key_npcs: dict[str, NPCProfile] | None = None,
        plot_hooks: list[PlotHook] | None = None,
        encounter_tables: dict[str, list[EncounterTemplate]] | None = None,
        # Directory mode
        index: CampaignIndex | None = None,
    ):
        if index is not None:
            # Directory-based campaign
            self.title = index.title
            self.setting_overview = index.setting_overview
            self.starting_location_id = index.starting_location_id
            self._index = index
            self._cache = _LRUCache(max_size=50)
            self._legacy = False
        else:
            # Legacy JSON campaign — store everything eagerly
            self.title = title
            self.setting_overview = setting_overview
            self.starting_location_id = starting_location_id
            self._index = None
            self._cache = _LRUCache(max_size=50)
            self._legacy = True
            # Store legacy data directly
            self._locations = locations or {}
            self._factions = factions or []
            self._key_npcs = key_npcs or {}
            self._plot_hooks = plot_hooks or []
            self._encounter_tables = encounter_tables or {}

    # ------------------------------------------------------------------
    # Legacy-compatible property: .locations
    # ------------------------------------------------------------------

    @property
    def locations(self) -> dict[str, Location]:
        """All locations. For legacy mode returns stored dict.
        For directory mode, loads all locations (used by main.py for world init)."""
        if self._legacy:
            return self._locations
        result = {}
        for eid in self._index.ids_of_type("location"):
            result[eid] = self.get_location(eid)
        return result

    @property
    def plot_hooks(self) -> list[PlotHook]:
        if self._legacy:
            return self._plot_hooks
        hooks = []
        for eid in self._index.ids_of_type("plot_hook"):
            hooks.append(self.get_entity("plot_hook", eid))
        return hooks

    @property
    def factions(self) -> list[Faction]:
        if self._legacy:
            return self._factions
        return [self.get_entity("faction", eid) for eid in self._index.ids_of_type("faction")]

    @property
    def key_npcs(self) -> dict[str, NPCProfile]:
        if self._legacy:
            return self._key_npcs
        result = {}
        for eid in self._index.ids_of_type("npc"):
            result[eid] = self.get_npc(eid)
        return result

    @property
    def encounter_tables(self) -> dict[str, list[EncounterTemplate]]:
        if self._legacy:
            return self._encounter_tables
        result = {}
        for eid in self._index.ids_of_type("encounter"):
            table: EncounterTable = self.get_entity("encounter", eid)
            result[table.location_id] = table.encounters
        return result

    # ------------------------------------------------------------------
    # Entity access (lazy for directory mode, direct for legacy)
    # ------------------------------------------------------------------

    def get_location(self, location_id: str) -> Location | None:
        if self._legacy:
            return self._locations.get(location_id)
        return self._load("location", location_id)

    def get_npc(self, npc_id: str) -> NPCProfile | None:
        if self._legacy:
            return self._key_npcs.get(npc_id)
        return self._load("npc", npc_id)

    def get_entity(self, entity_type: str, entity_id: str) -> BaseModel | None:
        if self._legacy:
            match entity_type:
                case "location":
                    return self._locations.get(entity_id)
                case "npc":
                    return self._key_npcs.get(entity_id)
                case "faction":
                    for f in self._factions:
                        if f.id == entity_id or f.name.lower().replace(" ", "_") == entity_id:
                            return f
                    return None
                case "plot_hook":
                    for h in self._plot_hooks:
                        if h.id == entity_id:
                            return h
                    return None
                case "encounter":
                    if entity_id in self._encounter_tables:
                        return EncounterTable(
                            location_id=entity_id,
                            encounters=self._encounter_tables[entity_id],
                        )
                    return None
                case _:
                    return None
        return self._load(entity_type, entity_id)

    def _load(self, entity_type: str, entity_id: str) -> BaseModel | None:
        """Load an entity from disk (with LRU caching)."""
        key = (entity_type, entity_id)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        if self._index is None or key not in self._index.refs:
            return None

        ref = self._index.refs[key]
        raw = yaml.safe_load(ref.file_path.read_text())
        model_cls = ENTITY_MODELS[entity_type]
        obj = model_cls.model_validate(raw)
        self._cache.put(key, obj)
        return obj

    # ------------------------------------------------------------------
    # Hierarchical location helpers
    # ------------------------------------------------------------------

    def get_children(self, location_id: str) -> list[Location]:
        """Return all direct child locations of the given location."""
        children = []
        if self._legacy:
            for loc in self._locations.values():
                if loc.parent == location_id:
                    children.append(loc)
        else:
            for eid in self._index.ids_of_type("location"):
                loc = self.get_location(eid)
                if loc and loc.parent == location_id:
                    children.append(loc)
        return children

    def get_all_sub_location_ids(self, location_id: str) -> list[str]:
        """Return all descendant location IDs (recursive)."""
        result = []
        for child in self.get_children(location_id):
            result.append(child.id)
            result.extend(self.get_all_sub_location_ids(child.id))
        return result

    def get_npcs_at_location(self, location_id: str, include_children: bool = True) -> list[NPCProfile]:
        """Return NPCs at a location. If include_children, also includes sub-locations."""
        loc_ids = {location_id}
        if include_children:
            loc_ids.update(self.get_all_sub_location_ids(location_id))

        npcs = []
        if self._legacy:
            for npc in self._key_npcs.values():
                if npc.location in loc_ids:
                    npcs.append(npc)
        else:
            for eid in self._index.ids_of_type("npc"):
                npc = self.get_npc(eid)
                if npc and npc.location in loc_ids:
                    npcs.append(npc)
        return npcs

    def get_connected_locations(self, location_id: str) -> list[Location]:
        """Return connected locations = explicit connected_to + direct children."""
        loc = self.get_location(location_id)
        if not loc:
            return []
        result = []
        for cid in loc.connected_to:
            connected = self.get_location(cid)
            if connected:
                result.append(connected)
        for child in self.get_children(location_id):
            if child.id not in loc.connected_to:
                result.append(child)
        return result

    # ------------------------------------------------------------------
    # Context & query (public API — unchanged interface)
    # ------------------------------------------------------------------

    def get_location_context(self, location_id: str, token_budget: int = 1500) -> str:
        """Build context for system prompt, staying within token budget."""
        loc = self.get_location(location_id)
        if not loc:
            return f"Unknown location: {location_id}"

        lines = [
            f"## Current Location: {loc.name}",
            loc.description,
        ]
        used = self._estimate_str_tokens("\n".join(lines))

        # NPCs present (including sub-locations)
        npcs_here = self.get_npcs_at_location(location_id, include_children=True)
        if npcs_here:
            npc_summaries = []
            for npc in npcs_here:
                summary = f"{npc.name} ({npc.disposition}): {npc.personality[:80]}"
                cost = self._estimate_str_tokens(summary)
                if used + cost > token_budget:
                    break
                npc_summaries.append(summary)
                used += cost
            if npc_summaries:
                lines.append("**NPCs present**: " + "; ".join(npc_summaries))

        # Nearby locations (name only)
        nearby = self.get_connected_locations(location_id)
        if nearby:
            nearby_str = ", ".join(n.name for n in nearby)
            cost = self._estimate_str_tokens(nearby_str)
            if used + cost <= token_budget:
                lines.append(f"**Nearby**: {nearby_str}")
                used += cost

        # Active plot hooks (title only)
        hooks = self.get_relevant_plot_hooks(location_id)
        if hooks:
            hooks_str = "; ".join(h.title for h in hooks)
            cost = self._estimate_str_tokens(hooks_str)
            if used + cost <= token_budget:
                lines.append("**Plot hooks**: " + hooks_str)

        return "\n".join(lines)

    def get_relevant_plot_hooks(self, location_id: str) -> list[PlotHook]:
        """Plot hooks triggered at this location or its sub-locations."""
        loc_ids = {location_id}
        loc_ids.update(self.get_all_sub_location_ids(location_id))

        if self._legacy:
            return [h for h in self._plot_hooks if h.trigger_location in loc_ids]

        hooks = []
        for eid in self._index.ids_of_type("plot_hook"):
            hook = self.get_entity("plot_hook", eid)
            if hook and hook.trigger_location in loc_ids:
                hooks.append(hook)
        return hooks

    def _fuzzy_match_id(self, query_id: str, valid_ids: list[str]) -> str | None:
        """Try to match a guessed ID against valid IDs using fuzzy heuristics.

        Handles common LLM mistakes: wrong word order (captain_thorvald vs
        thorvald_militia_captain), added/dropped prefixes (the_missing_woodcutters
        vs missing_woodcutters), case differences.
        """
        q = query_id.lower().strip()
        # Exact match (case-insensitive)
        for vid in valid_ids:
            if vid.lower() == q:
                return vid
        # Substring containment: if the query is contained in a valid ID or vice versa
        for vid in valid_ids:
            vl = vid.lower()
            if q in vl or vl in q:
                return vid
        # Word overlap: match if all significant words in the query appear in a valid ID
        q_words = set(q.replace("-", "_").split("_"))
        q_words -= {"the", "a", "an", "of", "in", "at", "to"}  # strip articles
        for vid in valid_ids:
            v_words = set(vid.lower().replace("-", "_").split("_"))
            if q_words and q_words <= v_words:
                return vid
            # Also check reverse: all valid ID words in query
            v_words -= {"the", "a", "an", "of", "in", "at", "to"}
            if v_words and v_words <= q_words:
                return vid
        return None

    def _not_found_error(self, entity_type: str, id: str, valid_ids: list[str]) -> dict:
        """Build a helpful 'not found' error that lists valid IDs."""
        ids_str = ", ".join(sorted(valid_ids)) if valid_ids else "(none)"
        return {
            "success": False,
            "error": f"{entity_type} {id!r} not found. Valid IDs: {ids_str}",
        }

    def query(self, query_type: str, id: str) -> dict:
        """Handle query_world_lore tool calls from the LLM."""
        match query_type:
            case "location":
                # Fuzzy match location ID
                valid_ids = list(self.locations.keys())
                loc = self.get_location(id)
                if not loc:
                    matched = self._fuzzy_match_id(id, valid_ids)
                    if matched:
                        loc = self.get_location(matched)
                        id = matched
                if not loc:
                    return self._not_found_error("Location", id, valid_ids)
                connected = self.get_connected_locations(id)
                nearby_names = {c.id: c.name for c in connected}
                npcs_here = self.get_npcs_at_location(id)
                npcs_dict = {npc.id or npc.name: npc.model_dump() for npc in npcs_here}
                encounters = self.encounter_tables.get(id, [])
                return {
                    "success": True,
                    "location": loc.model_dump(),
                    "connected_to_names": nearby_names,
                    "npcs_present": npcs_dict,
                    "possible_encounters": [e.model_dump() for e in encounters],
                }
            case "npc":
                valid_ids = list(self.key_npcs.keys())
                npc = self.get_npc(id)
                if not npc:
                    matched = self._fuzzy_match_id(id, valid_ids)
                    if matched:
                        npc = self.get_npc(matched)
                if not npc:
                    return self._not_found_error("NPC", id, valid_ids)
                return {"success": True, "npc": npc.model_dump()}
            case "faction":
                valid_ids = [f.id or f.name for f in self.factions]
                entity = self.get_entity("faction", id)
                if not entity:
                    # Try name match
                    for f in self.factions:
                        if f.name.lower().replace(" ", "_") == id.lower() or f.name == id:
                            return {"success": True, "faction": f.model_dump()}
                    matched = self._fuzzy_match_id(id, valid_ids)
                    if matched:
                        entity = self.get_entity("faction", matched)
                if not entity:
                    return self._not_found_error("Faction", id, valid_ids)
                return {"success": True, "faction": entity.model_dump()}
            case "plot_hook":
                valid_ids = [h.id for h in self.plot_hooks]
                entity = self.get_entity("plot_hook", id)
                if not entity:
                    matched = self._fuzzy_match_id(id, valid_ids)
                    if matched:
                        entity = self.get_entity("plot_hook", matched)
                if not entity:
                    return self._not_found_error("Plot hook", id, valid_ids)
                return {"success": True, "plot_hook": entity.model_dump()}
            case _:
                return {"success": False, "error": f"Unknown query_type: {query_type!r}"}

    @staticmethod
    def _estimate_str_tokens(s: str) -> int:
        """Rough token estimate: ~4 chars per token."""
        return len(s) // 4

    # ------------------------------------------------------------------
    # Legacy factory (from flat dict, e.g. JSON load)
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict) -> CampaignData:
        """Create from a flat dictionary (legacy JSON format)."""
        locations = {}
        for lid, loc_data in data.get("locations", {}).items():
            locations[lid] = Location.model_validate(loc_data)

        factions = [Faction.model_validate(f) for f in data.get("factions", [])]
        # Assign IDs to factions if missing
        for f in factions:
            if not f.id:
                f.id = f.name.lower().replace(" ", "_")

        key_npcs = {}
        for nid, npc_data in data.get("key_npcs", {}).items():
            npc = NPCProfile.model_validate(npc_data)
            if not npc.id:
                npc.id = nid
            key_npcs[nid] = npc

        plot_hooks = [PlotHook.model_validate(h) for h in data.get("plot_hooks", [])]

        encounter_tables = {}
        for loc_id, enc_list in data.get("encounter_tables", {}).items():
            encounter_tables[loc_id] = [
                EncounterTemplate.model_validate(e) for e in enc_list
            ]

        return cls(
            title=data.get("title", ""),
            setting_overview=data.get("setting_overview", ""),
            starting_location_id=data.get("starting_location_id", ""),
            locations=locations,
            factions=factions,
            key_npcs=key_npcs,
            plot_hooks=plot_hooks,
            encounter_tables=encounter_tables,
        )
