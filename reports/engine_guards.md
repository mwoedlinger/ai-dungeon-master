# engine_guards

---

## Run — 2026-06-12 07:50

**Status:** PASS  
**Failures:** 0  
**Warnings:** 0

Turns: 19 setup + 0 AI = 19 total  
Cost: free (engine-only, no LLM)  
Initial: `location=thornfield, combat_active=False, hp_summary={'Aldric Stonemantle': '28/28', 'Zara Moonwhisper': '19/19'}`  
Final: `location=thornfield, combat_active=False, hp_summary={'Aldric Stonemantle': '28/28', 'Zara Moonwhisper': '19/19'}`

<details><summary>Turn log</summary>

#### [+] engine 1

**Input:** nonexistent_tool()

**Output:**
rejected: Unknown tool: 'nonexistent_tool'

#### [+] engine 2

**Input:** attack(attacker_id='nobody', target_id='aldric', weapon_name='Longsword')

**Output:**
rejected: Character/object not found: "Character not found: 'nobody'"

#### [+] engine 3

**Input:** attack(attacker_id='aldric', target_id='zara', weapon_name='Excalibur')

**Output:**
rejected: Aldric Stonemantle does not have an attack named 'Excalibur'. Available: ['Longsword']

#### [+] engine 4

**Input:** apply_damage(target_id='aldric', amount=-10, damage_type='fire')

**Output:**
rejected: Damage amount must be non-negative.

#### [+] engine 5

**Input:** apply_healing(target_id='aldric', amount=-10)

**Output:**
rejected: Healing amount must be non-negative.

#### [+] engine 6

**Input:** cast_spell(caster_id='zara', spell_name='Summon Tarrasque', target_ids=[])

**Output:**
rejected: Spell 'Summon Tarrasque' not found in SRD data.

#### [+] engine 7

**Input:** cast_spell(caster_id='zara', spell_name='Fireball', target_ids=['aldric'], spell_level=1)

**Output:**
rejected: Fireball is a level 3 spell and cannot be cast with a level 1 slot.

#### [+] engine 8

**Input:** cast_spell(caster_id='aldric', spell_name='Fireball', target_ids=['zara'])

**Output:**
rejected: No level 3 spell slots remaining for Aldric Stonemantle.

#### [+] engine 9

**Input:** ability_check(character_id='aldric', ability='LUCK', dc=10)

**Output:**
rejected: Unknown ability 'LUCK'. Valid: STR, DEX, CON, INT, WIS, CHA.

#### [+] engine 10

**Input:** saving_throw(character_id='aldric', ability='SWAG', dc=10)

**Output:**
rejected: Unknown ability 'SWAG'. Valid: STR, DEX, CON, INT, WIS, CHA.

#### [x] engine 11

**Input:** ability_check(character_id='aldric', ability='str', dc=10)

**Output:**
rejected: 

#### [+] engine 12

**Input:** end_turn()

**Output:**
rejected: No active combat.

#### [+] engine 13

**Input:** end_combat(xp_awarded=500)

**Output:**
rejected: No active combat to end.

#### [+] engine 14

**Input:** death_save(character_id='aldric')

**Output:**
rejected: Aldric Stonemantle is not unconscious.

#### [+] engine 15

**Input:** attune_item(character_id='aldric', item_name='Ring of Wishes', item_type='ring', bonus=3)

**Output:**
rejected: Aldric Stonemantle does not possess 'Ring of Wishes'. Add it first via claim_treasure or add_item, t

#### [+] engine 16

**Input:** remove_item(character_id='aldric', item_name='Moon Cheese', quantity=3)

**Output:**
rejected: Aldric Stonemantle does not have 'Moon Cheese'.

#### [+] engine 17

**Input:** use_lay_on_hands(character_id='aldric', target_id='zara', amount=10)

**Output:**
rejected: Only Paladins can use Lay on Hands.

#### [+] engine 18

**Input:** apply_healing(target_id='zara', amount=10)

**Output:**
rejected: Zara Moonwhisper is dead — healing has no effect (resurrection magic required).

#### [+] engine 19

**Input:** take_long_rest(character_id='zara')

**Output:**
rejected: Zara Moonwhisper is dead and cannot benefit from a rest. Use resurrect_character instead.

