# AI Dungeon Master

A Python CLI application that uses an LLM as a Dungeon Master for two-player local D&D 5e sessions. The core design principle: **the LLM is the creative brain, the Python engine is the rules arbiter**. The LLM narrates and interprets intent; it never computes numbers directly — it calls deterministic tool functions for all mechanical adjudication (dice rolls, HP tracking, spell slots, conditions, XP, etc.).

## Quickstart guide

I typically use deepseek since it is very cheap and good quality. For this first to [https://platform.deepseek.com/usage](https://platform.deepseek.com/usage) and create an API key.

```bash
export export DEEPSEEK_API_KEY="1234567890"

cd ai-dungeon-master

# (Optional) create a virtual environment
pip venv .venv
source .venv/bin/activate

# Install necessary packages
pip install .

# New game — prompts for character setup (create interactively / load from file / use defaults)
python main.py --new --provider deepseek
```

Have fun!

## Features

- **Full D&D 5e combat loop** — initiative, attack rolls, crits, death saves, conditions with duration tracking
- **Spell resolution** — slot management, damage spells, healing spells, save-or-suck effects
- **Character progression** — XP, level-ups with correct HP/spell slot/hit dice gains, ability score improvements
- **Resting** — short rest (spend hit dice) and long rest (full reset)
- **Session recap** — `/recap` generates a narrative chronicle of significant session events
- **Interactive character creation** — Rich CLI wizard for all 12 SRD classes with standard array stat assignment
- **Prompt caching** — stable system prompt prefix (rules + location + quests) is cached on Anthropic for token savings
- **Multi-backend LLM** — Anthropic (default), Gemini, Ollama (local), DeepSeek (V3 and R1 thinking)
- **Persistent saves** — autosave JSON after every session; fully resumable

## Requirements

- Python 3.12+
- An API key for your chosen provider

## Installation

```bash
git clone <repo>
cd ai-dungeon-master
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set your API key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
# or for other providers:
export DEEPSEEK_API_KEY=...
export GOOGLE_API_KEY=...
```

Ollama runs locally and requires no API key. Install it from [ollama.com](https://ollama.com), then pull a model before use:

```bash
ollama pull llama3.2
```

## Usage

```bash
# New game — prompts for character setup (create interactively / load from file / use defaults)
python main.py --new

# Resume from autosave
python main.py

# Resume from a specific save
python main.py --save saves/mysave.json

# Use a different LLM provider
python main.py --provider deepseek                             # DeepSeek V3 (non-thinking)
python main.py --provider deepseek --model deepseek-reasoner  # DeepSeek R1 (thinking)
python main.py --provider gemini
python main.py --provider ollama --model llama3.2

# Use a specific campaign
python main.py --new --campaign campaigns/shattered_crown.json
```

### In-game commands

| Input | Effect |
|---|---|
| Any text | Sent to the DM as a player action |
| `/recap` | Generate a narrative session recap |
| `quit` / `exit` | Save and quit |

## Architecture

```
main.py                     # Entry point, arg parsing, wiring
src/
  campaign/
    campaign_db.py          # CampaignData dataclass
    loader.py               # JSON campaign loading, SRD data caching
  dm/
    dungeon_master.py       # DungeonMaster — LLM loop with tool use
    context.py              # ContextManager — history, compression, prompt caching blocks
    prompts.py              # Static DM system prompt
    tools.py                # ALL_TOOL_SCHEMAS + ToolDispatcher (LLM → engine bridge)
    backends/               # Pluggable LLM backends
      base.py               # LLMBackend ABC
      anthropic_backend.py  # Anthropic (with prompt caching)
      gemini.py             # Google Gemini
      ollama.py             # Ollama (local models via OpenAI-compatible API)
      deepseek.py           # DeepSeek V3 / R1 (via OpenAI-compatible API)
  engine/
    game_state.py           # GameState — save/load, authoritative mutable state
    combat.py               # Initiative, attack rolls, combat resolution
    dice.py                 # Dice parser: "4d6kh3", "2d6+3", advantage/disadvantage
    rules.py                # ability_check, saving_throw, attack_roll, conditions
    rest.py                 # Short/long rest logic
    spells.py               # Spell resolution
    progression.py          # Spell slot tables, level-up logic, class templates
  interface/
    cli.py                  # Rich console rendering
    session.py              # SessionManager — main game loop, player input
    character_creation.py   # Interactive character creation wizard
  log/
    event_log.py            # Structured event history for context injection and recap
  models/
    character.py            # Character, AbilityScores, Weapon, Armor (Pydantic)
    combat.py               # CombatState, AttackResult, DiceResult (Pydantic)
    monster.py              # Monster (Pydantic)
    spells.py               # Spell (Pydantic)
    world.py                # WorldState, Location, Quest (Pydantic)
campaigns/
  shattered_crown.json      # Default campaign: "The Shattered Crown"
  test_characters.json      # Prebuilt level-3 characters (Aldric + Zara)
saves/
  autosave.json             # Default autosave location
tests/
  test_combat.py
  test_dice.py
  test_rules.py
  test_spells.py
```

## How the LLM–engine split works

The LLM never computes numbers. Every mechanical action goes through a tool call:

```
Player: "I attack the goblin with my longsword"
  → LLM calls: attack(attacker_id="aldric", target_id="goblin_1", weapon_name="Longsword")
  → Engine: rolls 1d20 + attack bonus vs AC, rolls 1d8+STR on hit, updates HP
  → Engine returns: {hits: true, roll: [14], damage: 9, hp_remaining: 3}
  → LLM narrates: "Aldric's blade bites into the goblin's shoulder..."
```

The engine is a set of pure deterministic functions in `src/engine/`. The LLM only ever sees results and narrates them.

## Adding a campaign

Campaigns are JSON files following the `CampaignData` schema in `src/campaign/campaign_db.py`. Place them in `campaigns/` and pass via `--campaign`:

```bash
python main.py --new --campaign campaigns/my_campaign.json
```

## Adding an LLM backend

1. Create `src/dm/backends/my_backend.py` implementing `LLMBackend` (see `base.py`)
2. Register it in `src/dm/backends/__init__.py`
3. Add `--provider my_backend` to the choices in `main.py`

## Development

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=src

# Fetch/update SRD data
python scripts/fetch_srd_data.py
```
