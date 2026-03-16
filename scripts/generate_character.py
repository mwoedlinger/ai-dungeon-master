"""Generate D&D characters from a concept using an LLM backend.

LLM provides creative choices (name, race, class, personality, ability priority).
Python deterministically calculates all mechanical stats.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Allow running as script from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.dm.backends import PROVIDERS, create_backend
from src.engine.progression import ALIGNMENTS, BACKGROUNDS, CLASS_TEMPLATES, RACES, get_spell_slots_for_level
from src.engine.rules import proficiency_bonus_for_level, xp_for_level
from src.models.character import AbilityScores, Armor, Character, Item, Weapon

STANDARD_ARRAY = [15, 14, 13, 12, 10, 8]
ABILITIES = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]

SYSTEM_PROMPT = """\
You are a D&D 5e character designer. Generate character SKETCHES as JSON — creative choices only.
Python will calculate all mechanical stats (HP, AC, spell slots, etc.).

Output a JSON object with this EXACT schema:

{{
  "characters": [
    {{
      "name": "<full character name>",
      "race": "<one of: {races}>",
      "class_name": "<one of: {classes}>",
      "subclass": "<appropriate subclass for the class, or null>",
      "background": "<one of: {backgrounds}>",
      "alignment": "<one of: {alignments}>",
      "personality_traits": "<1-2 personality traits>",
      "ideals": "<what this character believes in>",
      "bonds": "<what ties this character to the world>",
      "flaws": "<a weakness or vice>",
      "backstory": "<2-3 sentences of backstory>",
      "ability_priority": ["<six abilities from highest to lowest priority: STR, DEX, CON, INT, WIS, CHA>"],
      "skill_choices": ["<exactly 2 skills from the class skill list>"],
      "extra_spells": ["<0-3 additional spells appropriate for class/level, beyond starting spells>"],
      "inventory_flavor": [
        {{"name": "<item name>", "description": "<brief description>"}}
      ]
    }}
  ]
}}

RULES:
- Generate exactly {count} character(s).
- ability_priority must list ALL SIX abilities in order from most to least important.
- skill_choices must be valid skills for the chosen class.
- extra_spells should only be provided for spellcasting classes, and should be level-appropriate.
- inventory_flavor: 2-4 flavorful personal items (not weapons/armor — those come from class).
- Output ONLY the JSON object — no markdown fences, no commentary."""


def extract_json(text: str) -> dict:
    """Parse JSON from LLM output, handling markdown fences."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return json.loads(text[start : end + 1])
    raise ValueError("Could not extract JSON from LLM response")


def compute_ability_scores(priority: list[str]) -> AbilityScores:
    """Map standard array to abilities based on priority ordering."""
    # Validate and deduplicate, falling back to order for missing
    seen: set[str] = set()
    clean: list[str] = []
    for ab in priority:
        ab = ab.upper()
        if ab in ABILITIES and ab not in seen:
            clean.append(ab)
            seen.add(ab)
    # Fill any missing abilities
    for ab in ABILITIES:
        if ab not in seen:
            clean.append(ab)
    mapping = {ab: score for ab, score in zip(clean, STANDARD_ARRAY)}
    return AbilityScores(**mapping)