</details>

---

## Run — 2026-06-12 07:50

**Status:** PASS  
**Failures:** 0  
**Warnings:** 0

Turns: 19 setup + 0 AI = 19 total  
Cost: free (engine-only, no LLM)  
Initial: `location=thornfield, combat_active=False, hp_summary={'Aldric Stonemantle': '28/28', 'Zara Moonwhisper': '19/19'}`  
Final: `location=thornfield, combat_active=False, hp_summary={'Aldric Stonemantle': '28/28', 'Zara Moonwhisper': '19/19'}`

<details><summary>Turn log</summary>

#### [+] engine 1

**Input:** nonexistent_tool()

**Output:**
rejected: Unknown tool: 'nonexistent_tool'

#### [+] engine 2

**Input:** attack(attacker_id='nobody', target_id='aldric', weapon_name='Longsword')

**Output:**
rejected: Character/object not found: "Character not found: 'nobody'"

#### [+] engine 3

**Input:** attack(attacker_id='aldric', target_id='zara', weapon_name='Excalibur')

**Output:**
rejected: Aldric Stonemantle does not have an attack named 'Excalibur'. Available: ['Longsword']

#### [+] engine 4

**Input:** apply_damage(target_id='aldric', amount=-10, damage_type='fire')

**Output:**
rejected: Damage amount must be non-negative.

#### [+] engine 5

**Input:** apply_healing(target_id='aldric', amount=-10)

**Output:**
rejected: Healing amount must be non-negative.

#### [+] engine 6

**Input:** cast_spell(caster_id='zara', spell_name='Summon Tarrasque', target_ids=[])

**Output:**
rejected: Spell 'Summon Tarrasque' not found in SRD data.

#### [+] engine 7

**Input:** cast_spell(caster_id='zara', spell_name='Fireball', target_ids=['aldric'], spell_level=1)

**Output:**
rejected: Fireball is a level 3 spell and cannot be cast with a level 1 slot.

#### [+] engine 8

**Input:** cast_spell(caster_id='aldric', spell_name='Fireball', target_ids=['zara'])

**Output:**
rejected: No level 3 spell slots remaining for Aldric Stonemantle.

#### [+] engine 9

**Input:** ability_check(character_id='aldric', ability='LUCK', dc=10)

**Output:**
rejected: Unknown ability 'LUCK'. Valid: STR, DEX, CON, INT, WIS, CHA.

#### [+] engine 10

**Input:** saving_throw(character_id='aldric', ability='SWAG', dc=10)

**Output:**
rejected: Unknown ability 'SWAG'. Valid: STR, DEX, CON, INT, WIS, CHA.

#### [x] engine 11

**Input:** ability_check(character_id='aldric', ability='str', dc=10)

**Output:**
rejected: 

#### [+] engine 12

**Input:** end_turn()

**Output:**
rejected: No active combat.

#### [+] engine 13

**Input:** end_combat(xp_awarded=500)

**Output:**
rejected: No active combat to end.

#### [+] engine 14

**Input:** death_save(character_id='aldric')

**Output:**
rejected: Aldric Stonemantle is not unconscious.

#### [+] engine 15

**Input:** attune_item(character_id='aldric', item_name='Ring of Wishes', item_type='ring', bonus=3)

**Output:**
rejected: Aldric Stonemantle does not possess 'Ring of Wishes'. Add it first via claim_treasure or add_item, t

#### [+] engine 16

**Input:** remove_item(character_id='aldric', item_name='Moon Cheese', quantity=3)

**Output:**
rejected: Aldric Stonemantle does not have 'Moon Cheese'.

#### [+] engine 17

**Input:** use_lay_on_hands(character_id='aldric', target_id='zara', amount=10)

**Output:**
rejected: Only Paladins can use Lay on Hands.

#### [+] engine 18

**Input:** apply_healing(target_id='zara', amount=10)

**Output:**
rejected: Zara Moonwhisper is dead — healing has no effect (resurrection magic required).

#### [+] engine 19

**Input:** take_long_rest(character_id='zara')

**Output:**
rejected: Zara Moonwhisper is dead and cannot benefit from a rest. Use resurrect_character instead.

