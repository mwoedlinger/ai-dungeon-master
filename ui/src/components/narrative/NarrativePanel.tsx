import { useEffect, useRef } from "react";
import { useGameStore } from "../../store/gameStore";
import { NarrativeMessage } from "./NarrativeMessage";
import { ProseBlock } from "./ProseBlock";
import { StreamingCursor } from "./StreamingCursor";

export function NarrativePanel() {
  const messages = useGameStore((s) => s.messages);
  const streamingBuffer = useGameStore((s) => s.streamingBuffer);
  const isStreaming = useGameStore((s) => s.isStreaming);
  const mode = useGameStore((s) => s.mode);

  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new content
  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages.length, streamingBuffer]);

  return (
    <div
      ref={scrollRef}
      className={`flex-1 overflow-y-auto border-r ${
        mode === "combat" ? "border-danger/15" : "border-border-subtle"
      }`}
    >
      {/* Subtle inner glow at top */}
      <div className="sticky top-0 h-8 bg-gradient-to-b from-bg/80 to-transparent pointer-events-none z-10" />

      <div className="px-8 pb-6 -mt-4 space-y-5">
        {messages.length === 0 && !isStreaming && (
          <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
            <div className="text-gold-dim/30 text-4xl animate-float">⚔</div>
            <p className="font-display text-xs tracking-[0.25em] text-text-mechanical/40 uppercase">
              The adventure awaits
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <NarrativeMessage key={msg.id} message={msg} />
        ))}

        {/* Streaming buffer */}
        {isStreaming && streamingBuffer && (
          <div className="animate-fade-in">
            <ProseBlock text={streamingBuffer} />
            <StreamingCursor />
          </div>
        )}
      </div>

      {/* Bottom fade */}
      <div className="sticky bottom-0 h-6 bg-gradient-to-t from-bg/60 to-transparent pointer-events-none z-10" />
    </div>
  );
}
