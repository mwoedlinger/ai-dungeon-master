# AI Dungeon Master

A CLI D&D 5e game powered by LLMs. The LLM narrates and voices NPCs; a Python engine handles all the rules — dice rolls, HP, spell slots, combat, conditions, leveling. Two-player local co-op.

## Quickstart

I typically use DeepSeek since it's cheap and good quality. Get an API key at [platform.deepseek.com](https://platform.deepseek.com/usage).

```bash
export DEEPSEEK_API_KEY="your-key-here"

cd ai-dungeon-master

# Create a virtual environment and install
python -m venv .venv
source .venv/bin/activate
pip install .

# Fetch SRD data (monsters, spells, equipment — needed once)
python scripts/fetch_srd_data.py

# Start a new game
python main.py --new --provider deepseek
```

The game will prompt you to create characters interactively, load them from a file, or use defaults. Then you're in.

### Other providers

```bash
# Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."
python main.py --new --provider anthropic

# Google Gemini
export GOOGLE_API_KEY="..."
python main.py --new --provider gemini

# Ollama (local, no API key)
ollama pull llama3.2
python main.py --new --provider ollama --model llama3.2
```

### Resuming a game

```bash
# Resume from autosave
python main.py --provider deepseek

# Resume from a specific save
python main.py --save saves/mysave.json --provider deepseek
```

## In-game commands

| Command | Effect |
|---------|--------|
| Any text | Sent to the DM as a player action |
| `/help` | List all commands |
| `/save` | Save the game |
| `/quit` | Save and quit |
| `/exit` | Quit without saving |
| `/<name>` | Show character sheet (e.g. `/aldric`) |
| `/status` | Party HP, AC, conditions |
| `/map` | Current location and exits |
| `/quests` | Quest log |
| `/inventory` | Party inventory |
| `/journal` | World journal — story summary, NPC attitudes, events |
| `/location` | Detailed location description (LLM-generated, cached) |
| `/recap` | Narrative session recap |

## Generating campaigns

Instead of writing campaign JSON by hand, you can generate one from a theme:

```bash
python scripts/generate_campaign.py "a monastery where the monks have forgotten what they worship" \
  --provider deepseek -v
```

This runs a multi-pass pipeline that builds locations, NPCs, factions, plot hooks, and encounters. See [scripts/README.md](scripts/README.md) for details.

## How it works

The LLM never does math. Every mechanical action goes through a tool call:

```
Player: "I attack the goblin with my longsword"
  -> LLM calls: attack(attacker_id="aldric", target_id="goblin_1", weapon_name="Longsword")
  -> Engine: rolls 1d20+4 vs AC 15, rolls 1d8+3 on hit, updates HP
  -> Returns: {hits: true, damage: 9, hp_remaining: 3}
  -> LLM narrates: "Aldric's blade bites into the goblin's shoulder..."
```

All game state (HP, inventory, quests, NPC attitudes) is persisted in save files. A world journal tracks story events across sessions so the DM remembers what happened.

## Development

```bash
pytest                          # Run tests
pytest --cov=src                # With coverage
python scripts/fetch_srd_data.py  # Fetch/update SRD data
```

Requires Python 3.12+.
