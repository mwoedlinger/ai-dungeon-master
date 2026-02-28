"""Campaign data models and database."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel
from src.models.world import Location


class Faction(BaseModel):
    name: str
    description: str
    goals: str
    allies: list[str] = []
    enemies: list[str] = []


class NPCProfile(BaseModel):
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


class EncounterTemplate(BaseModel):
    description: str
    monster_ids: list[str]
    difficulty: Literal["easy", "medium", "hard", "deadly"]
    trigger: str = "random"


class CampaignData(BaseModel):
    title: str
    setting_overview: str
    locations: dict[str, Location]
    factions: list[Faction] = []
    key_npcs: dict[str, NPCProfile] = {}
    plot_hooks: list[PlotHook] = []
    encounter_tables: dict[str, list[EncounterTemplate]] = {}
    starting_location_id: str = ""

    def get_location_context(self, location_id: str) -> str:
        """Return narrative context for the current location."""
        loc = self.locations.get(location_id)
        if not loc:
            return f"Unknown location: {location_id}"

        nearby = [
            self.locations[n].name
            for n in loc.connected_to
            if n in self.locations
        ]
        npcs_here = [n for n in self.key_npcs.values() if n.location == location_id]

        lines = [
            f"## Current Location: {loc.name}",
            loc.description,
        ]
        if nearby:
            lines.append(f"**Nearby**: {', '.join(nearby)}")
        if npcs_here:
            npc_summaries = []
            for npc in npcs_here:
                npc_summaries.append(f"{npc.name} ({npc.disposition}): {npc.personality[:80]}")
            lines.append("**NPCs present**: " + "; ".join(npc_summaries))

        hooks = self.get_relevant_plot_hooks(location_id)
        if hooks:
            lines.append("**Plot hooks**: " + "; ".join(h.title for h in hooks))

        return "\n".join(lines)

    def get_relevant_plot_hooks(self, location_id: str) -> list[PlotHook]:
        return [h for h in self.plot_hooks if h.trigger_location == location_id]

    def query(self, query_type: str, id: str) -> dict:
        """Handle query_world_lore tool calls from the LLM."""
        match query_type:
            case "location":
                loc = self.locations.get(id)
                if not loc:
                    return {"success": False, "error": f"Location {id!r} not found."}
                nearby_names = {n: self.locations[n].name for n in loc.connected_to if n in self.locations}
                npcs_here = {k: v.model_dump() for k, v in self.key_npcs.items() if v.location == id}
                encounters = self.encounter_tables.get(id, [])
                return {
                    "success": True,
                    "location": loc.model_dump(),
                    "connected_to_names": nearby_names,
                    "npcs_present": npcs_here,
                    "possible_encounters": [e.model_dump() for e in encounters],
                }
            case "npc":
                npc = self.key_npcs.get(id)
                if not npc:
                    return {"success": False, "error": f"NPC {id!r} not found."}
                return {"success": True, "npc": npc.model_dump()}
            case "faction":
                for f in self.factions:
                    if f.name.lower().replace(" ", "_") == id.lower() or f.name == id:
                        return {"success": True, "faction": f.model_dump()}
                return {"success": False, "error": f"Faction {id!r} not found."}
            case "plot_hook":
                for h in self.plot_hooks:
                    if h.id == id:
                        return {"success": True, "plot_hook": h.model_dump()}
                return {"success": False, "error": f"Plot hook {id!r} not found."}
            case _:
                return {"success": False, "error": f"Unknown query_type: {query_type!r}"}
