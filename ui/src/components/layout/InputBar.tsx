import { useRef, useState } from "react";
import { sendPlayerInput } from "../../api/websocket";
import { useGameStore } from "../../store/gameStore";
import { QuickActions } from "../shared/QuickActions";

export function InputBar() {
  const [input, setInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const isStreaming = useGameStore((s) => s.isStreaming);
  const mode = useGameStore((s) => s.mode);
  const currentTurn = useGameStore((s) => s.currentTurn);

  const isMonsterTurn = currentTurn && !currentTurn.is_player;
  const disabled = isStreaming || isMonsterTurn;

  function handleSubmit() {
    const text = input.trim();
    if (!text || disabled) return;
    sendPlayerInput(text);
    setInput("");
    inputRef.current?.focus();
  }

  let placeholder = "What do you do?";
  if (isMonsterTurn) {
    placeholder = `${currentTurn.character_name}'s turn (waiting...)`;
  } else if (mode === "combat" && currentTurn?.is_player) {
    placeholder = `${currentTurn.character_name}'s turn — what do you do?`;
  }

  const borderColor =
    mode === "combat" ? "border-danger/20" : "border-border-subtle";

  return (
    <div className={`relative bg-surface border-t ${borderColor} px-6 py-3`}>
      {/* Top decorative line */}
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-border-ornate/30 to-transparent" />

      <div className="flex gap-2.5 mb-2">
        <div className="relative flex-1">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSubmit();
            }}
            disabled={!!disabled}
            placeholder={placeholder}
            className="w-full px-4 py-2.5 rounded-lg
              bg-bg/80 border border-border
              text-sm text-text-primary placeholder:text-text-mechanical/60
              font-['Crimson_Text',serif]
              disabled:opacity-30 disabled:cursor-not-allowed
              transition-all duration-200"
            autoFocus
          />
          {isStreaming && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-accent animate-pulse-glow" />
            </div>
          )}
        </div>
        <button
          onClick={handleSubmit}
          disabled={!!disabled || !input.trim()}
          className="px-5 py-2.5 rounded-lg btn-primary font-display text-xs tracking-wider"
        >
          Send
        </button>
      </div>
      <QuickActions />
    </div>
  );
}
