# Dungeon Weaver — TODO

> Comprehensive backlog for taking the codebase from "works in dev" to "runs professional 20+ session campaigns reliably."
> Tiers reflect **play impact**: Tier 1 prevents session-ending failures, Tier 2 unlocks sustained campaign play,
> Tier 3 adds depth and developer confidence, Tier 4 is future vision.

---

## Tier 1 — Critical: Crashes, Data Loss, Soft-Locks

These are bugs and missing safeguards that **will** surface during normal play and can end a session or corrupt state. Most are small, high-leverage fixes.

### LLM Loop Safety

The core loop in `dungeon_master.py` is `while True` — the LLM calls tools, gets results, and loops until it produces pure narrative. Several failure modes are unhandled:

- [x] **Max iteration cap on tool loop** (`dungeon_master.py`). Hard cap of 15 iterations; returns graceful fallback message if exceeded.
- [x] **Retry with exponential backoff on API calls**. `_call_with_retry()` handles transient errors (429, 500, 502, 503, timeouts, connection errors) with 3 retries and exponential backoff.
- [x] **Graceful handling of token limit exceeded**. Context overflow detected → emergency compression → retry. Falls back to user-friendly error message.
- [x] **Timeout configuration for OpenAI-based backends** (DeepSeek, Ollama). 120s timeout set on both clients.

### Save/Load Resilience

Game state persistence (`game_state.py`) works but has no protection against corruption or schema changes:

- [x] **Atomic saves**: writes to temp file then `Path.replace()` — crash-safe.
- [x] **Backup rotation**: previous save copied to `.bak` before overwriting.
- [x] **Graceful load errors**: catches `JSONDecodeError` and `ValidationError`, auto-falls back to `.bak` backup.
- [x] **Save schema versioning + migration**: `version` field embedded; `_migrate_save()` applies sequential migrations.
- [x] **Persist monsters in saves**: all characters (PCs + monsters) serialized with `_is_monster` flag for correct deserialization.

### Context Management

The context window is the lifeblood of session continuity. Several edge cases can cause silent data loss:

- [x] **Rollback on compression failure**. History is now pruned only *after* successful compression; API failures preserve all messages.
- [x] **Hard safety check before API call**: `get_messages_for_api()` estimates system prompt overhead and subtracts from budget before trimming.
- [x] **Improve token estimation**: changed from `// 4` to `// 3` (~3 chars/token), better matching real tokenization.

### Combat State Bugs

Combat is the most stateful part of the engine. Several paths lead to crashes or infinite loops:

- [x] **Safe condition removal**. All `conditions.remove()` calls now check membership first or use try/except — no more `ValueError` crashes.
- [x] **All-dead infinite loop**. `end_turn()` checks if all combatants are down before advancing; auto-ends combat if so.
- [x] **Condition duration desync**. `apply_condition()` and `remove_condition()` now accept optional `combat_state` and sync `condition_durations` on the combatant. Tool dispatcher passes combat state.
- [x] **HP floor enforcement**. `apply_damage()` rejects negative amounts, always clamps HP to 0, and consistently applies `dead` condition to monsters at 0 HP.

---

## Tier 2 — High Impact: Unlocks Real Campaign Play

These gaps don't crash the game but **limit it to low-level, short campaigns**. A party that reaches level 5+ or plays more than ~10 sessions will hit these walls.

### Spell System Expansion

The tiered spell system is well-designed, but the resolved spell list is too thin for sustained play:

- [x] **Wire cached SRD spells into resolution system**. Improved `_infer_resolution`, added `_SPELL_OVERRIDES` for spells needing manual resolution, added `save_negates` for Disintegrate-style spells, `flat_healing` for Heal-style spells.
- [x] **Add resolved spells for levels 4-9**. Manual overrides for: Banishment, Greater Invisibility, Dimension Door (L4), Wall of Force, Hold Monster (L5), Heal, Chain Lightning, Disintegrate (L6), Teleport, Forcecage (L7), Power Word Stun (L8), Power Word Kill, Wish, Meteor Swarm (L9).
- [x] **Cantrip damage scaling by character level**. `cantrip_scaling` field on SpellData populated from `damage_at_character_level`; `resolve_spell()` uses `_get_cantrip_dice()` to select correct tier.
- [x] **Automate concentration saves**. `apply_damage()` now auto-rolls CON save (DC = max(10, damage/2)) and drops concentration on failure. No longer relies on LLM noticing the flag.
- [x] **Out-of-combat duration tracking**. `advance_time()` now accepts `game_state` and ticks spell durations via `_tick_spell_durations()`.
- [x] **Alternate upcast patterns**. `upcast_pattern` field on SpellData: "damage", "targets", "duration", "flat_healing". Auto-inferred from `higher_level` text. Flat healing upcasting implemented in `resolve_spell()`.

