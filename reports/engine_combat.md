# engine_combat

---

## Run — 2026-06-12 07:50

**Status:** PASS  
**Failures:** 0  
**Warnings:** 0

Turns: 52 setup + 0 AI = 52 total  
Cost: free (engine-only, no LLM)  
Initial: `location=thornfield, combat_active=False, hp_summary={'Aldric Stonemantle': '28/28', 'Zara Moonwhisper': '19/19'}`  
Final: `location=thornfield, combat_active=False, hp_summary={'Aldric Stonemantle': '28/28', 'Zara Moonwhisper': '8/19'}`

<details><summary>Turn log</summary>

#### [+] engine 1

**Input:** start_combat(participant_ids=['aldric', 'zara'], monster_templates=['wolf', 'wolf'])

**Output:**
ok

#### [+] engine 2

**Input:** attack(attacker_id='wolf_1', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: Wolf cannot act right now — combat turns are prompted one at a time by the engine. STOP and finish y

#### [+] engine 3

**Input:** start_combat(participant_ids=['aldric', 'zara'], monster_templates=['wolf'])

**Output:**
rejected: Combat is already active — do NOT call start_combat again. Initiative has been rolled; continue the 

#### [+] engine 4

**Input:** get_monster_actions(monster_id='wolf_1')

**Output:**
ok

#### [+] engine 5

**Input:** attack(attacker_id='wolf_1', target_id='aldric', weapon_name='Bite')

**Output:**
ok

#### [+] engine 6

**Input:** opportunity_attack(attacker_id='aldric', target_id='wolf_1', weapon_name='Longsword')

**Output:**
ok

#### [+] engine 7

**Input:** opportunity_attack(attacker_id='aldric', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: Aldric Stonemantle has already used their reaction this round.

#### [+] engine 8

**Input:** cast_spell(caster_id='zara', spell_name='Shield', target_ids=[])

**Output:**
ok

#### [+] engine 9

**Input:** end_turn()

**Output:**
ok

#### [+] engine 10

**Input:** end_turn()

**Output:**
rejected: This turn has already been passed. STOP — do not act for or end other combatants' turns; the engine 

#### [+] engine 11

**Input:** attack(attacker_id='wolf_2', target_id='aldric', weapon_name='Bite')

**Output:**
rejected: Only Wolf's turn is being resolved in this response — Wolf acts when the engine prompts their turn. 

#### [+] engine 12

**Input:** get_monster_actions(monster_id='wolf_2')

**Output:**
ok

#### [+] engine 13

**Input:** attack(attacker_id='wolf_2', target_id='aldric', weapon_name='Bite')

**Output:**
ok

#### [+] engine 14

**Input:** end_turn()

**Output:**
ok

#### [+] engine 15

**Input:** end_turn()

**Output:**
rejected: This turn has already been passed. STOP — do not act for or end other combatants' turns; the engine 

#### [+] engine 16

**Input:** attack(attacker_id='aldric', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: Only Wolf's turn is being resolved in this response — Aldric Stonemantle acts when the engine prompt

#### [+] engine 17

**Input:** attack(attacker_id='aldric', target_id='wolf_1', weapon_name='Longsword')

**Output:**
ok

#### [+] engine 18

**Input:** attack(attacker_id='aldric', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: No action remaining this turn.

#### [+] engine 19

**Input:** end_turn()

**Output:**
ok

#### [+] engine 20

**Input:** end_turn()

**Output:**
rejected: This turn has already been passed. STOP — do not act for or end other combatants' turns; the engine 

#### [+] engine 21

**Input:** attack(attacker_id='zara', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: Only Aldric Stonemantle's turn is being resolved in this response — Zara Moonwhisper acts when the e

#### [+] engine 22

**Input:** cast_spell(caster_id='zara', spell_name='Fire Bolt', target_ids=['wolf_1'])

**Output:**
ok

#### [+] engine 23

**Input:** attack(attacker_id='zara', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: No action remaining this turn.

#### [+] engine 24

**Input:** end_turn()

**Output:**
ok

#### [+] engine 25

**Input:** end_turn()

**Output:**
rejected: This turn has already been passed. STOP — do not act for or end other combatants' turns; the engine 

#### [+] engine 26

**Input:** attack(attacker_id='wolf_2', target_id='aldric', weapon_name='Bite')

**Output:**
rejected: Only Zara Moonwhisper's turn is being resolved in this response — Wolf acts when the engine prompts 

#### [+] engine 27

**Input:** get_monster_actions(monster_id='wolf_2')

**Output:**
ok

#### [+] engine 28

**Input:** attack(attacker_id='wolf_2', target_id='aldric', weapon_name='Bite')

**Output:**
ok

#### [+] engine 29

**Input:** end_turn()

**Output:**
ok

#### [+] engine 30

**Input:** end_turn()

**Output:**
rejected: This turn has already been passed. STOP — do not act for or end other combatants' turns; the engine 

#### [+] engine 31

**Input:** attack(attacker_id='aldric', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: Only Wolf's turn is being resolved in this response — Aldric Stonemantle acts when the engine prompt

#### [+] engine 32

**Input:** attack(attacker_id='aldric', target_id='wolf_2', weapon_name='Longsword')

**Output:**
ok

#### [+] engine 33

**Input:** attack(attacker_id='aldric', target_id='wolf_2', weapon_name='Longsword')

**Output:**
rejected: No action remaining this turn.

#### [+] engine 34

**Input:** end_turn()

**Output:**
ok

#### [+] engine 35

**Input:** end_turn()

**Output:**
rejected: This turn has already been passed. STOP — do not act for or end other combatants' turns; the engine 

#### [+] engine 36

**Input:** attack(attacker_id='zara', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: Only Aldric Stonemantle's turn is being resolved in this response — Zara Moonwhisper acts when the e

#### [+] engine 37

**Input:** cast_spell(caster_id='zara', spell_name='Fire Bolt', target_ids=['wolf_2'])

**Output:**
ok

#### [+] engine 38

**Input:** attack(attacker_id='zara', target_id='wolf_2', weapon_name='Longsword')

**Output:**
rejected: No action remaining this turn.

#### [+] engine 39

**Input:** end_turn()

**Output:**
ok

#### [+] engine 40

**Input:** end_turn()

**Output:**
rejected: This turn has already been passed. STOP — do not act for or end other combatants' turns; the engine 

#### [+] engine 41

**Input:** attack(attacker_id='wolf_2', target_id='aldric', weapon_name='Bite')

**Output:**
rejected: Only Zara Moonwhisper's turn is being resolved in this response — Wolf acts when the engine prompts 

#### [+] engine 42

**Input:** get_monster_actions(monster_id='wolf_2')

**Output:**
ok

#### [+] engine 43

**Input:** attack(attacker_id='wolf_2', target_id='aldric', weapon_name='Bite')

**Output:**
ok

#### [+] engine 44

**Input:** end_turn()

**Output:**
ok

#### [+] engine 45

**Input:** end_turn()

**Output:**
rejected: This turn has already been passed. STOP — do not act for or end other combatants' turns; the engine 

#### [+] engine 46

**Input:** attack(attacker_id='aldric', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: Only Wolf's turn is being resolved in this response — Aldric Stonemantle acts when the engine prompt

#### [+] engine 47

**Input:** apply_damage(target_id='zara', amount=24, damage_type='bludgeoning')

**Output:**
ok

#### [+] engine 48

**Input:** end_turn()

**Output:**
ok

#### [+] engine 49

**Input:** death_save(character_id='zara')

**Output:**
ok

#### [+] engine 50

**Input:** apply_healing(target_id='zara', amount=8)

**Output:**
ok

#### [+] engine 51

**Input:** end_combat(xp_awarded=100)

**Output:**
ok

#### [+] engine 52

**Input:** end_combat(xp_awarded=100)

**Output:**
rejected: No active combat to end.

</details>

---

## Run — 2026-06-12 07:50

**Status:** PASS  
**Failures:** 0  
**Warnings:** 0

Turns: 52 setup + 0 AI = 52 total  
Cost: free (engine-only, no LLM)  
Initial: `location=thornfield, combat_active=False, hp_summary={'Aldric Stonemantle': '28/28', 'Zara Moonwhisper': '19/19'}`  
Final: `location=thornfield, combat_active=False, hp_summary={'Aldric Stonemantle': '28/28', 'Zara Moonwhisper': '8/19'}`

<details><summary>Turn log</summary>

#### [+] engine 1

**Input:** start_combat(participant_ids=['aldric', 'zara'], monster_templates=['wolf', 'wolf'])

**Output:**
ok

#### [+] engine 2

**Input:** attack(attacker_id='wolf_1', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: Wolf cannot act right now — combat turns are prompted one at a time by the engine. STOP and finish y

#### [+] engine 3

**Input:** start_combat(participant_ids=['aldric', 'zara'], monster_templates=['wolf'])

**Output:**
rejected: Combat is already active — do NOT call start_combat again. Initiative has been rolled; continue the 

#### [+] engine 4

**Input:** get_monster_actions(monster_id='wolf_1')

**Output:**
ok

#### [+] engine 5

**Input:** attack(attacker_id='wolf_1', target_id='aldric', weapon_name='Bite')

**Output:**
ok

#### [+] engine 6

**Input:** opportunity_attack(attacker_id='aldric', target_id='wolf_1', weapon_name='Longsword')

**Output:**
ok

#### [+] engine 7

**Input:** opportunity_attack(attacker_id='aldric', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: Aldric Stonemantle has already used their reaction this round.

#### [+] engine 8

**Input:** cast_spell(caster_id='zara', spell_name='Shield', target_ids=[])

**Output:**
ok

#### [+] engine 9

**Input:** end_turn()

**Output:**
ok

#### [+] engine 10

**Input:** end_turn()

**Output:**
rejected: This turn has already been passed. STOP — do not act for or end other combatants' turns; the engine 

#### [+] engine 11

**Input:** attack(attacker_id='wolf_2', target_id='aldric', weapon_name='Bite')

**Output:**
rejected: Only Wolf's turn is being resolved in this response — Wolf acts when the engine prompts their turn. 

#### [+] engine 12

**Input:** get_monster_actions(monster_id='wolf_2')

**Output:**
ok

#### [+] engine 13

**Input:** attack(attacker_id='wolf_2', target_id='aldric', weapon_name='Bite')

**Output:**
ok

#### [+] engine 14

**Input:** end_turn()

**Output:**
ok

#### [+] engine 15

**Input:** end_turn()

**Output:**
rejected: This turn has already been passed. STOP — do not act for or end other combatants' turns; the engine 

#### [+] engine 16

**Input:** attack(attacker_id='aldric', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: Only Wolf's turn is being resolved in this response — Aldric Stonemantle acts when the engine prompt

#### [+] engine 17

**Input:** attack(attacker_id='aldric', target_id='wolf_1', weapon_name='Longsword')

**Output:**
ok

#### [+] engine 18

**Input:** attack(attacker_id='aldric', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: No action remaining this turn.

#### [+] engine 19

**Input:** end_turn()

**Output:**
ok

#### [+] engine 20

**Input:** end_turn()

**Output:**
rejected: This turn has already been passed. STOP — do not act for or end other combatants' turns; the engine 

#### [+] engine 21

**Input:** attack(attacker_id='zara', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: Only Aldric Stonemantle's turn is being resolved in this response — Zara Moonwhisper acts when the e

#### [+] engine 22

**Input:** cast_spell(caster_id='zara', spell_name='Fire Bolt', target_ids=['wolf_1'])

**Output:**
ok

#### [+] engine 23

**Input:** attack(attacker_id='zara', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: No action remaining this turn.

#### [+] engine 24

**Input:** end_turn()

**Output:**
ok

#### [+] engine 25

**Input:** end_turn()

**Output:**
rejected: This turn has already been passed. STOP — do not act for or end other combatants' turns; the engine 

#### [+] engine 26

**Input:** attack(attacker_id='wolf_2', target_id='aldric', weapon_name='Bite')

**Output:**
rejected: Only Zara Moonwhisper's turn is being resolved in this response — Wolf acts when the engine prompts 

#### [+] engine 27

**Input:** get_monster_actions(monster_id='wolf_2')

**Output:**
ok

#### [+] engine 28

**Input:** attack(attacker_id='wolf_2', target_id='aldric', weapon_name='Bite')

**Output:**
ok

#### [+] engine 29

**Input:** end_turn()

**Output:**
ok

#### [+] engine 30

**Input:** end_turn()

**Output:**
rejected: This turn has already been passed. STOP — do not act for or end other combatants' turns; the engine 

#### [+] engine 31

**Input:** attack(attacker_id='aldric', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: Only Wolf's turn is being resolved in this response — Aldric Stonemantle acts when the engine prompt

#### [+] engine 32

**Input:** attack(attacker_id='aldric', target_id='wolf_2', weapon_name='Longsword')

**Output:**
ok

#### [+] engine 33

**Input:** attack(attacker_id='aldric', target_id='wolf_2', weapon_name='Longsword')

**Output:**
rejected: No action remaining this turn.

#### [+] engine 34

**Input:** end_turn()

**Output:**
ok

#### [+] engine 35

**Input:** end_turn()

**Output:**
rejected: This turn has already been passed. STOP — do not act for or end other combatants' turns; the engine 

#### [+] engine 36

**Input:** attack(attacker_id='zara', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: Only Aldric Stonemantle's turn is being resolved in this response — Zara Moonwhisper acts when the e

#### [+] engine 37

**Input:** cast_spell(caster_id='zara', spell_name='Fire Bolt', target_ids=['wolf_2'])

**Output:**
ok

#### [+] engine 38

**Input:** attack(attacker_id='zara', target_id='wolf_2', weapon_name='Longsword')

**Output:**
rejected: No action remaining this turn.

#### [+] engine 39

**Input:** end_turn()

**Output:**
ok

#### [+] engine 40

**Input:** end_turn()

**Output:**
rejected: This turn has already been passed. STOP — do not act for or end other combatants' turns; the engine 

#### [+] engine 41

**Input:** attack(attacker_id='wolf_2', target_id='aldric', weapon_name='Bite')

**Output:**
rejected: Only Zara Moonwhisper's turn is being resolved in this response — Wolf acts when the engine prompts 

#### [+] engine 42

**Input:** get_monster_actions(monster_id='wolf_2')

**Output:**
ok

#### [+] engine 43

**Input:** attack(attacker_id='wolf_2', target_id='aldric', weapon_name='Bite')

**Output:**
ok

#### [+] engine 44

**Input:** end_turn()

**Output:**
ok

#### [+] engine 45

**Input:** end_turn()

**Output:**
rejected: This turn has already been passed. STOP — do not act for or end other combatants' turns; the engine 

#### [+] engine 46

**Input:** attack(attacker_id='aldric', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: Only Wolf's turn is being resolved in this response — Aldric Stonemantle acts when the engine prompt

#### [+] engine 47

**Input:** apply_damage(target_id='zara', amount=24, damage_type='bludgeoning')

**Output:**
ok

#### [+] engine 48

**Input:** end_turn()

**Output:**
ok

#### [+] engine 49

**Input:** death_save(character_id='zara')

**Output:**
ok

#### [+] engine 50

**Input:** apply_healing(target_id='zara', amount=8)

**Output:**
ok

#### [+] engine 51

**Input:** end_combat(xp_awarded=100)

**Output:**
ok

#### [+] engine 52

**Input:** end_combat(xp_awarded=100)

**Output:**
rejected: No active combat to end.

</details>

---

## Run — 2026-06-12 07:50

**Status:** PASS  
**Failures:** 0  
**Warnings:** 0

Turns: 52 setup + 0 AI = 52 total  
Cost: free (engine-only, no LLM)  
Initial: `location=thornfield, combat_active=False, hp_summary={'Aldric Stonemantle': '28/28', 'Zara Moonwhisper': '19/19'}`  
Final: `location=thornfield, combat_active=False, hp_summary={'Aldric Stonemantle': '28/28', 'Zara Moonwhisper': '8/19'}`

<details><summary>Turn log</summary>

#### [+] engine 1

**Input:** start_combat(participant_ids=['aldric', 'zara'], monster_templates=['wolf', 'wolf'])

**Output:**
ok

#### [+] engine 2

**Input:** attack(attacker_id='wolf_1', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: Wolf cannot act right now — combat turns are prompted one at a time by the engine. STOP and finish y

#### [+] engine 3

**Input:** start_combat(participant_ids=['aldric', 'zara'], monster_templates=['wolf'])

**Output:**
rejected: Combat is already active — do NOT call start_combat again. Initiative has been rolled; continue the 

#### [+] engine 4

**Input:** get_monster_actions(monster_id='wolf_1')

**Output:**
ok

#### [+] engine 5

**Input:** attack(attacker_id='wolf_1', target_id='aldric', weapon_name='Bite')

**Output:**
ok

#### [+] engine 6

**Input:** opportunity_attack(attacker_id='aldric', target_id='wolf_1', weapon_name='Longsword')

**Output:**
ok

#### [+] engine 7

**Input:** opportunity_attack(attacker_id='aldric', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: Aldric Stonemantle has already used their reaction this round.

#### [+] engine 8

**Input:** cast_spell(caster_id='zara', spell_name='Shield', target_ids=[])

**Output:**
ok

#### [+] engine 9

**Input:** end_turn()

**Output:**
ok

#### [+] engine 10

**Input:** end_turn()

**Output:**
rejected: This turn has already been passed. STOP — do not act for or end other combatants' turns; the engine 

#### [+] engine 11

**Input:** attack(attacker_id='wolf_2', target_id='aldric', weapon_name='Bite')

**Output:**
rejected: Only Wolf's turn is being resolved in this response — Wolf acts when the engine prompts their turn. 

#### [+] engine 12

**Input:** get_monster_actions(monster_id='wolf_2')

**Output:**
ok

#### [+] engine 13

**Input:** attack(attacker_id='wolf_2', target_id='aldric', weapon_name='Bite')

**Output:**
ok

#### [+] engine 14

**Input:** end_turn()

**Output:**
ok

#### [+] engine 15

**Input:** end_turn()

**Output:**
rejected: This turn has already been passed. STOP — do not act for or end other combatants' turns; the engine 

#### [+] engine 16

**Input:** attack(attacker_id='aldric', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: Only Wolf's turn is being resolved in this response — Aldric Stonemantle acts when the engine prompt

#### [+] engine 17

**Input:** attack(attacker_id='aldric', target_id='wolf_1', weapon_name='Longsword')

**Output:**
ok

#### [+] engine 18

**Input:** attack(attacker_id='aldric', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: No action remaining this turn.

#### [+] engine 19

**Input:** end_turn()

**Output:**
ok

#### [+] engine 20

**Input:** end_turn()

**Output:**
rejected: This turn has already been passed. STOP — do not act for or end other combatants' turns; the engine 

#### [+] engine 21

**Input:** attack(attacker_id='zara', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: Only Aldric Stonemantle's turn is being resolved in this response — Zara Moonwhisper acts when the e

#### [+] engine 22

**Input:** cast_spell(caster_id='zara', spell_name='Fire Bolt', target_ids=['wolf_1'])

**Output:**
ok

#### [+] engine 23

**Input:** attack(attacker_id='zara', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: No action remaining this turn.

#### [+] engine 24

**Input:** end_turn()

**Output:**
ok

#### [+] engine 25

**Input:** end_turn()

**Output:**
rejected: This turn has already been passed. STOP — do not act for or end other combatants' turns; the engine 

#### [+] engine 26

**Input:** attack(attacker_id='wolf_2', target_id='aldric', weapon_name='Bite')

**Output:**
rejected: Only Zara Moonwhisper's turn is being resolved in this response — Wolf acts when the engine prompts 

#### [+] engine 27

**Input:** get_monster_actions(monster_id='wolf_2')

**Output:**
ok

#### [+] engine 28

**Input:** attack(attacker_id='wolf_2', target_id='aldric', weapon_name='Bite')

**Output:**
ok

#### [+] engine 29

**Input:** end_turn()

**Output:**
ok

#### [+] engine 30

**Input:** end_turn()

**Output:**
rejected: This turn has already been passed. STOP — do not act for or end other combatants' turns; the engine 

#### [+] engine 31

**Input:** attack(attacker_id='aldric', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: Only Wolf's turn is being resolved in this response — Aldric Stonemantle acts when the engine prompt

#### [+] engine 32

**Input:** attack(attacker_id='aldric', target_id='wolf_2', weapon_name='Longsword')

**Output:**
ok

#### [+] engine 33

**Input:** attack(attacker_id='aldric', target_id='wolf_2', weapon_name='Longsword')

**Output:**
rejected: No action remaining this turn.

#### [+] engine 34

**Input:** end_turn()

**Output:**
ok

#### [+] engine 35

**Input:** end_turn()

**Output:**
rejected: This turn has already been passed. STOP — do not act for or end other combatants' turns; the engine 

#### [+] engine 36

**Input:** attack(attacker_id='zara', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: Only Aldric Stonemantle's turn is being resolved in this response — Zara Moonwhisper acts when the e

#### [+] engine 37

**Input:** cast_spell(caster_id='zara', spell_name='Fire Bolt', target_ids=['wolf_2'])

**Output:**
ok

#### [+] engine 38

**Input:** attack(attacker_id='zara', target_id='wolf_2', weapon_name='Longsword')

**Output:**
rejected: No action remaining this turn.

#### [+] engine 39

**Input:** end_turn()

**Output:**
ok

#### [+] engine 40

**Input:** end_turn()

**Output:**
rejected: This turn has already been passed. STOP — do not act for or end other combatants' turns; the engine 

#### [+] engine 41

**Input:** attack(attacker_id='wolf_2', target_id='aldric', weapon_name='Bite')

**Output:**
rejected: Only Zara Moonwhisper's turn is being resolved in this response — Wolf acts when the engine prompts 

#### [+] engine 42

**Input:** get_monster_actions(monster_id='wolf_2')

**Output:**
ok

#### [+] engine 43

**Input:** attack(attacker_id='wolf_2', target_id='aldric', weapon_name='Bite')

**Output:**
ok

#### [+] engine 44

**Input:** end_turn()

**Output:**
ok

#### [+] engine 45

**Input:** end_turn()

**Output:**
rejected: This turn has already been passed. STOP — do not act for or end other combatants' turns; the engine 

#### [+] engine 46

**Input:** attack(attacker_id='aldric', target_id='wolf_1', weapon_name='Longsword')

**Output:**
rejected: Only Wolf's turn is being resolved in this response — Aldric Stonemantle acts when the engine prompt

#### [+] engine 47

**Input:** apply_damage(target_id='zara', amount=24, damage_type='bludgeoning')

**Output:**
ok

#### [+] engine 48

**Input:** end_turn()

**Output:**
ok

#### [+] engine 49

**Input:** death_save(character_id='zara')

**Output:**
ok

#### [+] engine 50

**Input:** apply_healing(target_id='zara', amount=8)

**Output:**
ok

#### [+] engine 51

**Input:** end_combat(xp_awarded=100)

**Output:**
ok

#### [+] engine 52

**Input:** end_combat(xp_awarded=100)

**Output:**
rejected: No active combat to end.

</details>

