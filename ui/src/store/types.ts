/* TypeScript interfaces mirroring the Python Pydantic models. */

export interface AbilityScores {
  STR: number;
  DEX: number;
  CON: number;
  INT: number;
  WIS: number;
  CHA: number;
}

export interface Weapon {
  name: string;
  damage_dice: string;
  damage_type: string;
  properties: string[];
  range_normal: number | null;
  range_long: number | null;
  attack_bonus_override: number | null;
}

export interface Armor {
  name: string;
  base_ac: number;
  armor_type: string;
  stealth_disadvantage: boolean;
}

export interface MagicItem {
  name: string;
  item_type: string;
  bonus: number;
  rarity: string;
  requires_attunement: boolean;
  properties: Record<string, unknown>;
  description: string;
}

export interface Item {
  name: string;
  description: string;
  quantity: number;
  weight: number;
}

export interface DeathSaves {
  successes: number;
  failures: number;
}

export interface Character {
  id: string;
  name: string;
  race: string;
  class_name: string;
  subclass: string | null;
  level: number;
  xp: number;
  ability_scores: AbilityScores;
  hp: number;
  max_hp: number;
  temp_hp: number;
  ac: number;
  speed: number;
  proficiency_bonus: number;
  skill_proficiencies: string[];
  expertise_skills: string[];
  weapon_proficiencies: string[];
  armor_proficiencies: string[];
  saving_throw_proficiencies: string[];
  spell_slots: Record<string, number>;
  max_spell_slots: Record<string, number>;
  spellcasting_ability: string | null;
  known_spells: string[];
  hit_dice_remaining: number;
  hit_die_type: string;
  class_resources: Record<string, number>;
  weapons: Weapon[];
  armor: Armor | null;
  shield: boolean;
  inventory: Item[];
  gold: number;
  attuned_items: MagicItem[];
  background: string | null;
  alignment: string | null;
  personality_traits: string | null;
  ideals: string | null;
  bonds: string | null;
  flaws: string | null;
  conditions: string[];
  concentration: string | null;
  death_saves: DeathSaves;
  is_player: boolean;
}

export interface Combatant {
  character_id: string;
  initiative: number;
  has_action: boolean;
  has_bonus_action: boolean;
  has_reaction: boolean;
  movement_remaining: number;
}

export interface CombatState {
  active: boolean;
  round: number;
  turn_order: string[];
  current_turn_index: number;
  combatants: Record<string, Combatant>;
}

export interface Location {
  id: string;
  name: string;
  description: string;
  connected_to: string[];
}

export interface Quest {
  id: string;
  title: string;
  description: string;
  status: "active" | "completed" | "failed";
  objectives: string[];
  completed_objectives: string[];
}

export interface TimeState {
  day: number;
  hour: number;
  minute: number;
}

export interface WorldState {
  current_location_id: string;
  locations: Record<string, Location>;
  quests: Quest[];
  time: TimeState;
}

export interface NpcAttitude {
  disposition: string;
  notes: string;
}

export interface JournalEntry {
  event: string;
  location_id: string;
  involved_npcs: string[];
  importance: string;
  turn: number;
}

export interface WorldJournal {
  global_summary: string;
  conversation_summary: string;
  global_entries: JournalEntry[];
  location_summaries: Record<string, string>;
  npc_attitudes: Record<string, NpcAttitude>;
  npc_summaries: Record<string, string>;
  world_flags: Record<string, string>;
}

export interface NarrativeMessage {
  id: string;
  type: "prose" | "player_input" | "event";
  text: string;
  eventType?: string;
  eventData?: Record<string, unknown>;
  timestamp: number;
}

export interface TurnPrompt {
  character_id: string;
  character_name: string;
  is_player: boolean;
}

export interface GameStateSnapshot {
  characters: Character[];
  combat: CombatState | null;
  world: WorldState;
  journal: WorldJournal;
  mode: "exploration" | "combat";
  current_turn: TurnPrompt | null;
}
