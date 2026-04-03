import { useGameStore } from "../../store/gameStore";
import { sendPlayerInput } from "../../api/websocket";

export function MapTab() {
  const world = useGameStore((s) => s.world);

  if (!world) {
    return <EmptyState text="No world data." />;
  }

  const loc = world.locations[world.current_location_id];
  if (!loc) {
    return <EmptyState text="Unknown location." />;
  }

  const connections = loc.connected_to
    .map((cid) => {
      const target = world.locations[cid];
      return { id: cid, name: target?.name ?? cid };
    })
    .filter(Boolean);

  return (
    <div className="space-y-4">
      {/* Current location */}
      <div>
        <h3 className="text-sm font-display font-semibold tracking-wide text-accent text-glow-accent mb-1.5">
          {loc.name}
        </h3>
        <p className="text-xs text-text-secondary leading-relaxed font-['Crimson_Text',serif]">
          {loc.description.length > 200
            ? loc.description.slice(0, 200) + "..."
            : loc.description}
        </p>
      </div>

      {/* Exits */}
      {connections.length > 0 && (
        <div>
          <h4 className="text-[9px] font-display font-semibold tracking-[0.2em] text-text-mechanical/60 uppercase mb-2">
            Exits
          </h4>
          <div className="space-y-1.5">
            {connections.map((c) => (
              <button
                key={c.id}
                onClick={() =>
                  sendPlayerInput(`I travel to ${c.name}`)
                }
                className="w-full text-left px-3 py-2 text-sm rounded-md
                  card card-hover group"
              >
                <span className="text-text-mechanical/40 group-hover:text-accent/60 transition-colors mr-1.5">→</span>
                <span className="group-hover:text-accent transition-colors">{c.name}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <p className="text-xs text-text-mechanical/40 italic font-['Crimson_Text',serif] p-2">
      {text}
    </p>
  );
}
