# Design — Interactive Inventory & Character Management

*Status: proposal (2026-06-13). Supersedes the slash-command inventory in `commands.py`.*

> **As-built note (2026-06-14).** Phase 1 landed as a **controller façade over the
> legacy storage**, not the stored unified model this proposal originally sketched.
> The four legacy `Character` containers (`weapons`/`armor`/`shield`/`inventory`/
> `attuned_items`) remain the single authoritative source of truth; there is **no
> second persisted model and no save-schema change**. `src/models/items.py` is a thin
> presentation/DTO vocabulary (categories, slots, parsed consumable effect) and
> `InventoryController` reads the legacy containers, builds a unified view with stable
> transient ids, and translates actions back to legacy mutations. Rationale: AC/attack
> code (`rules.recalculate_ac`, the attack handler) and ~20 equipment/combat tests read
> `char.armor`/`char.shield`/`char.weapons` directly; a stored-model flip would have
> been a behavior change on combat-critical code for no user-visible gain. The façade
> delivers the same unified UX at far lower risk. The Layer-1 *model* and *migration*
> sections below describe the **original** plan and are retained for context — read them
> against this note. Layer 2 (the controller) is as-built.

## Goal

Make inventory and character management **interactive and intuitive in the terminal** — no memorized command vocabulary. Today everything is a slash command (`/inventory`, `/equip longsword 1d8 slashing`, …): the player must know the command *and* type item stats by hand, and `/inventory` doesn't even show gold or equipped gear. We replace that with **modal, keyboard-driven screens** you open with a single key and operate entirely by selection.

### Principles

1. **Zero memorization.** One hotkey opens a screen; everything else is arrow-key selection from menus that always show their own keybindings in a footer.
2. **Contextual actions.** Selecting a potion offers *Use / Drop / Give*; selecting a sword offers *Equip / Drop / Give*. Invalid actions never appear — you cannot "use" a sword.
3. **Self-documenting detail.** A live detail pane shows the selected item's description and stats, so there's no separate "examine" verb.
4. **No tokens, no waiting.** Management screens are 100% engine-side (local state edits via the controller). They make **zero LLM calls** — instant and free.
5. **One source of truth for two transports.** All logic lives in a transport-agnostic controller shared by the CLI screens and the future web UI, so the two cannot diverge (the lesson from the duplicated combat loop — see `codebase-review.md` §5).

---

## Architecture — three layers

```
src/models/items.py          # Layer 1: unified item + equipment model (Pydantic)
src/engine/inventory.py      # Layer 2: InventoryController — transport-agnostic verbs
src/interface/screens/       # Layer 3a: CLI interactive screens (Rich + readchar)
  menu.py                    #   reusable SelectList / ActionMenu primitives
  inventory_screen.py
  character_screen.py
src/api/... (web)            # Layer 3b: web view reuses Layer 2 verbatim
```

The View never mutates state directly. It calls the **controller**, gets a structured result, and re-renders. This is what keeps CLI and web in sync.

---

## Layer 1 — unified item model

Replace the four disconnected containers (`inventory: list[Item]`, `weapons: list[Weapon]`, `armor: Armor | None`, `shield: bool`, `attuned_items: list[MagicItem]`) with **one bag + explicit slots that reference items by id**.

```python
class ItemCategory(str, Enum):
    WEAPON = "weapon"; ARMOR = "armor"; SHIELD = "shield"
    CONSUMABLE = "consumable"; MAGIC = "magic"; GEAR = "gear"

class InventoryItem(BaseModel):
    id: str                          # stable uuid4 — identity is NOT the name
    name: str
    category: ItemCategory
    quantity: int = 1
    weight: float = 0.0
    description: str = ""
    # category-specific payload (only the relevant block is populated):
    weapon: WeaponStats | None = None      # damage_dice, damage_type, properties, range
    armor: ArmorStats | None = None        # base_ac, armor_type, stealth_disadv, str_req
    consumable: ConsumableEffect | None = None  # {"heal": "2d4+2"} | {"cast": "Fire Bolt"}
    magic: MagicProps | None = None        # bonus, rarity, requires_attunement, charges
    equippable_slot: Slot | None = None    # where it *can* go, if anywhere

class EquipmentSlots(BaseModel):
    main_hand: str | None = None     # -> InventoryItem.id
    off_hand: str | None = None      # weapon or shield
    armor: str | None = None
    attunement: list[str] = []       # <= 3 item ids

class Character(BaseModel):
    ...
    inventory: list[InventoryItem] = []
    equipment: EquipmentSlots = Field(default_factory=EquipmentSlots)
    gold: int = 0
```

