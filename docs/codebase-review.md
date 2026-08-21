# Dungeon Weaver — Codebase Review

*Date: 2026-06-11. Scope: full `src/` + `main.py` at working-tree state (uncommitted streaming refactor included). Test suite: 366 passed, 5 skipped.*

> **Fix status (2026-06-12):** All bugs in sections 1 and 2 are fixed (✅). Section 3: 3.1, 3.2, 3.3, 3.6 fixed; 3.4 fixed in simplified form (opportunity attacks + reaction spells; movement consumption and Counterspell interrupts deliberately out of scope); 3.5 deferred. Attack resolution is unified (roadmap #4). Regression tests in `tests/test_bugfix_regressions.py`; full suite 400 passed, 5 skipped. Remaining open work: 3.5 (unified ActiveEffect records), Counterspell-style cast interrupts, and the SessionManager facade for the web UI (roadmap #5).
>
> **Re-review (2026-06-13):** Focused pass over the newer `src/api/` web layer (added after the last review). Found **three regressions in the web combat loop** — all bugs that were fixed in the CLI but never reached the web path because the loop is reimplemented rather than shared (section 5). This is the concrete cost of deferring the roadmap #5 facade: the two transports have already diverged in correctness. Bug 6.1 (dying PCs skipped) is high priority. `src/engine/economy.py` (buy/sell/craft/resurrect, ~347 lines) is wired into the dispatcher but missing from the CLAUDE.md architecture map.

The architecture is sound: the LLM/engine split is consistently enforced, Pydantic state models are clean, the structured journal compression is a genuinely good design, and the multi-backend abstraction is tidy. The issues below are mostly correctness gaps in the rules engine, context-management edge cases that will surface as API 400s in long sessions, and a few CLI wiring problems.

---

## 1. Bugs — high priority

### ✅ 1.1 Long rest resurrects dead characters — FIXED
`src/engine/rest.py:77-89` — `long_rest()` sets `hp = max_hp` unconditionally and strips every condition except `"cursed"`, including `"dead"`. A dead PC who "takes a long rest" comes back at full HP. Add a guard:

```python
if "dead" in character.conditions:
    return {"success": False, "error": f"{character.name} is dead."}
```

Related: a long rest should remove only **one** level of exhaustion, not all `exhaustion_*` conditions.

### ✅ 1.2 Player resistances/immunities are never applied — FIXED
`src/engine/rules.py:433-437` — `apply_damage()` only checks `damage_immunities`/`damage_resistances` on `Monster`. `Character` has no resistance fields at all, so racial/class/spell resistances (Bear Totem, *protection from energy*, tiefling fire resistance…) are silently impossible. Add `damage_resistances`/`damage_immunities` to `Character` and check them for all targets.

### ✅ 1.3 Concentration check uses the wrong amount, and only for players — FIXED
`src/engine/rules.py:459-471` —
- DC is computed from `amount` (pre-resistance/pre-temp-HP raw input) instead of damage actually taken.
- The check is gated on `target.is_player`, so concentrating monsters (casters are common) never risk losing concentration.

### ✅ 1.4 `cast_spell` can burn a lower-level slot for a higher-level spell — FIXED
`src/engine/spells.py:88-94` — `resolve_spell` validates only that `caster.spell_slots[cast_level] > 0`. There is no check that `cast_level >= spell.level`, so the LLM passing `spell_level: 1` for Fireball deducts a level-1 slot and resolves the spell at full strength. Validate `cast_level >= spell.level` (and reject `cast_level > max known tier`).

Also in `resolve_spell`: the slot is deducted and concentration switched **before** the resolution `match` — the `case _` error path ("Unknown spell resolution type") still consumes the slot and may have dropped an active concentration spell. Move side effects after validation, or refund on failure.

### ✅ 1.5 Unconscious PCs never get their death-save turn — FIXED
Two places treat `hp <= 0` as "skip this combatant":
- `src/engine/combat.py:101-111` (`end_turn` skip loop — comment even says "Skip combatants that are dead (0 HP …)")
- `src/interface/session.py:139-142` (auto-skip without involving the LLM)

In 5e an unconscious PC still takes a turn to roll a death save. As written, death saves only happen if the LLM spontaneously calls `death_save` during someone else's turn. A downed PC can hang in limbo indefinitely. Fix: skip only `"dead" in conditions`; when the current combatant is an unconscious PC, auto-roll (or prompt) a death save and then advance.

Related inconsistency in `combat.py:206-210` (`death_save`): on 3 successes the code **removes** `"unconscious"` while HP stays 0 — RAW the character is *stable but unconscious*. The resulting state (0 HP, conscious, no condition) confuses `apply_healing`'s revive logic (`rules.py:478`), which keys on `"unconscious"` being present. Introduce a `"stable"` flag instead of removing `"unconscious"`.

### ✅ 1.6 `npc_heal(stabilize_only=True)` doesn't stabilize — FIXED
`src/dm/tools.py:1668-1679` — the comment says "set to 0 HP, remove unconscious, reset death saves", but the code only resets `death_saves`. The character remains unconscious and (with 1.5 fixed) would keep rolling death saves. Same root cause as above: no "stable" concept.

### ✅ 1.7 Context trimming/compression can split tool_use/tool_result pairs — FIXED
`src/dm/context.py`:
- `get_messages_for_api` (`context.py:327-330`) pops oldest messages one at a time. If it pops an assistant `tool_use` message but leaves its `tool_result`, or leaves history starting on an assistant message, the Anthropic API rejects the request (400: orphaned `tool_result`).
- `compress_if_needed` (`context.py:414, 453`) prunes `full_history[:n_to_compress]` where `n_to_compress = len//2` — the cut point ignores message structure, so it can also strand a `tool_result` at the head of the remaining history.

This bites exactly when context pressure is highest (long sessions). Fix: after choosing a cut index, advance it until the boundary is a plain `user` text message (and never separate an assistant-with-tools message from the following results message).

### ✅ 1.8 Hitting MAX_TOOL_ITERATIONS leaves malformed history — FIXED
`src/dm/dungeon_master.py:251-252` — on loop exhaustion the last appended message is the `user` message carrying tool results; the function returns a placeholder without appending an assistant message. The next player input appends a second consecutive `user` message → Anthropic rejects non-alternating roles. Append a synthetic assistant message (e.g. the placeholder text) before returning. The same exhaustion path also skips `compact_tool_pairs()`/`compress_if_needed()`.

### ✅ 1.9 `--save` loads a save but writes progress elsewhere — FIXED
`main.py:345, 360, 379` — the save/autosave path passed to `DungeonMaster`, `ToolDispatcher`, and `SessionManager` is always `args.autosave`. Running `python main.py --save saves/mysave.json` loads `mysave.json` but `/save`, `/quit`, and the `save_game` tool all write to `saves/autosave.json`. Default the write path to the loaded save (`args.save or args.autosave`).

### ✅ 1.10 Every `DungeonMaster` init failure is reported as an auth error — FIXED
`main.py:353-365` — the bare `except Exception` around the constructor funnels into `_handle_auth_error`, which prints API-key instructions and `sys.exit(1)`. A missing optional dependency, a typo'd model name, or any other init bug masquerades as "Authentication error". Also `main.py:382` catches `TypeError` to detect auth failures during the session — SDK auth errors are not `TypeError`s; catch the SDK's `AuthenticationError` (per backend) instead.

### ✅ 1.11 Session-loop dead-combatant fallback re-raises — FIXED
`src/interface/session.py:134-138` — if `current_combatant_id` isn't in `characters` (e.g. a monster removed by `end_combat` with stale combat state), the `except KeyError` handler calls `end_turn()`, whose first statement is `game_state.get_character(current_id)` (`combat.py:62`) — the same `KeyError` escapes and crashes the loop. `end_turn` needs to tolerate a missing current combatant.

---

## 2. Bugs — medium / low

| # | Location | Issue |
|---|----------|-------|
| ✅ 2.1 | `src/engine/dice.py:28` | `kh` notation doesn't accept modifiers — `"4d6kh3+2"` raises `ValueError`, which surfaces as a tool error mid-game. Advantage/disadvantage args are also silently ignored for `kh` expressions. |
| ✅ 2.2 | `src/engine/combat.py:22` | Initiative tie-break sorts by DEX *modifier*, but the comment promises "DEX then name"; name is absent, and DEX is already baked into the initiative value, so the tie-break is effectively a no-op double-count. |
| ✅ 2.3 | `src/engine/spells.py:129-156` | Spell attack rolls bypass the condition system entirely (no advantage from `attacked_advantage`, no attacker disadvantage from `poisoned` etc.), ignore attuned magic-armor AC, and report rolled damage rather than `damage_dealt` after resistances. Weapon attacks and spell attacks should share one resolution path. |
| ✅ 2.4 | `src/engine/spells.py:109-127` | AoE save spells roll damage **per target**; RAW rolls once for all targets. Minor, but makes Fireball swingier than intended. |
| ✅ 2.5 | `src/engine/spells.py:159-175` | `HEALING` resolution heals only `targets[0]` — *Mass Cure Wounds* / *Mass Healing Word* silently drop other targets. |
| ✅ 2.6 | `src/engine/rules.py:211-212` | Reliable Talent mutates `raw` before the `nat_20`/`nat_1` flags are computed, so a natural 1 on a proficient Rogue-11 check reports `nat_1=False`. Cosmetic, but the LLM narrates from these flags. |
| ✅ 2.7 | `src/dm/dungeon_master.py:87-94` | `_is_context_overflow` matches the substring `"max_tokens"` — a validation error about the `max_tokens` parameter would trigger a pointless emergency compression instead of surfacing the real error. |
| ✅ 2.8 | `src/dm/dungeon_master.py:28-33` | Cost table hardcodes Sonnet pricing for the whole `anthropic` provider regardless of `--model`, and ignores cache read/write pricing even though cache tokens are tracked. Estimated cost will drift badly on cache-heavy sessions. |
| ✅ 2.9 | `src/engine/game_state.py:121-133` vs `combat.py:154` | Quest-completion XP (`award_xp`) gives the **full** reward to every PC, while `end_combat` **splits** XP among PCs. Pick one convention. |
| ✅ 2.10 | `src/engine/progression.py:412-419` | `_eval_scaling` uses `eval()` on formula strings. Data is in-repo today, but campaign JSON is user-supplied territory; a tiny arithmetic parser (or `simpleeval`) removes the footgun. |
| ✅ 2.11 | `src/dm/tools.py:1415-1449` | `attune_item` lets the LLM mint arbitrary items with arbitrary bonuses out of thin air — there's no cross-check against location treasure or inventory. Combined with `equip_weapon` (also free-form), the "engine is the arbiter" principle has a trust hole: numbers are computed deterministically, but their *inputs* are LLM-invented. Consider requiring the item to exist in inventory/treasure. |
| ✅ 2.12 | `src/engine/rules.py` attack path | Proficiency bonus is always added (`rules.py:298`) — `weapon_proficiencies` is stored on `Character` but never consulted. Same for `armor_proficiencies` and `strength_requirement` in `equip_armor` (`tools.py:1466`). Either enforce or delete the fields. |
| ✅ 2.13 | `src/models/character.py:109` | `death_saves: DeathSaves = DeathSaves()` — works under Pydantic v2 (deep-copied), but `default_factory=DeathSaves` is the idiomatic, safe form; same for the bare `[]`/`{}` defaults. |
| ✅ 2.14 | `src/log/event_log.py:47` | Event log opens with mode `"a"` and is never rotated — `autosave.events.jsonl` grows unboundedly across sessions, and `get_session_recap_data` would include stale events if entries were ever hydrated from disk. |
| ✅ 2.15 | `src/dm/dungeon_master.py:355` | *(found post-review)* `/summary` crashed with `AttributeError`: `generate_story_summary` read `context_manager.messages`, but the attribute is `full_history`. |
| ✅ 2.16 | `src/dm/tools.py` (`start_combat`) | *(found post-review)* Calling `start_combat` while combat was already active re-rolled initiative, reset the round to 1, and spawned a duplicate set of monsters. Now rejected with the current turn order returned to the LLM. |
| ✅ 2.17 | `src/interface/session.py` (monster turn) | *(found post-review)* If the LLM narrated a monster turn without calling `end_turn`, the session re-prompted the same monster's turn forever. The session now force-advances the turn when the current combatant is unchanged after the render. |
| ✅ 2.18 | `src/interface/cli.py:359,377` | *(found post-review)* Negative attack bonuses rendered as `1d20+-2`; now signed formatting (`1d20-2`). |
| ✅ 2.19 | `src/dm/tools.py` (dispatch) | *(found post-review)* The LLM could fast-forward whole rounds inside one response by chaining `end_turn` calls (skipping monster turns, desyncing the session loop and turn separators). Dispatcher now enforces a per-render **turn scope**: each combat render may act for and end exactly one combatant's turn; a combat started mid-render is locked until the session prompts the first turn. `None` scope (API server/scripts) stays unrestricted. |
| ✅ 2.20 | `src/interface/session.py` (`_process_and_render`) | *(found post-review)* Dice rolls logged after streaming began were displayed under the NEXT render's turn separator (attacks appearing under the wrong combatant's turn). A final flush at end-of-render fixes attribution. |