</details>

---

## Run — 2026-06-12 07:50

**Status:** PASS  
**Failures:** 0  
**Warnings:** 0

Turns: 19 setup + 0 AI = 19 total  
Cost: free (engine-only, no LLM)  
Initial: `location=thornfield, combat_active=False, hp_summary={'Aldric Stonemantle': '28/28', 'Zara Moonwhisper': '19/19'}`  
Final: `location=thornfield, combat_active=False, hp_summary={'Aldric Stonemantle': '28/28', 'Zara Moonwhisper': '19/19'}`

<details><summary>Turn log</summary>

#### [+] engine 1

**Input:** nonexistent_tool()

**Output:**
rejected: Unknown tool: 'nonexistent_tool'

#### [+] engine 2

**Input:** attack(attacker_id='nobody', target_id='aldric', weapon_name='Longsword')

**Output:**
rejected: Character/object not found: "Character not found: 'nobody'"

#### [+] engine 3

**Input:** attack(attacker_id='aldric', target_id='zara', weapon_name='Excalibur')

**Output:**
rejected: Aldric Stonemantle does not have an attack named 'Excalibur'. Available: ['Longsword']

#### [+] engine 4

**Input:** apply_damage(target_id='aldric', amount=-10, damage_type='fire')

**Output:**
rejected: Damage amount must be non-negative.

#### [+] engine 5

**Input:** apply_healing(target_id='aldric', amount=-10)

**Output:**
rejected: Healing amount must be non-negative.

#### [+] engine 6

**Input:** cast_spell(caster_id='zara', spell_name='Summon Tarrasque', target_ids=[])

**Output:**
rejected: Spell 'Summon Tarrasque' not found in SRD data.

#### [+] engine 7

**Input:** cast_spell(caster_id='zara', spell_name='Fireball', target_ids=['aldric'], spell_level=1)

**Output:**
rejected: Fireball is a level 3 spell and cannot be cast with a level 1 slot.

#### [+] engine 8

**Input:** cast_spell(caster_id='aldric', spell_name='Fireball', target_ids=['zara'])

**Output:**
rejected: No level 3 spell slots remaining for Aldric Stonemantle.

#### [+] engine 9

**Input:** ability_check(character_id='aldric', ability='LUCK', dc=10)

**Output:**
rejected: Unknown ability 'LUCK'. Valid: STR, DEX, CON, INT, WIS, CHA.

#### [+] engine 10

**Input:** saving_throw(character_id='aldric', ability='SWAG', dc=10)

**Output:**
rejected: Unknown ability 'SWAG'. Valid: STR, DEX, CON, INT, WIS, CHA.

#### [x] engine 11

**Input:** ability_check(character_id='aldric', ability='str', dc=10)

**Output:**
rejected: 

#### [+] engine 12

**Input:** end_turn()

**Output:**
rejected: No active combat.

#### [+] engine 13

**Input:** end_combat(xp_awarded=500)

**Output:**
rejected: No active combat to end.

#### [+] engine 14

**Input:** death_save(character_id='aldric')

**Output:**
rejected: Aldric Stonemantle is not unconscious.

#### [+] engine 15

**Input:** attune_item(character_id='aldric', item_name='Ring of Wishes', item_type='ring', bonus=3)

**Output:**
rejected: Aldric Stonemantle does not possess 'Ring of Wishes'. Add it first via claim_treasure or add_item, t

#### [+] engine 16

**Input:** remove_item(character_id='aldric', item_name='Moon Cheese', quantity=3)

**Output:**
rejected: Aldric Stonemantle does not have 'Moon Cheese'.

#### [+] engine 17

**Input:** use_lay_on_hands(character_id='aldric', target_id='zara', amount=10)

**Output:**
rejected: Only Paladins can use Lay on Hands.

#### [+] engine 18

**Input:** apply_healing(target_id='zara', amount=10)

**Output:**
rejected: Zara Moonwhisper is dead — healing has no effect (resurrection magic required).

#### [+] engine 19

**Input:** take_long_rest(character_id='zara')

**Output:**
rejected: Zara Moonwhisper is dead and cannot benefit from a rest. Use resurrect_character instead.

</details>