### Character Progression (Levels 10-20)

Progression works well through level 9 but thins out dramatically for higher levels:

- [x] **Fill `CLASS_FEATURES` for levels 10-20**. All 12 classes now have complete feature schedules through level 20, including subclass feature placeholders at correct levels.
- [x] **Mechanically apply expertise in `ability_check()`**. `expertise_skills` field on Character; `ability_check()` doubles proficiency bonus for those skills.
- [x] **Mechanically apply Jack of All Trades**. Bard level 2+: half proficiency added to non-proficient ability checks in `ability_check()`.
- [x] **Mechanically apply Reliable Talent**. Rogue level 11+: d20 rolls below 10 treated as 10 for proficient skill checks in `ability_check()`.
- [x] **Legendary actions on Monster model**. `legendary_actions`, `legendary_actions_per_round`, `legendary_actions_remaining` fields. `use_legendary_action` tool. Actions refresh at start of monster's turn via `end_turn()`. Auto-parsed from SRD data.
- [x] **Legendary resistance on Monster model**. `legendary_resistances`, `legendary_resistances_remaining` fields. `use_legendary_resistance` tool. Auto-consumed in `_save_with_legendary_resistance()` during spell resolution. Auto-parsed from SRD special abilities.
- [x] **Lair actions**. `lair_actions`, `has_lair` fields on Monster model. `LairAction` data model with save_dc, damage, conditions. Parsed from SRD data when available.

### Death & Continuity

PC death is mechanically resolved (death saves work), but there's no path forward after death:

- [x] **Resurrection mechanic**. `resurrect_character` tool supports Revivify (300gp, level 3 slot), Raise Dead (500gp, level 5, with penalties), Resurrection (1000gp, level 7), and True Resurrection (25000gp, level 9, full HP). Validates spell slots and material costs on caster. Clears dead/unconscious conditions and resets death saves.
- [x] **Party wipe handling**. All-dead detection in `end_turn()` (Tier 1) auto-ends combat. `resurrect_character` tool provides path to reverse death. NPC heal tool allows allied NPCs to intervene before party wipe completes.
- [x] **NPC rescue mechanic**. `npc_heal` tool allows allied NPCs to heal or stabilize downed PCs. Supports both `stabilize_only` (reset death saves) and full healing. Uses existing `apply_healing` engine for reviving unconscious characters.

### Economy & Downtime

Gold exists but has no purpose — characters accumulate it from quests with nothing to spend it on:

- [x] **Merchant/shop system**. `buy_item` and `sell_item` tools with gold deduction/addition. Validates sufficient gold/inventory, stacks items, handles partial quantities. `get_item_price` tool looks up SRD prices.
- [x] **Item price database**. `EQUIPMENT_PRICES` dict in `src/engine/economy.py` with 70+ SRD items (weapons, armor, gear, potions, ammunition). `MAGIC_ITEM_PRICE_RANGES` by rarity for magic items.
- [x] **Crafting system**. `craft_item` tool: INT ability check against DC by rarity (10-30), material cost (half item value), tool proficiency bonus. Failed crafts lose half materials. Returns days required for narration.
- [x] **Downtime activity tools**. `downtime_training` (250-day skill proficiency training with progress tracking), `downtime_carousing` (random event table: trouble/contact/rumor/windfall), `downtime_recuperate` (remove condition + full HP restore in 3 days).

### NPC Memory & World Reactivity

NPCs and the world currently have no long-term memory of player actions:

- [x] **Auto-inject NPC conversation history into dialogue sub-agent**. `NPCDialogueSession` now accepts `journal` parameter. `_build_npc_prompt()` injects: NPC attitude and notes, NPC interaction summary from `npc_summaries`, and recent journal entries involving the NPC. `start_npc_dialogue` tool passes `gs.journal` to the session.
- [x] **Faction reputation system**. `FactionReputation` model with score (-100 to +100), tier property (hostile/unfriendly/neutral/friendly/allied), and capped history log. `adjust_faction_reputation` and `get_faction_reputation` tools. Reputation displayed in journal context block. Clamped to [-100, +100].
- [x] **World state beyond binary flags**. `set_world_flag` tool description updated to document numeric values (`'orc_threat': '45'`), timestamps (`'bridge_collapsed_day': '7'`), and binary flags. Journal entries now include `day` field for temporal context. Faction reputation provides structured numeric tracking separate from flags.

### Campaign Time

