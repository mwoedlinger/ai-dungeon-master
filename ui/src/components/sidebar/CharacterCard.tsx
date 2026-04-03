import type { Character } from "../../store/types";
import { useGameStore } from "../../store/gameStore";
import { HPBar } from "../character/HPBar";
import { SpellSlotPips } from "../character/SpellSlotPips";
import { ConditionBadge } from "../shared/ConditionBadge";

interface CharacterCardProps {
  character: Character;
}

export function CharacterCard({ character }: CharacterCardProps) {
  const setInspected = useGameStore((s) => s.setInspectedCharacter);
  const setInventory = useGameStore((s) => s.setInventoryDrawer);

  return (
    <div className="card corner-accents p-3 card-hover">
      {/* Header */}
      <div className="flex items-baseline justify-between mb-2">
        <h3 className="text-sm font-display font-semibold tracking-wide text-gold">
          {character.name}
        </h3>
        <span className="text-[9px] font-display tracking-wider text-text-mechanical uppercase">
          Lv{character.level} {character.class_name}
        </span>
      </div>

      {/* HP + AC */}
      <div className="flex items-center gap-2.5 mb-2">
        <div className="flex-1">
          <HPBar
            hp={character.hp}
            maxHp={character.max_hp}
            tempHp={character.temp_hp}
            size="sm"
          />
        </div>
        <div className="flex items-center gap-1 text-xs">
          <span className="text-text-mechanical/60 text-[9px]">AC</span>
          <span className="font-mono font-bold text-text-secondary">{character.ac}</span>
        </div>
      </div>

      {/* Spell slots */}
      {Object.keys(character.max_spell_slots).length > 0 && (
        <div className="mb-2">
          <SpellSlotPips
            spellSlots={character.spell_slots}
            maxSpellSlots={character.max_spell_slots}
          />
        </div>
      )}

      {/* Conditions */}
      {character.conditions.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {character.conditions.map((c) => (
            <ConditionBadge key={c} condition={c} />
          ))}
        </div>
      )}

      {/* Concentration */}
      {character.concentration && (
        <div className="text-[10px] text-magic mb-2 flex items-center gap-1">
          <span className="text-magic/50">✦</span>
          {character.concentration}
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-1.5 mt-2.5">
        <button
          onClick={() => setInspected(character.id)}
          className="flex-1 px-2 py-1 text-[10px] font-display tracking-wider rounded
            btn-ghost uppercase"
        >
          Sheet
        </button>
        <button
          onClick={() => setInventory(character.id)}
          className="flex-1 px-2 py-1 text-[10px] font-display tracking-wider rounded
            btn-ghost uppercase"
        >
          Inventory
        </button>
      </div>
    </div>
  );
}