def compute_hp(level: int, hit_die: str, con_mod: int) -> int:
    """Compute HP: level 1 = max die + CON mod; levels 2+ = floor(die/2)+1 + CON mod each."""
    die_sides = int(hit_die[1:])
    hp = die_sides + con_mod  # Level 1
    per_level = max(1, (die_sides // 2 + 1) + con_mod)
    hp += per_level * (level - 1)
    return max(1, hp)


def compute_ac(template: dict, ability_scores: AbilityScores, class_name: str) -> tuple[int, Armor | None]:
    """Compute AC from class starting armor and ability scores."""
    armor_data = template.get("starting_armor")
    if armor_data is None:
        # Unarmored — Monk or Sorcerer/Wizard
        dex_mod = ability_scores.modifier("DEX")
        if class_name == "Monk":
            ac = 10 + dex_mod + ability_scores.modifier("WIS")
        elif class_name == "Barbarian":
            ac = 10 + dex_mod + ability_scores.modifier("CON")
        else:
            ac = 10 + dex_mod
        return ac, None

    armor = Armor(**armor_data)
    dex_mod = ability_scores.modifier("DEX")
    if armor.armor_type == "light":
        ac = armor.base_ac + dex_mod
    elif armor.armor_type == "medium":
        ac = armor.base_ac + min(2, dex_mod)
    else:  # heavy
        ac = armor.base_ac
    return ac, armor


def build_character(sketch: dict, level: int) -> Character:
    """Build a full Character from an LLM sketch + deterministic calculations."""
    class_name = sketch["class_name"]
    template = CLASS_TEMPLATES.get(class_name)
    if template is None:
        raise ValueError(f"Unknown class: {class_name!r}. Valid: {list(CLASS_TEMPLATES)}")

    # Ability scores from priority
    ability_scores = compute_ability_scores(sketch.get("ability_priority", template["primary"]))
    con_mod = ability_scores.modifier("CON")

    # HP
    hit_die = template["hit_die"]
    hp = compute_hp(level, hit_die, con_mod)

    # AC
    ac, armor = compute_ac(template, ability_scores, class_name)

    # Weapons
    weapons = [Weapon(**w) for w in template["starting_weapons"]]

    # Spell slots
    spell_slots = get_spell_slots_for_level(class_name, level)

    # Known spells: template starting + LLM extras (deduplicated)
    known_spells = list(template["starting_spells"])
    for spell in sketch.get("extra_spells", []):
        if spell not in known_spells:
            known_spells.append(spell)

    # Skills: validate against class options, fallback to first available
    valid_skills = set(template["skill_options"])
    skills: list[str] = []
    for s in sketch.get("skill_choices", []):
        if s in valid_skills and s not in skills:
            skills.append(s)
    # Fill to 2 if LLM gave invalid choices
    for s in template["skill_options"]:
        if len(skills) >= 2:
            break
        if s not in skills:
            skills.append(s)

    # Inventory from LLM flavor items + standard adventuring gear
    inventory = [Item(name=it["name"], description=it.get("description", ""))
                 for it in sketch.get("inventory_flavor", [])]
    inventory.extend([
        Item(name="Healing Potion", description="Restores 2d4+2 HP", quantity=2, weight=0.5),
        Item(name="Rations", description="One day of food", quantity=5, weight=2.0),
        Item(name="Gold Pieces", quantity=25, weight=0.02),
    ])

    # ID from name
    char_id = re.sub(r"[^a-z0-9]+", "_", sketch["name"].lower()).strip("_")
    # Use first name only for brevity
    first_word = char_id.split("_")[0]

    prof_bonus = proficiency_bonus_for_level(level)

    # Background — validate against known backgrounds, fallback to Folk Hero
    background = sketch.get("background", "Folk Hero")
    if background not in BACKGROUNDS:
        background = "Folk Hero"
    bg_skills = BACKGROUNDS[background]["skill_proficiencies"]
    # Add background skills (deduplicated)
    for s in bg_skills:
        if s not in skills:
            skills.append(s)

    return Character(
        id=first_word,
        name=sketch["name"],
        race=sketch.get("race", "Human"),
        class_name=class_name,
        subclass=sketch.get("subclass"),
        level=level,
        xp=xp_for_level(level),
        ability_scores=ability_scores,
        hp=hp,
        max_hp=hp,
        ac=ac,
        proficiency_bonus=prof_bonus,
        skill_proficiencies=skills,
        weapon_proficiencies=template["weapon_proficiencies"],
        armor_proficiencies=template["armor_proficiencies"],
        saving_throw_proficiencies=template["saves"],
        spell_slots=dict(spell_slots),
        max_spell_slots=dict(spell_slots),
        spellcasting_ability=template["spellcasting_ability"],
        known_spells=known_spells,
        hit_dice_remaining=level,
        hit_die_type=hit_die,
        class_resources=dict(template.get("class_resources", {})),
        weapons=weapons,
        armor=armor,
        inventory=inventory,
        background=background,
        alignment=sketch.get("alignment"),
        personality_traits=sketch.get("personality_traits"),
        ideals=sketch.get("ideals"),
        bonds=sketch.get("bonds"),
        flaws=sketch.get("flaws"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate D&D characters from a concept")
    parser.add_argument("concept", help="Character concept description")
    parser.add_argument("--provider", default="anthropic", choices=PROVIDERS)
    parser.add_argument("--model", default=None, help="Override model name")
    parser.add_argument("--output", default="campaigns/generated_characters.json")
    parser.add_argument("--level", type=int, default=3, help="Character level (default: 3)")
    parser.add_argument("--count", type=int, default=None,
                        help="Number of characters (default: inferred from concept)")
    args = parser.parse_args()

    count = args.count or "the number implied by the concept (default to 2 if unclear)"

    backend = create_backend(args.provider, args.model)
    system = SYSTEM_PROMPT.format(
        races=", ".join(RACES),
        classes=", ".join(CLASS_TEMPLATES),
        backgrounds=", ".join(sorted(BACKGROUNDS)),
        alignments=", ".join(ALIGNMENTS),
        count=count,
    )
    user_msg = {
        "role": "user",
        "content": f"Generate characters for this concept: {args.concept}\nCharacter level: {args.level}",
    }

    print(f"Generating characters with {args.provider}...")
    response = backend.compress(system, [user_msg], max_tokens=4096)

    data = extract_json(response)
    sketches = data.get("characters", [])
    if not sketches:
        print("Error: LLM returned no characters", file=sys.stderr)
        sys.exit(1)

    characters = []
    for sketch in sketches:
        try:
            char = build_character(sketch, args.level)
            characters.append(char)
            print(f"  Built: {char.name} ({char.race} {char.class_name} {char.level})")
        except Exception as e:
            print(f"  Warning: Failed to build '{sketch.get('name', '?')}': {e}", file=sys.stderr)

    if not characters:
        print("Error: No characters could be built", file=sys.stderr)
        sys.exit(1)

    output = {"characters": [c.model_dump() for c in characters]}
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2) + "\n")
    print(f"Wrote {len(characters)} character(s) to {out_path}")


if __name__ == "__main__":
    main()