Time tracking exists but lacks depth for campaign pacing:

- [x] **Travel time between locations**. `LocationConnection` model with `travel_hours` and `description` fields. `travel_to_location` tool: calculates travel time from connections, applies pace modifiers (fast ×0.75, slow ×1.5), advances the clock via `advance_time()`, flags random encounter eligibility for journeys ≥1 hour, then moves party to destination. `travel_time()` helper function for querying without moving. Parent-child locations (tavern in village) are instant.
- [x] **Time-gated quest events and deadlines**. `deadline_day` and `deadline_description` fields on Quest model. `_check_quest_deadlines()` called by `advance_time()` — auto-fails active quests past their deadline and returns expiration info for narration.

---

## Tier 3 — Quality & Polish

Improvements to developer experience, code quality, and mechanical depth. Not blocking play but increase confidence and richness.

### Input Validation

The tool dispatcher trusts the LLM to send well-formed inputs. It usually does, but when it doesn't, errors are cryptic:

- [ ] **Pre-validate tool inputs against schema**. Check that required fields exist and have correct types before calling the handler. Currently, a missing `ability` field in `ability_check` produces a raw `KeyError` caught by a broad `except` — the LLM gets a generic "engine error" with no guidance.
- [ ] **Validate entity references**. When `character_id` or `target_id` doesn't exist in `game_state.characters`, return an error listing valid IDs instead of a generic "not found." This helps the LLM self-correct.
- [ ] **Case-insensitive spell name lookup**. The LLM may send "Magic Missile" while the SRD stores "magic missile" (or vice versa). Currently returns `None` silently. Add `.lower()` normalization.
- [ ] **Null-check `get_monster_template()`** return. An unknown template ID returns `None`, then the code accesses `.id` on it — `AttributeError` crash. Should return a clean validation error.
- [ ] **Bounds-check numeric inputs**. `apply_damage(amount=-5)` or `cast_spell(spell_level=15)` should be rejected, not silently processed.
- [ ] **Log failed tool calls to EventLog**. Currently only successful dispatches are logged. Failures (caught at the broad `except`) are invisible — can't debug why the LLM keeps retrying the same broken call.

### Observability & Debugging

The codebase has almost no logging. Debugging a bad session after the fact is impossible:

- [x] **Structured logging**. Python `logging` in the DM loop, tool dispatcher, and context manager. DEBUG: every tool call, API request/response shape, compression events. WARNING: tool failures, context budget exceeded, unexpected LLM behavior.
- [x] **Persistent EventLog**. JSONL file alongside the save (`*.events.jsonl`). Append mode across sessions. `EventLog.load_entries()` for post-session analysis.
- [x] **`--debug` CLI flag**. Prints tool call name, compact inputs, and OK/FAIL status in real-time alongside narrative. `--verbose` for INFO-level logging.
- [x] **Token usage tracking**. `TokenUsage` dataclass extracted from all backends (Anthropic, DeepSeek, Gemini, Ollama). `SessionTokenStats` aggregates per-session with per-provider cost estimation. Summary printed at session end.
- [x] **Compression visibility** (`--verbose`). Logs when compression triggers (estimated tokens, threshold, message count), post-compression stats (token reduction, summaries extracted), and global summary at DEBUG.

### Testing

238 unit tests cover engine mechanics well, but there are significant gaps:

- [ ] **Full DM loop integration tests**. No test exercises `process_player_input()` → backend → tool dispatch → narration end-to-end. A mock backend that returns scripted tool calls would catch serialization bugs, tool dispatch routing errors, and context management regressions.
- [ ] **Backend serialization tests**. Each backend converts between internal message format and its API's format differently. No tests verify this conversion. A Gemini-specific bug (e.g., tool_result format) would only surface during live play.
- [ ] **Failure-path tests**. No tests for: corrupted save files, API timeouts, malformed LLM tool calls (missing required fields, wrong types), references to non-existent characters. These are the most common production failures.
- [ ] **Streaming tests**. `stream_complete()` methods exist on all backends but have zero test coverage.
- [ ] **Campaign-level integration test**. Load a full campaign, create characters, play 10 turns of combat, save, reload, verify all state persists. This is the closest thing to a smoke test for the whole system.
- [ ] **High-level spell resolution tests**. Once level 4-9 spells are implemented, add tests covering upcast scaling, concentration, multi-target resolution, and interaction with legendary resistance.

### Configuration

All behavioral parameters are hardcoded — users can't tune the experience:

