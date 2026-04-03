import { useGameStore } from "../../store/gameStore";
import { CompendiumTab } from "./CompendiumTab";
import { JournalTab } from "./JournalTab";
import { MapTab } from "./MapTab";
import { PartyTab } from "./PartyTab";
import { QuestsTab } from "./QuestsTab";

const TABS = [
  { key: "party" as const, label: "Party", icon: "⚔" },
  { key: "map" as const, label: "Map", icon: "◇" },
  { key: "quests" as const, label: "Quests", icon: "☆" },
  { key: "journal" as const, label: "Journal", icon: "✎" },
  { key: "compendium" as const, label: "SRD", icon: "✦" },
];

export function Sidebar() {
  const activeTab = useGameStore((s) => s.sidebarTab);
  const setTab = useGameStore((s) => s.setSidebarTab);

  return (
    <div className="w-80 flex flex-col bg-surface min-h-0">
      {/* Tab bar */}
      <div className="relative flex border-b border-border-subtle px-1">
        {/* Bottom decorative line */}
        <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-gold-dim/20 to-transparent" />

        {TABS.map((tab) => {
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setTab(tab.key)}
              className={`relative flex-1 flex flex-col items-center gap-0.5 px-2 py-2 transition-all duration-200
                ${isActive
                  ? "text-accent"
                  : "text-text-mechanical hover:text-text-secondary"
                }`}
            >
              <span className={`text-[10px] ${isActive ? "opacity-80" : "opacity-40"}`}>
                {tab.icon}
              </span>
              <span className="text-[10px] font-display tracking-wider">
                {tab.label}
              </span>
              {isActive && (
                <div className="absolute bottom-0 left-2 right-2 h-px bg-accent shadow-[0_0_6px_var(--color-accent)]" />
              )}
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto p-3">
        {activeTab === "party" && <PartyTab />}
        {activeTab === "map" && <MapTab />}
        {activeTab === "quests" && <QuestsTab />}
        {activeTab === "journal" && <JournalTab />}
        {activeTab === "compendium" && <CompendiumTab />}
      </div>
    </div>
  );
}
