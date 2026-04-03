import { useGameStore } from "../../store/gameStore";
import { AbilityScores } from "./AbilityScores";
import { HPBar } from "./HPBar";
import { SpellSlotPips } from "./SpellSlotPips";

export function CharacterSheetModal() {
  const charId = useGameStore((s) => s.inspectedCharacterId);
  const characters = useGameStore((s) => s.characters);
  const close = () => useGameStore.getState().setInspectedCharacter(null);

  const char = characters.find((c) => c.id === charId);
  if (!char) return null;

  function modifier(score: number): string {
    const mod = Math.floor((score - 10) / 2);
    return mod >= 0 ? `+${mod}` : `${mod}`;
  }

  const spellSaveDC = char.spellcasting_ability
    ? 8 +
      char.proficiency_bonus +
      Math.floor(
        (char.ability_scores[
          char.spellcasting_ability as keyof typeof char.ability_scores
        ] - 10) / 2
      )
    : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-[2px]"
      onClick={close}
    >
      <div
        className="w-full max-w-lg max-h-[85vh] overflow-y-auto
          bg-surface-elevated border border-border-ornate rounded-lg
          shadow-[0_8px_60px_rgba(0,0,0,0.5)]
          ornate-border p-6 animate-slide-up"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between mb-1">
          <div>
            <h2 className="text-lg font-display font-bold tracking-wide text-gold text-glow-gold">
              {char.name}
            </h2>
            <p className="text-[11px] text-text-secondary mt-0.5">
              {char.race} {char.class_name}
              {char.subclass && ` (${char.subclass})`} — Level {char.level}
              {char.background && ` | ${char.background}`}
              {char.alignment && ` | ${char.alignment}`}
            </p>
            <p className="text-[10px] text-text-mechanical mt-0.5 font-mono">
              XP: {char.xp}
            </p>
          </div>
          <button
            onClick={close}
            className="text-text-mechanical hover:text-text-primary text-sm leading-none p-1 transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Ornate divider */}
        <div className="divider-ornate" />

        {/* Personality */}
        {(char.personality_traits || char.ideals || char.bonds || char.flaws) && (
          <div className="mb-4 p-3 rounded-md bg-bg/60 border border-border-subtle text-xs text-text-secondary space-y-1 italic font-['Crimson_Text',serif]">
            {char.personality_traits && <p><span className="text-gold/80 not-italic font-display text-[10px] tracking-wider uppercase">Traits</span> {char.personality_traits}</p>}
            {char.ideals && <p><span className="text-gold/80 not-italic font-display text-[10px] tracking-wider uppercase">Ideals</span> {char.ideals}</p>}
            {char.bonds && <p><span className="text-gold/80 not-italic font-display text-[10px] tracking-wider uppercase">Bonds</span> {char.bonds}</p>}
            {char.flaws && <p><span className="text-gold/80 not-italic font-display text-[10px] tracking-wider uppercase">Flaws</span> {char.flaws}</p>}
          </div>
        )}

        {/* Ability Scores */}
        <SectionHeader>Ability Scores</SectionHeader>
        <div className="mb-5">
          <AbilityScores
            scores={char.ability_scores}
            savingThrowProficiencies={char.saving_throw_proficiencies}
          />
        </div>

        {/* Combat Stats */}
        <SectionHeader>Combat</SectionHeader>
        <div className="mb-5 p-3 rounded-md bg-bg/60 border border-border-subtle space-y-2.5">
          <HPBar hp={char.hp} maxHp={char.max_hp} tempHp={char.temp_hp} />
          <div className="grid grid-cols-3 gap-2 text-xs">
            <StatBlock label="AC" value={String(char.ac)} />
            <StatBlock label="Speed" value={`${char.speed} ft`} />
            <StatBlock label="Prof" value={`+${char.proficiency_bonus}`} />
          </div>
          <div className="text-[11px] text-text-mechanical">
            Hit Dice: <span className="text-text-secondary font-mono">{char.hit_dice_remaining}{char.hit_die_type}</span>
          </div>
          {char.conditions.length > 0 && (
            <div className="text-xs">
              <span className="text-text-mechanical">Conditions:</span>{" "}
              <span className="text-yellow-400">
                {char.conditions.join(", ")}
              </span>
            </div>
          )}
        </div>

        {/* Skills */}
        {char.skill_proficiencies.length > 0 && (
          <>
            <SectionHeader>Skills</SectionHeader>
            <p className="text-xs text-text-secondary mb-4">
              {char.skill_proficiencies.join(", ")}
            </p>
          </>
        )}

        {/* Weapons */}
        {char.weapons.length > 0 && (
          <>
            <SectionHeader>Weapons</SectionHeader>
            <div className="mb-4 space-y-1">
              {char.weapons.map((w, i) => (
                <div key={i} className="text-xs text-text-secondary">
                  <span className="text-text-primary">{w.name}</span>:{" "}
                  <span className="font-mono text-gold/80">{w.damage_dice}</span> {w.damage_type}
                  {w.properties.length > 0 && (
                    <span className="text-text-mechanical">
                      {" "}({w.properties.join(", ")})
                    </span>
                  )}
                </div>
              ))}
            </div>
          </>
        )}

        {/* Armor */}
        {char.armor && (
          <>
            <SectionHeader>Armor</SectionHeader>
            <p className="text-xs text-text-secondary mb-4">
              {char.armor.name} (AC <span className="font-mono">{char.armor.base_ac}</span>,{" "}
              {char.armor.armor_type})
              {char.armor.stealth_disadvantage && " — stealth disadvantage"}
            </p>
          </>
        )}

        {/* Spells */}
        {char.known_spells.length > 0 && (
          <>
            <SectionHeader>Spells</SectionHeader>
            <div className="mb-4 p-3 rounded-md bg-bg/60 border border-magic/15 space-y-2">
              {char.spellcasting_ability && (
                <div className="text-[11px] text-text-secondary font-mono">
                  <span className="text-magic/70">{char.spellcasting_ability}</span>
                  {spellSaveDC && <span> | DC {spellSaveDC}</span>}
                  {" | Atk "}
                  {modifier(
                    char.ability_scores[
                      char.spellcasting_ability as keyof typeof char.ability_scores
                    ]
                  )}
                </div>
              )}
              <SpellSlotPips
                spellSlots={char.spell_slots}
                maxSpellSlots={char.max_spell_slots}
              />
              <p className="text-xs text-text-secondary">
                {char.known_spells.join(", ")}
              </p>
            </div>
          </>
        )}

        {/* Class Resources */}
        {Object.keys(char.class_resources).length > 0 && (
          <>
            <SectionHeader>Class Resources</SectionHeader>
            <div className="mb-4">
              {Object.entries(char.class_resources).map(([k, v]) => (
                <div key={k} className="text-xs text-text-secondary">
                  <span className="text-text-primary">{k}:</span>{" "}
                  <span className="font-mono">{v}</span>
                </div>
              ))}
            </div>
          </>
        )}

        {/* Attuned Magic Items */}
        {char.attuned_items.length > 0 && (
          <>
            <SectionHeader>Attuned Items</SectionHeader>
            <div className="mb-4 space-y-1">
              {char.attuned_items.map((m, i) => (
                <div key={i} className="text-xs text-text-secondary">
                  <span className="text-magic text-glow-magic">{m.name}</span>
                  {m.bonus > 0 && <span className="font-mono text-magic/70"> +{m.bonus}</span>}
                  <span className="text-text-mechanical"> ({m.rarity})</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-[10px] font-display font-semibold tracking-[0.2em] text-gold/70 uppercase mb-2">
      {children}
    </h3>
  );
}

function StatBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-center">
      <div className="text-[9px] text-text-mechanical/60 uppercase tracking-wider mb-0.5">{label}</div>
      <div className="font-mono font-bold text-sm text-text-primary">{value}</div>
    </div>
  );
}
