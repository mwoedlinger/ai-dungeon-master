interface HPBarProps {
  hp: number;
  maxHp: number;
  tempHp?: number;
  showText?: boolean;
  size?: "sm" | "md";
}

export function HPBar({
  hp,
  maxHp,
  tempHp = 0,
  showText = true,
  size = "md",
}: HPBarProps) {
  const ratio = maxHp > 0 ? Math.max(0, Math.min(hp / maxHp, 1)) : 0;
  const height = size === "sm" ? "h-1.5" : "h-2.5";

  // Gradient colors based on health
  const barStyle = ratio > 0.5
    ? {
        background: `linear-gradient(90deg, #2d9d5a, #3ebd6a)`,
        boxShadow: `0 0 6px rgba(62, 189, 106, 0.3)`,
      }
    : ratio > 0.25
      ? {
          background: `linear-gradient(90deg, #c4960a, #e8b414)`,
          boxShadow: `0 0 6px rgba(232, 180, 20, 0.3)`,
        }
      : {
          background: `linear-gradient(90deg, #a12030, #c93545)`,
          boxShadow: `0 0 6px rgba(201, 53, 69, 0.4)`,
        };

  return (
    <div className="flex items-center gap-2">
      <div
        className={`flex-1 ${height} rounded-full bg-border/40 overflow-hidden`}
      >
        <div
          className={`${height} rounded-full transition-all duration-500 ease-out`}
          style={{ width: `${ratio * 100}%`, ...barStyle }}
        />
      </div>
      {showText && (
        <span className="text-[10px] font-mono text-text-secondary whitespace-nowrap tabular-nums">
          {hp}/{maxHp}
          {tempHp > 0 && (
            <span className="text-accent">+{tempHp}</span>
          )}
        </span>
      )}
    </div>
  );
}
