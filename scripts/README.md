# Scripts

## generate_campaign.py

Generates a complete campaign from a one-line theme using a multi-pass LLM pipeline.

### Usage

```bash
python scripts/generate_campaign.py "a coastal city where the tides are wrong" --provider deepseek -v
```

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `--provider` | `anthropic` | LLM provider |
| `--model` | per-provider | Model override |
| `--output` | auto from title | Output path |
| `--locations` | `8` | Number of locations |
| `--npcs` | `6` | Number of NPCs |
| `--hooks` | `4` | Number of plot hooks |
| `--cr-range` | `0-5` | Monster CR range (e.g. `1-8` for higher-level campaigns) |
| `-v` | off | Verbose — show progress for each step |

### How it works

The generator runs 5 sequential LLM passes, each building on the previous output:

1. **Concept** — Central mystery, three-layer mystery structure (surface / intermediate / deep truth), thematic motifs, tone.
2. **Locations** — Connected location graph. Each location gets a narrative role (introduction, investigation, revelation, etc.) and sensory atmosphere. Validated for connectivity.
3. **NPCs & Factions** — Characters built from randomly selected archetypes to ensure variety. Some NPCs are straightforward and warm, others are guarded, unreliable, or haunted. Not everyone has a dark secret.
4. **Plot Hooks** — Interconnected quest web (hooks link to other hooks). Includes a suggested revelation sequence for pacing.
5. **Encounters** — One LLM call per location. Picks from the full SRD monster database (334 creatures), filtered by CR range and matched thematically to each location.

After all passes, a validation step checks cross-references (NPC locations, hook NPCs, monster IDs) and auto-fixes common issues. The output is a standard campaign JSON loadable with `python main.py --campaign campaigns/<name>.json`.

### Examples

```bash
# Quick 4-location one-shot
python scripts/generate_campaign.py "a haunted lighthouse" --locations 4 --npcs 3 --hooks 2

# Larger campaign with higher-level monsters
python scripts/generate_campaign.py "a city built on the back of a sleeping god" \
  --locations 12 --npcs 10 --hooks 6 --cr-range 3-12

# Using a local model
python scripts/generate_campaign.py "a forest that remembers" --provider ollama --model llama3.2
```

## fetch_srd_data.py

Downloads D&D 5e SRD data from [dnd5eapi.co](https://www.dnd5eapi.co) and caches it locally. Run this once before playing.

```bash
python scripts/fetch_srd_data.py
```

Downloads monsters, spells, equipment, classes, races, conditions, skills, and features. Cached in `src/data/srd/cache/`. Skips already-downloaded entries on re-run.

## generate_character.py

Generates a character JSON file via LLM. Used less often since the game has interactive character creation built in.