**Why this shape**
- *Equip = move a reference into a slot.* You can only equip what you carry → closes the "mint stats from thin air" trust hole (`codebase-review.md` §2.11): the engine derives attack/AC from the slotted item's own stats, the LLM never re-supplies them.
- *Stable ids* fix name-string matching (`equip_weapon`/`remove_item` currently match on lowercased name — collisions, fuzzy LLM naming). Names become display-only.
- *Consumables become first-class* with an effect payload → a real `use_item` path instead of free-form `apply_healing`.
- AC/attack/encumbrance are **computed properties** over `equipment`, so there's no desync between "what I'm wearing" and "my AC".

**Migration:** save-schema bump (reuse the v2 pattern from history persistence). A loader migrates old saves: `weapons` → `WEAPON` items (the first becomes `main_hand`), `armor` → an `ARMOR` item in the `armor` slot, `shield: true` → a generic shield item in `off_hand`, `attuned_items` → `MAGIC` items listed in `equipment.attunement`, plain `Item`s → `GEAR`.

---

## Layer 2 — InventoryController (the shared brain)

Pure functions over `GameState`; no I/O, no rendering, fully unit-testable, reused by web.

```python
class InventoryController:
    def view(self, char_id) -> InventoryView          # grouped items, gold, weight/cap, slots, attune x/3
    def actions_for(self, char_id, item_id) -> list[ItemAction]   # CONTEXTUAL, valid-only
    def apply(self, char_id, action, item_id, **kw) -> ActionResult
```

