import { useGameStore } from "../../store/gameStore";
import { InitiativeTimeline } from "./InitiativeTimeline";

export function CombatOverlay() {
  const combat = useGameStore((s) => s.combat);

  if (!combat?.active) return null;

  return (
    <div className="relative border-b border-danger/20 bg-gradient-to-r from-surface via-danger/5 to-surface px-4 py-2.5 animate-combat-pulse">
      {/* Danger glow line at bottom */}
      <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-danger/40 to-transparent" />

      <div className="flex items-center gap-3 mb-1.5">
        <span className="font-display text-xs font-bold tracking-[0.15em] text-danger text-glow-danger uppercase">
          ⚔ Combat
        </span>
        <span className="text-[10px] font-mono text-text-mechanical">
          Round {combat.round}
        </span>
      </div>
      <InitiativeTimeline />
    </div>
  );
}