- [ ] **Config file support**. `config.yaml` or equivalent for: temperature, max_tokens, retry count, compression thresholds, debug mode. Allow per-campaign overrides.
- [ ] **`--temperature` CLI flag**. Let players choose between conservative (0.3, predictable combat narration) and creative (0.9, wild improv) styles.
- [ ] **`--max-response-tokens` flag**. Currently hardcoded to 2048 for all backends and all contexts. A long-rest scene description deserves more tokens than a single attack narration.
- [ ] **Configurable compression thresholds**. Different campaign styles need different memory: a combat-heavy dungeon crawl can compress aggressively, while a political intrigue campaign needs longer narrative memory.

### Tactical Positioning & Movement

Currently combat has no spatial dimension — everything is abstract narrative distance:

- [ ] **Movement speed consumption**. Track remaining movement per turn. A character with 30ft speed can move 30ft total, split across actions.
- [ ] **Opportunity attacks**. Trigger when a combatant leaves melee range without taking the Disengage action. Core 5e tactical mechanic.
- [ ] **Readied actions**. "I ready an attack for when the goblin comes around the corner." Requires reaction economy tracking.
- [ ] **AoE targeting helper**. Given an area type (cone, sphere, line) and positions, return which combatants are affected. Currently the LLM guesses.
- [ ] **Difficult terrain**. Double movement cost in certain areas. Requires location metadata.

### Equipment & AC

Equipment models (Weapon, Armor, MagicItem) are well-defined, but equipping and AC calculation have critical gaps that break mid-campaign play:

- [x] **Dynamic AC recalculation**. `recalculate_ac()` in `rules.py` computes AC from current armor + ability scores + class features (Monk/Barbarian Unarmored Defense) + shield. Called from `improve_ability_score`, `equip_armor`, `equip_shield`. Magic item bonuses applied at attack-resolution time to avoid double-stacking.
- [x] **Equip/unequip armor tool**. `equip_armor` moves armor from inventory to `char.armor` (returning old armor to inventory), recalculates AC. Supports `item_name="unequip"` to just remove current armor.
- [x] **Equip/unequip weapon tool**. `equip_weapon` adds to `char.weapons` (removes from inventory if present). `unequip_weapon` returns to inventory. Error messages list currently equipped weapons.
- [x] **Shield support**. `equip_shield` tool sets `char.shield` bool and recalculates AC (+2). Shield boolean now read by `recalculate_ac()`.
- [x] **AC auto-update on ability score improvement**. `improve_ability_score` now calls `recalculate_ac()` and reports `ac_changed` in the result when AC changes (e.g., DEX for light/medium armor, WIS for Monk, CON for Barbarian).

### Class Mechanics & Spell Validation

Essential gameplay mechanics that were missing or broken, affecting core class identity and spell system integrity:

- [x] **Spell-known validation**. `cast_spell` now checks `caster.known_spells` before resolving (case-insensitive). Rejects unknown spells with a list of known spells in the error. Skipped for monsters and characters with empty spell lists (not yet fully set up).
- [x] **Second Wind tool (Fighter)**. `use_second_wind` heals 1d10 + fighter level as a bonus action. Consumes `second_wind` class resource (restored on short rest). Class-restricted to Fighters.
- [x] **Lay on Hands tool (Paladin)**. `use_lay_on_hands` heals target from the Paladin's healing pool (level × 5 HP). Pool tracked as `lay_on_hands` class resource (restored on long rest). Can revive unconscious characters.
- [x] **Short rest restores class resources**. `short_rest()` now restores: `second_wind`, `action_surge`, `channel_divinity`, `ki`, `wild_shape`, `superiority_dice`. Warlock pact spell slots also restore on short rest. Bardic Inspiration restores at Bard 5+ (Font of Inspiration).
- [x] **Long rest restores ALL class resources**. `long_rest()` now computes max values from `CLASS_FEATURES` progression table and resets all resources (rage, lay_on_hands, sorcery_points, sneak_attack_dice, etc.).
- [x] **Sneak Attack damage (Rogue)**. Attack dispatch auto-adds `sneak_attack_dice` d6 when: weapon has finesse or ranged property, AND (attacker has advantage OR another living ally is in combat). Crits double sneak attack dice. Result includes `sneak_attack` field with dice and damage.

### Magic Items

- [ ] **Item-granted abilities mechanically resolved**. The `MagicItem.properties` field supports `{"daily_spell": "fireball", "charges": 3}` in the schema, but the engine never reads or acts on these properties. A Staff of Fire should actually let you cast Fireball — currently it's just flavor text.

### Feats

