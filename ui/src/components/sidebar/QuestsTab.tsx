import { useGameStore } from "../../store/gameStore";

const STATUS_STYLE: Record<string, { icon: string; color: string; glow?: string }> = {
  active: { icon: "◆", color: "text-gold", glow: "text-glow-gold" },
  completed: { icon: "✓", color: "text-heal" },
  failed: { icon: "✗", color: "text-danger" },
};

export function QuestsTab() {
  const world = useGameStore((s) => s.world);
  const quests = world?.quests ?? [];

  if (quests.length === 0) {
    return (
      <p className="text-xs text-text-mechanical/40 italic font-['Crimson_Text',serif] p-2">
        No quests tracked.
      </p>
    );
  }

  return (
    <div className="space-y-2.5">
      {quests.map((q) => {
        const style = STATUS_STYLE[q.status] ?? STATUS_STYLE.active;
        return (
          <div key={q.id} className="card p-3">
            <div className="flex items-start gap-2">
              <span className={`${style.color} ${style.glow ?? ""} text-xs mt-0.5`}>
                {style.icon}
              </span>
              <div className="flex-1 min-w-0">
                <h4 className="text-xs font-display font-semibold tracking-wide text-text-primary">
                  {q.title}
                </h4>
                <p className="text-[11px] text-text-secondary mt-0.5 font-['Crimson_Text',serif] leading-relaxed">
                  {q.description}
                </p>
                {q.completed_objectives.length > 0 && (
                  <div className="mt-1.5 space-y-0.5">
                    {q.completed_objectives.map((obj, i) => (
                      <div key={i} className="text-[10px] text-heal/80 flex items-center gap-1">
                        <span className="opacity-60">✓</span> {obj}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
