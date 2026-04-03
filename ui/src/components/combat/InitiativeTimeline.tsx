import { useGameStore } from "../../store/gameStore";
import { HPBar } from "../character/HPBar";

export function InitiativeTimeline() {
  const combat = useGameStore((s) => s.combat);
  const characters = useGameStore((s) => s.characters);

  if (!combat?.active) return null;

  const charMap = new Map(characters.map((c) => [c.id, c]));

  return (
    <div className="flex items-center gap-1 overflow-x-auto py-1 px-1">
      {combat.turn_order.map((cid, i) => {
        const combatant = combat.combatants[cid];
        const char = charMap.get(cid);
        if (!char || !combatant) return null;

        if (char.hp <= 0 || char.conditions.includes("dead")) return null;

        const isActive = i === combat.current_turn_index;
        const nameColor = char.is_player ? "text-accent" : "text-danger";

        return (
          <div key={cid} className="flex items-center">
            {i > 0 && (
              <span className="text-text-mechanical/30 text-[9px] mx-0.5">→</span>
            )}
            <div
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs whitespace-nowrap transition-all duration-200
                ${isActive
                  ? "bg-surface-elevated border border-accent/30 glow-accent"
                  : "opacity-60 hover:opacity-80"
                }`}
            >
              {isActive && <span className="text-accent text-[10px]">▶</span>}
              <span className={`font-display font-semibold text-[11px] tracking-wide ${nameColor}`}>
                {char.name}
              </span>
              <span className="text-text-mechanical/50 text-[9px] font-mono">
                {combatant.initiative >= 0 ? "+" : ""}{combatant.initiative}
              </span>
              <div className="w-12">
                <HPBar hp={char.hp} maxHp={char.max_hp} showText={false} size="sm" />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