---

## 3. Suboptimal implementations

### ✅ 3.1 Conversation history is not persisted — FIXED
*(Fixed: `GameState.conversation_history` field (save schema v2, migration included, capped at the last 200 messages); `ContextManager.full_history` is now a property backed by it, so the history survives save/load.)*

`ContextManager.full_history` lives only in memory. On `/quit` → reload, the DM keeps journal summaries but loses all un-summarized recent dialogue — the first response after loading visibly "forgets" the last scene. Persist `full_history` (or its tail) in the save file, or force a compression pass on save so the journal captures everything.

### ✅ 3.2 Token estimation is crude where it matters most — FIXED
*(Fixed: trimming now uses per-message sizes + suffix sums (O(n)); the DM reports the real prompt size from each response (`input + cache read + cache write`) to `ContextManager.last_actual_prompt_tokens`, which compress_if_needed uses alongside the estimate.)*

`context.py:499-506` estimates `len(json.dumps(msgs)) // 3` and `get_messages_for_api` re-serializes the whole history **multiple times per call** (once for the check, once per pop in the trim loop — O(n²) in messages). Use the actual `usage.input_tokens` from the previous response as the primary signal (it's already tracked in `SessionTokenStats`) and keep the estimate only for the first call.

### ✅ 3.3 Tool schemas are sent uncached-aware but unre-used — FIXED
*(Fixed: `get_tool_schemas(context_window)` serves a 28-tool core set (~3.8k est. tokens) to backends under 32k context instead of the full 62 tools (~9.5k est. tokens, which alone overflowed Ollama's 8k window).)*

All 60+ tool schemas (~the bulk of the prompt) ride on every iteration. They sit before the cached system block so they do participate in the prompt cache for Anthropic — good — but Gemini/DeepSeek/Ollama get the full payload every time with much smaller windows (Ollama: 8k!). 60 tools plus system prompt likely *already* overflows the Ollama window before any history. Consider a reduced tool set for small-context backends, or tool-choice gating by mode (exploration vs. combat tools).

### ✅ 3.4 `_validate_combat_action` has narrow coverage — FIXED (simplified)
*(Fixed: new `opportunity_attack` tool consumes `has_reaction` (melee-only, off-turn-only, once per round); `use_legendary_action` now rejects use on the monster's own turn; `end_combat` outside combat is rejected (no more phantom XP); unused `COMBAT_ONLY_TOOLS` removed. Reaction spells: `casting_time == "reaction"` spells (Shield) may be cast off-turn — they bypass the turn-scope checks and consume the reaction; Shield applies a "shielded" condition (+5 effective AC) that expires at the end of the caster's next turn. Deliberately out of scope: movement consumption (meaningless without a positioning system) and Counterspell, which needs a cast-interrupt flow the turn-based tool loop doesn't have.)*

`tools.py:916-933` — only `attack`, `cast_spell`, `apply_condition`, `use_second_wind`, `use_lay_on_hands` have action costs; `use_legendary_action` isn't validated against whose turn it is (legendary actions happen *between* turns, but nothing checks the actor isn't acting on its own turn for free), movement is tracked (`movement_remaining`) but no tool ever consumes it, and reactions (`has_reaction`) are dead state — there is no opportunity-attack or reaction-spell path at all.

### 3.5 Two sources of truth for condition durations
Durations live in `Combatant.condition_durations` while the condition itself lives in `Character.conditions`; sync is manual in `apply_condition`/`remove_condition`/`end_turn`. Out-of-combat durations are handled by a *third* mechanism (`time_tracking._tick_spell_durations`) that only handles concentration ≥1h. A single `ActiveEffect` record (condition, source, expiry in rounds or minutes) owned by the character would eliminate the desync class.

### ✅ 3.6 `generate`/`compress` assume `response.content[0].text` — FIXED
`anthropic_backend.py:73, 87` — an empty completion (or future thinking-block-first response shape) raises `IndexError`. Iterate content blocks for the first text block instead. *(Fixed: `_first_text()` helper.)*

### 3.7 Misc
- ✅ `dungeon_master.py:165` hardcodes `max_tokens=2048` — long set-piece narrations get truncated mid-sentence with no continuation handling. *(raised to `MAX_RESPONSE_TOKENS = 4096`)*
- ✅ `anthropic_backend.py:35` — the `prompt-caching-2024-07-31` beta header has been GA for a long time; drop it. *(removed)*
- ✅ `session.py:8` imports `Panel` unused; `commands.py:72` builds `used` dict and discards it. *(both removed)*
- `_cmd_exit` says "Quit without saving" but the autosave file from the *last* `save_game` tool call persists — fine, but the legacy bare-word `q` maps to *save-and-quit* in commands while `quit/exit/q` in the exploration loop routes through the LLM (`session.py:103-105`); three subtly different quit paths. *(✅ unified: bare `quit`/`exit`/`q` now route through `/quit` (save + exit) in both exploration and combat — no LLM round-trip, no unsaved exit)*
- Repo hygiene: `josef.json`, `.DS_Store`, `reports/`, `.vscode/` are untracked at root; `.DS_Store` belongs in `.gitignore`, the rest should be committed or relocated deliberately. `CLAUDE.md`, `TODO.md`, `DESIGN_WEB_UI.md` are untracked too. *(🔶 `.DS_Store` added to `.gitignore`; deciding what to commit is left to the author)*

---

## 4. Suggested next steps (ordered)

1. ✅ ~~**Fix the session-killers first** (½ day): tool-pair-safe trimming/compression (1.7), MAX_TOOL_ITERATIONS history repair (1.8), `--save` write path (1.9), auth-error masking (1.10), `end_turn` KeyError (1.11).~~ **Done.**
2. ✅ ~~**Rules-engine correctness pass** (1 day): dead-character long rest (1.1), player resistances (1.2), concentration fixes (1.3), upcast slot validation (1.4), death-save turn flow + `stable` state (1.5/1.6).~~ **Done** — regression tests in `tests/test_bugfix_regressions.py`.
3. ✅ ~~**Persist conversation history in saves** (3.1)~~ **Done** — save schema v2.
4. ✅ ~~**Unify attack resolution** (2.3)~~ **Done** — `rules.resolve_attack()` is the single d20 core (condition adv/disadv, effective AC, crit dice, nat 1/20); `attack_roll()` (weapons) and the spell `ATTACK_ROLL` path both delegate to it. The `attack` tool now also accepts monster statblock actions (Bite, Claw, …) by name, using `MonsterAction.attack_bonus` as the override, and SRD monster weapons carry their statblock attack bonus instead of a recomputed STR-mod guess.
5. **Web UI / shared game-loop facade** — *(now urgent, not just hygiene — see section 6).* `src/api/_process_combat_turns` has already diverged from `SessionManager._combat_input_loop` and lost three fixes (5.1–5.3). Before building the web UI further, extract a transport-agnostic combat/turn driver that both `SessionManager` and `GameSession` call, so dying-PC handling, the stall guard, and turn-scope live in exactly one place. `SessionManager` currently mixes input handling, ANSI cursor tricks, and game logic; the `_TeeWriter`/Rich coupling in `main.py` is another sign the presentation layer needs a seam. **Stopgap:** until the facade exists, port the three fixes into `_process_combat_turns` (cheap, ~30 lines) so the web path isn't shipping a known softlock.
6. ✅ ~~**Reaction/opportunity-attack support** (3.4)~~ **Done (simplified)** — opportunity attacks and reaction spells (Shield) in; Counterspell interrupts deferred.
7. ✅ ~~**Small-context backend strategy** (3.3)~~ **Done** — measured (62 tools ≈ 9.5k est. tokens) and core-set gating added at <32k context.
8. ✅ ~~**Cost model accuracy** (2.8)~~ **Done** — per-model substring-matched price table including cache read/write rates.
9. **Interactive inventory & character management** — full redesign in [`DESIGN_INVENTORY_UI.md`](DESIGN_INVENTORY_UI.md). Replaces the slash-command inventory with modal, keyboard-driven terminal screens (open with `i`/`c`, operate by selection — zero memorized commands) backed by a transport-agnostic `InventoryController` shared with the web UI. Folds in the §2.12 dead weight fields (compute + soft-warn encumbrance) and the missing gold/attunement/consumable surfaces. **Phase 1 done (2026-06-14):** built as a *controller façade over the legacy storage* (not a stored unified model — that flip would have churned ~20 combat-critical AC/equipment tests for no user gain), so no save-schema change. `src/models/items.py` (DTO layer) + `src/engine/inventory.py` (`InventoryController`: `view`/`actions_for`/`apply` over `weapons`/`armor`/`shield`/`inventory`/`attuned_items`); `/inventory` renders the unified view (gold, equipped slots, attunement, usable consumables). **Interactive screens done (2026-06-14):** `src/interface/screens/menu.py` (reusable `select`/`MenuOption` over Rich `Live`+`readchar`, injectable key reader, `interactive_enabled()` guard) + `screens/inventory_screen.py` (pick item → contextual action menu → apply → re-render). Opened by bare hotkey **`i`** in `session.py`, with a static-render fallback under piped stdin so the headless harness/CI are unaffected. The key reader uses a raw `os.read`+`select` path (not `readchar.readkey`, which blocks on a lone Esc) so Esc backs out instantly. `readchar>=4.0` added to base deps. **Character screen done (2026-06-14):** `screens/character_screen.py` — full sheet as the menu header (shared `cli.build_character_sheet`), actions: Manage inventory, Short/Long rest (engine-side, disabled in combat), Switch character; opened by **`c`**. 37 new tests total; suite 450 passed, 5 skipped. **Next:** expose `use_item` as an LLM tool + route writer tools through the controller (closes the §2.11 equip-trust-hole the façade leaves open — legacy storage still lets the LLM supply weapon stats); web view reuses the controller. Caveat: menu rests bypass the LLM, so the DM narrative isn't told time passed (per design principle 4, management screens make zero LLM calls).

---

## 5. New findings — web API layer (2026-06-13)

The `src/api/` FastAPI layer reimplements the combat turn loop in `game_server._process_combat_turns` instead of sharing the CLI's `SessionManager._combat_input_loop`. The two have diverged: every combat fix landed in the CLI after the web layer was written is **absent** from the web path. All three below have the same root cause (duplicated loop) and the same fix (roadmap #5 facade).

### 5.1 Web combat loop skips dying PCs — regression of fixed bug 1.5 — HIGH
`src/api/game_server.py:177` — `_process_combat_turns` does `if char.hp <= 0 or "dead" in char.conditions: end_turn(...)` for **every** combatant. An unconscious PC is `hp == 0`, `"unconscious"`, not `"dead"` (see `rules.apply_damage`, `rules.py:528`), so the web loop skips their turn every round. They never roll a death save, never die, never stabilize — the downed player is softlocked indefinitely. The CLI handles this in `SessionManager._handle_dying_player_turn` (auto-rolls a death save on the PC's turn); the web path has no equivalent. Fix: when the current combatant is a PC with `hp <= 0` and not `"stable"`, roll a death save (or surface it to the frontend) and then `end_turn`, exactly as the CLI does — skip only `"dead"` and downed monsters.

### 5.2 Web combat loop has no stalled-turn guard — regression of fixed bug 2.17 — MEDIUM/HIGH
`src/api/game_server.py:163-199` — if the LLM narrates a monster's turn but never calls `end_turn`, `_process_combat_turns` loops back with `current_combatant_id` unchanged and re-sends the **same** `turn_prompt` + monster prompt, calling the model again and again with no termination — an unbounded API-credit drain / hang. The CLI guards against this (`session.py:197-200`: "if combatant unchanged after the render, force `end_turn`"). The web loop needs the same force-advance.

### 5.3 Turn-scope protection is inert in the web path — regression of the bug 2.19 guard — MEDIUM
`GameSession.handle_player_input` (`game_server.py:63`) calls `self.dm.process_player_input` directly and **never** calls `set_turn_scope`, so the dispatcher runs at `_turn_scope = None` (unrestricted) for the entire web session. All the action-economy / turn-fast-forward guards (bug 2.19) that protect the CLI are disabled in the web UI: a single LLM response can chain `end_turn` across multiple combatants and desync `_process_combat_turns` (which assumes exactly one `end_turn` per monster prompt). The "API stays unrestricted" carve-out in 2.19 predates this per-turn web loop and is now actively harmful here. Fix: set the turn scope to the current combatant id before each turn's `handle_player_input`, mirroring `_process_and_render(..., turn_scope=current_id)`.

### 5.4 Minor / hygiene
- **Feature gap (not a divergence bug):** `GameSession.handle_command` supports only `save`/`quit`/`exit`/`recap`; the CLI has a much richer set (`/journal`, `/location`, `/help`, …) in `commands.py`. A shared command layer would close this too.
- `src/engine/economy.py` (buy/sell/craft, train-skill, resurrect — wired via the `buy_item`/`sell_item`/`craft_item`/`resurrect` tool branches) is absent from the architecture map in `CLAUDE.md`; add it under `src/engine/`.
- `_build_game_state` (`routes/session.py:35`) seeds quests only from `campaign.plot_hooks[:2]`; intentional? The CLI loader may use a different rule — worth confirming the two entry points build identical initial state (another argument for a shared builder).

**Complexity note:** `_route` in `tools.py` (a 900-line `match` over ~62 tools inside a 2033-line file) reads fine case-by-case, but the file conflates three concerns — schema definitions, the dispatcher, and engine-adjacent helpers (`_is_sneak_attack_eligible`, etc.). Splitting `ALL_TOOL_SCHEMAS` into `tools_schemas.py` and grouping the `match` arms into a few handler modules would make it navigable without changing behavior. Low priority; not a bug.

---

## 6. What's in good shape

- Engine/LLM separation is consistently enforced; tool dispatch error handling (`dispatch`'s KeyError → friendly error) is robust.
- Structured journal compression (per-location/per-NPC merge prompts, prune-after-success in `compress_if_needed`) is a thoughtful design — better than the flat-summary approach most projects use.
- Atomic save with `.bak` rotation and backup-fallback on load (`game_state.py:178-264`) is exactly right.
- NPC dialogue sub-sessions with information gating (`npc_dialogue.py` secret handling) are a nice touch.
- Test suite is fast (1s) and broad (366 tests); CI-ability is trivially there.
