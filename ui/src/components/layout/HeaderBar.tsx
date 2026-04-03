import { useGameStore } from "../../store/gameStore";

function formatTime(time: { day: number; hour: number; minute: number }): string {
  const period =
    time.hour >= 6 && time.hour < 12
      ? "morning"
      : time.hour >= 12 && time.hour < 17
        ? "afternoon"
        : time.hour >= 17 && time.hour < 21
          ? "evening"
          : "night";
  return `Day ${time.day}, ${String(time.hour).padStart(2, "0")}:${String(time.minute).padStart(2, "0")} (${period})`;
}

const TIME_ICON: Record<string, string> = {
  morning: "☀",
  afternoon: "☀",
  evening: "☾",
  night: "☾",
};

export function HeaderBar() {
  const world = useGameStore((s) => s.world);
  const mode = useGameStore((s) => s.mode);

  const loc = world?.locations[world.current_location_id ?? ""];
  const locationName = loc?.name ?? "";
  const timeStr = world?.time ? formatTime(world.time) : "";

  const period = world?.time
    ? (world.time.hour >= 6 && world.time.hour < 17 ? "morning" : "evening")
    : "";
  const timeIcon = period ? TIME_ICON[period] || "" : "";

  return (
    <header
      className="relative flex items-center justify-between px-6 py-2.5
        bg-gradient-to-r from-surface via-surface to-surface
        border-b border-border-subtle"
    >
      {/* Subtle gold line at bottom */}
      <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-gold-dim/30 to-transparent" />

      <div className="flex items-center gap-3">
        <h1 className="font-display text-[11px] font-semibold tracking-[0.2em] text-gold/80 uppercase">
          Dungeon Weaver
        </h1>
        {mode === "combat" && (
          <span className="px-2 py-0.5 text-[9px] font-display tracking-[0.15em] uppercase text-danger bg-danger/10 border border-danger/20 rounded">
            Combat
          </span>
        )}
      </div>

      <div className="flex items-center gap-5 text-[11px]">
        {timeStr && (
          <span className="flex items-center gap-1.5 text-text-mechanical">
            <span className="text-gold-dim/60 text-xs">{timeIcon}</span>
            <span className="font-mono text-[10px]">{timeStr}</span>
          </span>
        )}
        {locationName && (
          <span className="flex items-center gap-1.5">
            <span className="text-gold-dim/40 text-[8px]">◆</span>
            <span className="font-display text-[11px] tracking-wider text-gold/90">{locationName}</span>
          </span>
        )}
      </div>
    </header>
  );
}
