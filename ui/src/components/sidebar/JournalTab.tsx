import { useGameStore } from "../../store/gameStore";

const DISPOSITION_COLOR: Record<string, string> = {
  friendly: "text-heal",
  neutral: "text-gold",
  hostile: "text-danger",
  fearful: "text-magic",
};

export function JournalTab() {
  const journal = useGameStore((s) => s.journal);

  if (!journal) {
    return <EmptyState />;
  }

  const summary = journal.global_summary || journal.conversation_summary;
  const hasNpcs =
    Object.keys(journal.npc_attitudes).length > 0 ||
    Object.keys(journal.npc_summaries).length > 0;
  const allNpcIds = [
    ...new Set([
      ...Object.keys(journal.npc_attitudes),
      ...Object.keys(journal.npc_summaries),
    ]),
  ].sort();
  const recentEntries = journal.global_entries.slice(-15);
  const hasLocations = Object.keys(journal.location_summaries).length > 0;

  if (!summary && !hasNpcs && recentEntries.length === 0 && !hasLocations) {
    return <EmptyState />;
  }

  return (
    <div className="space-y-4">
      {/* Global summary */}
      {summary && (
        <div>
          <SectionLabel>Story So Far</SectionLabel>
          <p className="text-xs text-text-secondary leading-relaxed font-['Crimson_Text',serif]">
            {summary}
          </p>
        </div>
      )}

      {/* Location summaries */}
      {hasLocations && (
        <div>
          <SectionLabel>Location Notes</SectionLabel>
          {Object.entries(journal.location_summaries).map(([locId, s]) => (
            <div key={locId} className="mb-1.5">
              <span className="text-[10px] text-accent font-display tracking-wider">{locId}</span>
              <p className="text-[11px] text-text-secondary/80 ml-2 font-['Crimson_Text',serif]">{s}</p>
            </div>
          ))}
        </div>
      )}

      {/* NPC knowledge */}
      {hasNpcs && (
        <div>
          <SectionLabel>NPC Knowledge</SectionLabel>
          {allNpcIds.map((npcId) => {
            const att = journal.npc_attitudes[npcId];
            const npcSum = journal.npc_summaries[npcId];
            const color = att
              ? DISPOSITION_COLOR[att.disposition] ?? "text-text-secondary"
              : "text-text-secondary";
            return (
              <div key={npcId} className="mb-2">
                <div className="flex items-center gap-1.5">
                  <span className={`text-[11px] font-display font-semibold tracking-wide ${color}`}>
                    {npcId}
                  </span>
                  {att && (
                    <span className={`text-[9px] ${color}/60 font-mono`}>
                      {att.disposition}
                    </span>
                  )}
                </div>
                {att?.notes && (
                  <p className="text-[10px] text-text-mechanical ml-2 mt-0.5">
                    {att.notes}
                  </p>
                )}
                {npcSum && (
                  <p className="text-[10px] text-text-secondary/70 ml-2 mt-0.5 font-['Crimson_Text',serif]">
                    {npcSum}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Recent events */}
      {recentEntries.length > 0 && (
        <div>
          <SectionLabel>Recent Events</SectionLabel>
          <div className="space-y-1">
            {recentEntries.map((e, i) => (
              <div key={i} className="text-[10px] text-text-secondary/70 flex items-start gap-1.5">
                <span className={`mt-0.5 ${e.importance === "major" ? "text-gold" : "text-text-mechanical/40"}`}>
                  {e.importance === "major" ? "★" : "·"}
                </span>
                <span>
                  {e.event}
                  {e.location_id && (
                    <span className="text-text-mechanical/40 ml-1 font-mono text-[9px]">[{e.location_id}]</span>
                  )}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="text-[9px] font-display font-semibold tracking-[0.2em] text-gold/60 uppercase mb-1.5">
      {children}
    </h4>
  );
}

function EmptyState() {
  return (
    <p className="text-xs text-text-mechanical/40 italic font-['Crimson_Text',serif] p-2">
      No journal entries yet.
    </p>
  );
}
