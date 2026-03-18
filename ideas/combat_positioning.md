# Combat Positioning System

## Goal

Add a 2D grid-based positioning system for combat. The engine handles all geometry
and pathfinding; the LLM only expresses high-level tactical intent (e.g. "move toward
hero_a"). The LLM never sees or reasons about coordinates — it receives a compact
pairwise distance matrix each turn.

---

## Architecture Overview

```
LLM (intent)  ──>  move_combatant tool  ──>  positioning engine  ──>  grid state
                                                     │
                                              distance matrix ──> injected into LLM context
                                              ASCII map       ──> rendered in CLI via Rich
```

---

## New Module: `src/engine/positioning.py`

Core engine for all spatial logic. All coordinates are in **feet** (multiples of 5).

### Data

Position stored on `Combatant` (in `src/models/combat.py`):

```python
class Combatant(BaseModel):
    ...
    position: tuple[int, int] | None = None  # (x, y) in feet, None = not placed
```

### Functions

```python
def distance(a: tuple[int, int], b: tuple[int, int]) -> float:
    """Euclidean distance between two grid positions (in feet)."""

def move_toward(
    combat: CombatState, character_id: str, target_id: str,
    desired_range: int | None = None,
) -> dict:
    """
    Move character toward target, spending movement_remaining.
    Stops at desired_range (default 5ft for melee) or when movement runs out.
    Returns: distance_moved, new distances to all combatants, movement_remaining,
             opportunity_attacks_provoked (list of enemy IDs).
    """

def move_away(
    combat: CombatState, character_id: str, target_id: str,
    game_state: GameState,
) -> dict:
    """
    Move character directly away from target, spending all remaining movement.
    Returns same shape as move_toward.
    """

def get_distance_matrix(combat: CombatState, game_state: GameState) -> dict:
    """
    Build compact pairwise distance summary for all living combatants.
    Returns dict with per-combatant distances and HP, suitable for
    injection into LLM context.
    """

def check_range(
    combat: CombatState, attacker_id: str, target_id: str,
    range_normal: int, range_long: int | None = None,
) -> dict:
    """
    Check if target is within weapon/spell range.
    Returns: in_range, current_distance, disadvantage (if in long range bracket).
    """

def place_combatants(
    combat: CombatState, game_state: GameState,
    player_ids: list[str], enemy_ids: list[str],
    layout: str = "face_to_face",
) -> None:
    """
    Auto-place combatants on the grid at combat start.
    Mutates combatant positions in-place.
    """

def threatened_enemies(
    combat: CombatState, character_id: str, game_state: GameState,
) -> list[str]:
    """
    Return IDs of enemies within melee threat range (5ft, or 10ft for reach).
    Used for opportunity attack detection during movement.
    """
```

### Movement Logic

- Straight-line movement (no obstacles initially).
- Snap to 5ft grid after moving.
- Deduct distance moved from `movement_remaining`.
- **Opportunity attacks**: if the mover leaves a square within 5ft of a hostile
  combatant (and doesn't end still within 5ft), flag that enemy as provoking
  an opportunity attack. Return `opportunity_attacks_provoked: [enemy_ids]` so
  the LLM can resolve reactions.

### Distance Calculation

Use Euclidean distance, rounded down to nearest 5ft for game purposes.
This is simpler than D&D's official diagonal rules but close enough for
simplified 5e.

---

## Auto-Placement Layouts

The `start_combat` tool gets an optional `layout` parameter. The engine maps
each layout to initial positions:

| Layout          | Description                                         | Typical gap |
|-----------------|-----------------------------------------------------|-------------|
| `face_to_face`  | PCs in a line, enemies in a parallel line opposite   | 30ft        |
| `ambush`        | Enemies start close, partially flanking              | 15ft        |
| `surrounded`    | Enemies encircle PCs                                 | 10-15ft     |
| `scattered`     | Everyone spread randomly across a wider area         | 40-60ft     |

Default: `face_to_face`. Combatants within each group are spaced 5ft apart
to avoid overlap.

---

## Tool Changes

### New Tool: `move_combatant`

```json
{
    "name": "move_combatant",
    "description": "Move a combatant on the battle grid. Specify intent (approach/flee/maintain_range) and a target — the engine handles pathing. Returns new distances and any opportunity attacks provoked.",
    "input_schema": {
        "type": "object",
        "properties": {
            "character_id": {"type": "string"},
            "intent": {
                "type": "string",
                "enum": ["approach", "flee", "maintain_range"],
                "description": "approach = get as close as possible, flee = move directly away, maintain_range = move to desired_range distance"
            },
            "target_id": {"type": "string", "description": "Move relative to this combatant"},
            "desired_range": {
                "type": "integer",
                "description": "Target distance in feet (used with maintain_range, default 5 for approach)"
            }
        },
        "required": ["character_id", "intent", "target_id"]
    }
}
```

**Returns:**
```json
{
    "success": true,
    "distance_moved": 25,
    "movement_remaining": 5,
    "distance_to_target": 5,
    "distances": {"hero_a": 5, "hero_b": 40, "goblin_2": 10},
    "opportunity_attacks_provoked": []
}
```

### Modified Tool: `start_combat`

Add optional `layout` field:

```json
"layout": {
    "type": "string",
    "enum": ["face_to_face", "ambush", "surrounded", "scattered"],
    "default": "face_to_face",
    "description": "Initial positioning layout for combatants"
}
```

Return value gains a `positions` summary (distance matrix, not coordinates).

### Modified Tools: `attack` and `cast_spell`

Add automatic range validation before resolving:

- **`attack`**: check weapon `range_normal` (melee default 5ft). If out of range,
  return `{"success": false, "error": "Target is 30ft away (melee range: 5ft). Move closer first.", "current_distance": 30}`.
  For ranged weapons in long range bracket, auto-apply disadvantage.
- **`cast_spell`**: check spell range from SRD data. Return error with distance
  if out of range.

### Modified Tool: `end_turn`

Return value includes the distance matrix for the next combatant's perspective,
so the LLM immediately has tactical context for the next turn.

---

## Tactical Summary (LLM Context Injection)

After each turn (in `end_turn` result) and at combat start, include a compact
text block:

```
── Round 2 · Goblin_1's turn (30ft movement) ──
Goblin_1 (5/7 HP) → Hero_A 25ft · Hero_B 40ft · Goblin_2 10ft
Hero_A  (24/30 HP) → Hero_B 15ft · Goblin_2 35ft
Hero_B  (18/22 HP) → Goblin_2 30ft
```

This is ~4 lines regardless of combatant count (triangular matrix). The LLM gets
pairwise distances and HP — exactly what a DM thinks in terms of.

The context manager (`src/dm/context.py`) or `end_turn` tool result should include
this block. Prefer returning it in the tool result to keep it simple.

---

## CLI Visualization

Render an ASCII grid in a Rich panel during combat. Updated after every action
that changes positions.

```
┌─── Battle Map (Round 2) ──────────────┐
│ · · · · · · · · · · · · ·             │
│ · · · · · · · · · · · · ·             │
│ · · · · G2· · · · · · · ·             │
│ · · · · · · · · · · · · ·             │
│ · · G1· · · · · · · · · ·             │
│ · · P1· · · P2· · · · · ·             │
│ · · · · · · · · · · · · ·             │
│                                       │
│ P1=Aldric  P2=Lyra  G1=Goblin  G2=Orc│
└───────────────────────────────────────┘
```

- Only render the bounding box around combatants (+ margin), not a fixed-size grid.
- Token labels: `P1`, `P2` for players, first letter + number for monsters.
- Legend below the grid.
- This is **CLI-only** — the LLM never sees this, only the distance matrix.

---

## Implementation Plan

### Step 1: Model changes
- Add `position: tuple[int, int] | None = None` to `Combatant` in `src/models/combat.py`.

### Step 2: Positioning engine
- Create `src/engine/positioning.py` with all spatial functions:
  `distance`, `move_toward`, `move_away`, `check_range`, `place_combatants`,
  `get_distance_matrix`, `threatened_enemies`.

### Step 3: Wire into combat flow
- `start_combat` in `src/engine/combat.py`: call `place_combatants` after
  initiative rolls, accept `layout` parameter.
- `end_turn`: include distance matrix in return value.

### Step 4: New tool + modify existing tools
- Add `move_combatant` tool schema and dispatch in `src/dm/tools.py`.
- Add range checks to `attack` and `cast_spell` dispatch handlers.
- Add `layout` param to `start_combat` schema.

### Step 5: CLI map renderer
- Add `render_combat_map` to `src/interface/cli.py` using Rich.
- Call it from session after any combat action that changes positions.

### Step 6: Tests
- Unit tests for all positioning functions (distance, movement, placement,
  range checks, opportunity attacks).
- Integration tests: full combat flow with positioning.

---

## What This Does NOT Include (Possible Future Work)

- **Obstacles / terrain**: all movement is open-field straight-line.
- **Difficult terrain**: no half-speed squares.
- **Cover**: no AC bonuses from partial cover.
- **Diagonal movement penalties**: Euclidean distance, no 5-10-5 alternation.
- **AoE geometry**: cone/sphere/line templates for spells (can be added per-spell later).
- **Flanking**: optional rule, not in base 5e SRD.
