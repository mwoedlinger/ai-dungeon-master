interface ConditionBadgeProps {
  condition: string;
}

const CONDITION_STYLES: Record<string, { bg: string; text: string; glow?: string }> = {
  poisoned: { bg: "bg-green-900/50", text: "text-green-400", glow: "shadow-[0_0_4px_rgba(74,222,128,0.15)]" },
  frightened: { bg: "bg-purple-900/50", text: "text-purple-400", glow: "shadow-[0_0_4px_rgba(192,132,252,0.15)]" },
  charmed: { bg: "bg-pink-900/50", text: "text-pink-400", glow: "shadow-[0_0_4px_rgba(244,114,182,0.15)]" },
  stunned: { bg: "bg-yellow-900/50", text: "text-yellow-400" },
  paralyzed: { bg: "bg-red-900/50", text: "text-red-400" },
  blinded: { bg: "bg-gray-800/50", text: "text-gray-400" },
  deafened: { bg: "bg-gray-800/50", text: "text-gray-400" },
  prone: { bg: "bg-amber-900/50", text: "text-amber-400" },
  restrained: { bg: "bg-orange-900/50", text: "text-orange-400" },
  incapacitated: { bg: "bg-red-900/50", text: "text-red-400" },
  unconscious: { bg: "bg-gray-900/60", text: "text-gray-500" },
  dead: { bg: "bg-gray-900/60", text: "text-gray-600" },
  invisible: { bg: "bg-blue-900/50", text: "text-blue-400", glow: "shadow-[0_0_4px_rgba(96,165,250,0.15)]" },
  concentrating: { bg: "bg-indigo-900/50", text: "text-indigo-400", glow: "shadow-[0_0_4px_rgba(129,140,248,0.15)]" },
};

export function ConditionBadge({ condition }: ConditionBadgeProps) {
  const style =
    CONDITION_STYLES[condition.toLowerCase()] ??
    { bg: "bg-yellow-900/50", text: "text-yellow-400" };
  return (
    <span
      className={`inline-block px-1.5 py-0.5 rounded text-[9px] font-display tracking-wider
        border border-current/10 ${style.bg} ${style.text} ${style.glow ?? ""}`}
    >
      {condition}
    </span>
  );
}