`ItemAction` is an enum the View renders as a menu. **As built:** `UNEQUIP, USE, DROP, GIVE, SPLIT, EXAMINE` — there is no `EQUIP` action, because equipping a statless legacy `inventory` item isn't well-defined; equipping still flows through the dedicated `equip_*`/`attune_item` tools. `actions_for` is where intuition lives — it returns only what's legal for *this* item in *this* state (a potion → `EXAMINE/USE/DROP/GIVE/SPLIT`; an equipped sword → `EXAMINE/UNEQUIP/GIVE`; `GIVE` is absent when there's no second PC).

`apply` validates and mutates against the legacy containers: `USE` a healing potion (an `Item` whose `properties` hold `{"heal": "2d4+2"}`) → rolls the dice, calls `rules.apply_healing`, decrements via `GameState.remove_item`, removes at 0; `UNEQUIP` → move the weapon/armor/shield/attuned item back to `inventory` + `recalculate_ac`; `GIVE` → transfer between the two PCs (deep-copying inventory items so effect `properties` survive); `DROP` → remove. Each returns an `ActionResult` with a short narration string the View prints (and the web pushes as an event).

**Not yet wired (future phase):** the existing `add_item` / `remove_item` / `equip_*` / `attune_item` / `buy_item` / `sell_item` tool branches still mutate storage directly; routing them through the controller (so the LLM and player share one validation path) remains a follow-up. Today the controller is the player/UI-side seam; `/inventory` already renders its `view()`.

---

## Layer 3a — the CLI screens

### Entry: single-key hotkeys at the prompt

The exploration/combat prompt gains a discoverable hint line:

```
  Aldric  HP 24/24   Mara  HP 18/18            The Salt Quarter
  [i] inventory   [c] character   [j] journal   [/] commands

> _
```

Press `i` or `c` to open the corresponding screen. Slash commands stay as a scriptable/power-user fallback, but they're no longer how you discover anything.

### Inventory screen (`i`) — two-pane browser

```
┌─ Aldric — Inventory ──────────────────────────────┬─ Details ───────────────┐
│  Gold: 47 gp            Weight: 38 / 120 lb        │  Healing Potion          │
│                                                    │  Consumable · 0.5 lb     │
│    Longsword            equipped · main hand       │                          │
│    Chain Mail           equipped · armor           │  Restores 2d4+2 HP when  │
│  ▸ Healing Potion  x3                              │  drunk (an action).      │
│    Oil Flask       x2                              │                          │
│    Torch           x5                              │  Worth ~50 gp.           │
│    Rope (50 ft)                                    │                          │
│                                                    │                          │
│  [↑↓] move   [Enter] actions   [Tab] switch hero   [Esc] back to game        │
└────────────────────────────────────────────────────┴──────────────────────────┘
```

`Enter` on the selection opens a **contextual action menu** in place:

```
  Healing Potion x3 ─┐
    ▸ Use            │   ← only valid actions, from controller.actions_for()
      Drop           │
      Give to Mara   │
      Split stack    │
      Cancel         │
  ───────────────────┘
```

Choosing `Use` → controller applies it → toast under the list: *"Aldric drinks a Healing Potion — heals 9 HP (24/24). 2 remaining."* The list re-renders. Equipped items show an `Unequip`; carriable weapons/armor show `Equip`; everything shows `Drop`/`Give`. **Nothing to memorize — you see your options.**

`Tab` cycles the two player characters (header retitles). `Give to <other>` is the headline two-player affordance.

### Character screen (`c`) — sectioned sheet

Navigable sheet (Stats · Skills · Equipment · Spells), `←/→` or `Tab` switches sections, `↑↓` moves within. The **Equipment** section is interactive — selecting a slot lets you swap/unequip; it shares the same action menu. Adds what the current sheet omits: **gold, attunement slots (x/3), resistances/immunities, temp HP, equipped-vs-carried.** Stats/Skills/Spells are read-only inspection (casting still flows through narrative).

---

## Tech choice

**Recommended: Rich `Live` + `readchar`.** Build a small reusable menu engine (`screens/menu.py`: `SelectList`, `ActionMenu`) — `readchar` reads single keypresses (incl. arrows) cross-platform; a Rich `Live` region re-renders the panel on each keystroke. Reasons: Rich is already the core dependency and owns the theming, the footprint is one tiny dep (`readchar`), and it composes with the existing console rather than seizing the whole app.

**Alternative considered: Textual** (same authors as Rich, full TUI: widgets, mouse, focus). More polish and mouse support, but a heavyweight dependency and a different programming model (its own async event loop) that fights the existing synchronous `input()` + streaming-narrative loop. **Recommendation:** ship the screens on Rich+readchar now; revisit Textual only if a persistent full-screen dashboard becomes the goal. *(This is the one real fork — flag for sign-off before building.)*

Add to `pyproject.toml`: `readchar>=4.0` in core deps (it's ~tiny and pure-Python).

### Coexisting with the game loop — and not breaking headless mode

- **Modal overlay.** A screen runs on the **alternate screen buffer** (like `less`/`vim`): it suspends the game loop, takes the terminal, and on `Esc` restores the narrative exactly as it was. No scrollback pollution.
- **Pure engine, zero tokens.** Nothing in a screen calls the DM; all edits go through the controller. Free and instant.
- **TTY fallback (critical).** Raw-key reads require a real terminal. Guard every screen with `if not sys.stdin.isatty(): fall back to the printed command path`. This keeps the debug-agent harness, piped input, and CI working unchanged — they never enter interactive mode. (There is no `isatty` handling in the codebase today; this is new and load-bearing.)

---

## Web parity

The web UI renders the **same `InventoryController.view()`** as clickable slots + bag, and posts `apply(action, item_id)` over the existing WebSocket. Because Layer 2 is shared, an item-handling fix lands in both transports at once — exactly the divergence we want to avoid repeating.

---

## Phased implementation

1. **Controller façade + DTO layer** — ✅ **Phase 1 done (2026-06-14).** *(Built as a façade over legacy storage — see the as-built note up top. No stored unified model, no save-schema change.)*
   - `src/models/items.py` — lean DTO/vocabulary layer: `ItemCategory`/`Slot` enums, `ConsumableEffect`, `consumable_from_properties()` (parses a legacy `Item.properties` dict into an effect, or `None` for ordinary gear), `MAX_ATTUNEMENT = 3`.
   - `src/engine/inventory.py` — `InventoryController(game_state)` over the legacy containers: `view()` → `InventoryView` (gold, weight/capacity via `rules.encumbrance_status`, equipped slots, attunement x/3, items with stable ids like `i:healing potion`, `w:longsword`), contextual `actions_for()`, and `apply()` for UNEQUIP/USE/DROP/GIVE/SPLIT/EXAMINE. Stable ids are `f"{prefix}:{slug(name)}"` resolved back by prefix + lowercased name.
   - **`/inventory` (`commands.py`) now renders `controller.view()`** — gold, equipped slots, attunement, and usable-consumable tags are finally visible (the cheap display win from §5 of the old proposal).
   - Tests: `tests/test_items.py` (7) + `tests/test_inventory.py` (12). Full suite green at **432 passed, 5 skipped**.

2. **CLI menu engine** (`screens/menu.py`) — ✅ **done (2026-06-14).** Reusable `select(title, options)` over `MenuOption`s: cursor with ↑/↓ (or j/k), Enter selects, Esc backs out; renders transiently via Rich `Live` (no alternate-screen-buffer complexity). Key reading is injectable (`read_key`) so navigation is unit-tested without a TTY/`readchar`; `interactive_enabled()` is the guard. Styles are literal (not theme names) so it renders on any `Console`. `readchar>=4.0` added to base deps. Tests: `tests/test_menu.py` (8).
3. **Inventory & character screens** — ✅ **done (2026-06-14).**
   - `screens/inventory_screen.py`: pick item → contextual action menu from `actions_for` → `apply` → view re-renders. Opened by the bare hotkey **`i`** (also `inv`/`inventory`).
   - `screens/character_screen.py`: the full sheet rendered as the menu *header* (via the shared `cli.build_character_sheet`, also used by the static `/<name>` command), with actions below — **Manage inventory** (jumps into the inventory screen scoped to that PC), **Short rest** / **Long rest** (resolved engine-side via `engine/rest.py`, disabled in combat), **Switch character**. Opened by the bare hotkey **`c`** (also `char`/`character`).
   - Both are intercepted in exploration *and* combat loops (`session.py`) and fall back to the static render under piped stdin. The menu engine gained an optional `header` renderable to support the sheet-on-top layout.
4. **`use_item` + writer-tool routing** — controller path exists (`apply(USE)`) and the player can already use consumables via the `i` screen; still to do: expose `use_item` as an LLM tool and route the writer tools (`add_item`/`remove_item`/`equip_*`/`attune_item`/`buy_item`/`sell_item`) through the controller so the LLM and player share one validation path (also closes the §2.11 equip-trust-hole).
5. **Hotkey hints** at the prompt; demote slash commands to fallback. *(Partial: `/help` now lists `i`/`c` first.)*
6. **Web view** reuses Layer 2 (`InventoryController` + `InventoryView`).

Encumbrance: compute carry weight vs `STR×15`, **display and soft-warn** (header turns amber past capacity); don't hard-block. This finally gives the long-dead `weight`/`strength_requirement` fields a purpose (`codebase-review.md` §2.12).

### Testing
- Controller: unit tests for every `actions_for`/`apply` path and invariant (no negative quantities, AC recompute on unequip, give-between-PCs conservation, effect `properties` survive a transfer). ✅ done in `tests/test_inventory.py`.
- No migration tests needed — the façade reads existing storage, so old saves load unchanged.
- Menu/screen: navigation (down/up-wrap/cancel/skip-disabled), `interactive_enabled()` false under piped stdin, and a driven inventory-screen run that uses a potion (HP up, quantity down). ✅ done in `tests/test_menu.py`. The `_maybe_open_screen` hotkey path in `session.py` falls back to the static `/inventory` render when `interactive_enabled()` is false, so the headless harness and CI (piped stdin) are unaffected.