- [ ] **Feat data model**. Curated SRD feat set: Alert, Great Weapon Master, Sentinel, Lucky, War Caster, Sharpshooter, Resilient, Tough. Each needs a mechanical effect hook.
- [ ] **ASI-or-feat choice**. At ASI levels (4, 8, 12, 16, 19), the LLM should ask the player: improve ability scores or take a feat? Currently only ASI is offered.
- [ ] **Feat effects in engine**. Feats like GWM (optional -5 attack / +10 damage) or Sentinel (opportunity attack on Disengage, reduce speed to 0 on hit) need to hook into existing engine calls.

---

## Tier 4 — Extensions

Long-term vision features. Not required for campaign play but would significantly enhance the experience:

- [ ] **Encounter balancing tools**. XP budget calculator by party level and size. Help the DM (or campaign author) design appropriately challenging encounters.
- [ ] **More resolved spells**. Continuously promote spells from narrative to resolved tier based on playtest frequency. If players keep casting Haste, give it full engine support.
- [ ] **Homebrew content injection**. User-defined items, monsters, and spells via custom JSON/YAML files loaded alongside SRD data. Essential for DMs with custom worlds.
- [ ] **Voice interface**. TTS for DM narration (immersive), STT for player input (hands-free play). Could use system TTS or cloud APIs.
- [ ] **Graphical UI**. Web or desktop app complementing the Rich CLI. Map display, character portraits, drag-and-drop inventory, clickable spell lists.
- [ ] **AI-generated scene images**. DALL-E or Stable Diffusion triggered by location changes, combat start, and dramatic narrative beats. Displayed inline in the UI.
- [ ] **Surprise round mechanics**. Pre-initiative round where surprised combatants can't act. Requires stealth checks vs. passive perception.
- [ ] **Monster AI heuristics**. Simple decision logic (focus low-HP targets, retreat at 25% HP, protect casters) so the LLM doesn't have to reason about every goblin's turn from scratch. Reduces API calls per combat round.

---

## Miscellaneous

Small fixes and improvements that don't fit neatly into the tiers:

- [ ] Use location description from campaign data instead of generating it when calling `/location`
- [ ] Extensive playtesting and prompt tuning
- [ ] Unbounded NPC dialogue session cache (`tools.py:584`) — prune old sessions or cap size to prevent memory growth
- [ ] NPC dialogue turn limit hardcoded to 6 (`npc_dialogue.py:14`) — make configurable for complex plot conversations

---

## Priority Matrix

| Category | Items | Effort | Impact | Suggested Order |
|---|---|---|---|---|
| LLM loop safety (max iterations, retry, timeout, token overflow) | 4 | S | Prevents crashes | **1st** |
| Combat state bugs (condition remove, dead loop, duration sync, HP floor) | 4 | S | Prevents soft-locks | **2nd** |
| Save/load resilience (atomic write, backup, schema migration) | 5 | S–M | Prevents data loss | **3rd** |
| Context safety (compression rollback, pre-flight check, token estimation) | 3 | S | Prevents history loss | **4th** |
| Input validation (schema check, entity refs, case normalization) | 6 | S | Fewer LLM-caused errors | **5th** |
| Cantrip scaling + concentration auto-save | 2 | S | Core 5e correctness | **6th** |
| Expertise / Jack of All Trades / Reliable Talent | 3 | S | Core 5e correctness | **7th** |
| Observability (logging, persistent event log, debug flag) | 5 | S–M | Debuggability | **8th** |
| Death handling (resurrection, party wipe, NPC rescue) | 3 | S–M | Campaign continuity | **9th** |
| Spell system expansion (wire 319 spells, add levels 4-9) | 6 | L | Unlocks high-level play | **10th** |
| Class features levels 10-20 | 1 | M | Meaningful progression | **11th** |
| Legendary/lair actions on monsters | 3 | M | Boss fight quality | **12th** |
| Economy (merchant, prices, crafting, downtime) | 4 | M | World feels alive | **13th** |
| NPC memory + faction reputation | 3 | M | World reactivity | **14th** |
| Integration + backend + failure-path tests | 6 | M | Confidence in changes | **15th** |
| Campaign time (travel, deadlines) | 2 | S | Pacing and urgency | **16th** |
| Configuration (config file, temperature, max tokens) | 4 | S | User control | **17th** |
| Tactical movement (speed, opportunity attacks, AoE) | 5 | M–L | Combat depth | **18th** |
| Feats system | 3 | M | Character customization | **19th** |
| Magic item abilities | 1 | M | Item depth | **20th** |
| Extensions (voice, GUI, images, homebrew, encounter balance) | 8 | L–XL | Future vision | **21st** |

**Effort key**: S = hours, M = 1-3 days, L = 1-2 weeks, XL = weeks+
