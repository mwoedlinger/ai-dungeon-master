interface SpellSlotPipsProps {
  spellSlots: Record<string, number>;
  maxSpellSlots: Record<string, number>;
}

export function SpellSlotPips({
  spellSlots,
  maxSpellSlots,
}: SpellSlotPipsProps) {
  const levels = Object.keys(maxSpellSlots)
    .map(Number)
    .filter((l) => maxSpellSlots[String(l)] > 0)
    .sort();

  if (levels.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1">
      {levels.map((lvl) => {
        const total = maxSpellSlots[String(lvl)] ?? 0;
        const remaining = spellSlots[String(lvl)] ?? 0;
        return (
          <div key={lvl} className="flex items-center gap-0.5">
            <span className="text-[9px] text-text-mechanical/60 mr-0.5 font-mono">
              {lvl}
            </span>
            {Array.from({ length: total }, (_, i) => (
              <span
                key={i}
                className={`inline-block w-1.5 h-1.5 rounded-full transition-all duration-300 ${
                  i < remaining
                    ? "bg-slot-available shadow-[0_0_5px_var(--color-slot-available)]"
                    : "bg-slot-spent/40"
                }`}
              />
            ))}
          </div>
        );
      })}
    </div>
  );
}
