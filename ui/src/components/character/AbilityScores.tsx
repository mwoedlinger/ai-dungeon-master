import type { AbilityScores as AbilityScoresType } from "../../store/types";

interface AbilityScoresProps {
  scores: AbilityScoresType;
  savingThrowProficiencies?: string[];
}

const ABILITIES = ["STR", "DEX", "CON", "INT", "WIS", "CHA"] as const;

function modifier(score: number): string {
  const mod = Math.floor((score - 10) / 2);
  return mod >= 0 ? `+${mod}` : `${mod}`;
}

export function AbilityScores({
  scores,
  savingThrowProficiencies = [],
}: AbilityScoresProps) {
  return (
    <div className="grid grid-cols-6 gap-1.5">
      {ABILITIES.map((ab) => {
        const val = scores[ab];
        const hasSave = savingThrowProficiencies.includes(ab);
        return (
          <div
            key={ab}
            className="flex flex-col items-center py-2 px-1 rounded-md
              bg-bg/60 border border-border-subtle
              hover:border-border-ornate/50 transition-colors"
          >
            <span className="text-[8px] font-display tracking-[0.2em] text-text-mechanical/60 uppercase">
              {ab}
              {hasSave && <span className="text-gold ml-0.5">*</span>}
            </span>
            <span className="text-lg font-bold text-text-primary leading-tight mt-0.5">
              {modifier(val)}
            </span>
            <span className="text-[10px] text-text-mechanical font-mono">{val}</span>
          </div>
        );
      })}
    </div>
  );
}
