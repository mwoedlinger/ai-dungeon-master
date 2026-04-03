import { sendPlayerInput, sendCommand } from "../../api/websocket";
import { useGameStore } from "../../store/gameStore";

interface QuickAction {
  label: string;
  icon: string;
  action: () => void;
}

const EXPLORATION_ACTIONS: QuickAction[] = [
  { label: "Search", icon: "⊞", action: () => sendPlayerInput("I search the area carefully") },
  { label: "Short Rest", icon: "☽", action: () => sendPlayerInput("We take a short rest") },
  { label: "Long Rest", icon: "☾", action: () => sendPlayerInput("We take a long rest") },
  { label: "Map", icon: "◇", action: () => useGameStore.getState().setSidebarTab("map") },
  { label: "Save", icon: "✦", action: () => sendCommand("save") },
];

const COMBAT_ACTIONS: QuickAction[] = [
  { label: "Attack", icon: "⚔", action: () => sendPlayerInput("I attack with my weapon") },
  { label: "Cast Spell", icon: "✦", action: () => sendPlayerInput("I cast a spell") },
  { label: "Dodge", icon: "◇", action: () => sendPlayerInput("I take the Dodge action") },
  { label: "Dash", icon: "→", action: () => sendPlayerInput("I take the Dash action") },
  { label: "Disengage", icon: "←", action: () => sendPlayerInput("I take the Disengage action") },
];

export function QuickActions() {
  const mode = useGameStore((s) => s.mode);
  const isStreaming = useGameStore((s) => s.isStreaming);
  const actions = mode === "combat" ? COMBAT_ACTIONS : EXPLORATION_ACTIONS;

  return (
    <div className="flex flex-wrap gap-1.5">
      {actions.map((a) => (
        <button
          key={a.label}
          onClick={a.action}
          disabled={isStreaming}
          className="group flex items-center gap-1 px-2.5 py-1 text-[10px] rounded
            btn-ghost font-display tracking-wider uppercase"
        >
          <span className="text-[9px] opacity-40 group-hover:opacity-70 transition-opacity">
            {a.icon}
          </span>
          {a.label}
        </button>
      ))}
    </div>
  );
}
