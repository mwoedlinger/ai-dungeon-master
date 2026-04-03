import { useGameStore } from "../../store/gameStore";

export function InventoryDrawer() {
  const charId = useGameStore((s) => s.inventoryDrawerCharacterId);
  const characters = useGameStore((s) => s.characters);
  const close = () => useGameStore.getState().setInventoryDrawer(null);

  const char = characters.find((c) => c.id === charId);
  if (!char) return null;

  const hasEquipment =
    char.weapons.length > 0 ||
    char.armor != null ||
    char.shield ||
    char.attuned_items.length > 0;

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-[1px]"
      onClick={close}
    >
      <div
        className="w-80 h-full overflow-y-auto bg-surface-elevated border-l border-border-ornate p-5
          shadow-[-8px_0_40px_rgba(0,0,0,0.4)] animate-slide-in-right"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-sm font-display font-bold tracking-wide text-gold">
            {char.name}
          </h2>
          <button
            onClick={close}
            className="text-text-mechanical hover:text-text-primary transition-colors p-1"
          >
            ✕
          </button>
        </div>
        <p className="text-[9px] font-display tracking-[0.2em] text-text-mechanical uppercase mb-4">
          Inventory
        </p>

        {/* Gold */}
        <div className="mb-4 flex items-center gap-2 text-xs">
          <span className="text-gold/60">●</span>
          <span className="font-mono text-gold">{char.gold}</span>
          <span className="text-text-mechanical">gold pieces</span>
        </div>

        {/* Equipped */}
        {hasEquipment && (
          <div className="mb-5">
            <h3 className="text-[9px] font-display font-semibold tracking-[0.2em] text-accent/70 mb-2.5 uppercase">
              Equipped
            </h3>
            <div className="space-y-1.5">
              {char.weapons.map((w, i) => (
                <InventoryItem
                  key={`w-${i}`}
                  icon="⚔"
                  iconColor="text-danger/60"
                  name={w.name}
                  detail={`${w.damage_dice} ${w.damage_type}${w.properties.length > 0 ? ` (${w.properties.join(", ")})` : ""}`}
                />
              ))}
              {char.armor && (
                <InventoryItem
                  icon="◇"
                  iconColor="text-accent/60"
                  name={char.armor.name}
                  detail={`AC ${char.armor.base_ac} (${char.armor.armor_type})${char.armor.stealth_disadvantage ? " • stealth disadv." : ""}`}
                />
              )}
              {char.shield && (
                <InventoryItem
                  icon="◇"
                  iconColor="text-accent/60"
                  name="Shield"
                  detail="+2 AC"
                />
              )}
              {char.attuned_items.map((m, i) => (
                <InventoryItem
                  key={`m-${i}`}
                  icon="✦"
                  iconColor="text-magic/60"
                  name={m.name}
                  detail={`${m.rarity}${m.bonus > 0 ? ` +${m.bonus}` : ""}${m.requires_attunement ? " • attuned" : ""}`}
                  magical
                />
              ))}
            </div>
          </div>
        )}

        {/* Bag contents */}
        <div>
          <h3 className="text-[9px] font-display font-semibold tracking-[0.2em] text-accent/70 mb-2.5 uppercase">
            Bag
          </h3>
          {char.inventory.length === 0 ? (
            <p className="text-xs text-text-mechanical/40 italic font-['Crimson_Text',serif]">
              Nothing but dust and shadow.
            </p>
          ) : (
            <div className="space-y-1">
              {char.inventory.map((item, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between px-2.5 py-1.5 rounded-md
                    bg-bg/40 border border-border-subtle
                    hover:border-border/60 transition-colors"
                >
                  <span className="text-xs text-text-primary">{item.name}</span>
                  <span className="text-[10px] text-text-mechanical font-mono">
                    {item.quantity > 1 && `×${item.quantity} `}
                    {item.weight > 0 && `${item.weight} lb`}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function InventoryItem({
  icon,
  iconColor,
  name,
  detail,
  magical = false,
}: {
  icon: string;
  iconColor: string;
  name: string;
  detail: string;
  magical?: boolean;
}) {
  return (
    <div className={`flex items-start gap-2 px-2.5 py-2 rounded-md
      bg-bg/40 border ${magical ? "border-magic/15" : "border-border-subtle"}
      hover:border-border/60 transition-colors`}
    >
      <span className={`${iconColor} text-xs mt-0.5`}>{icon}</span>
      <div className="flex-1 min-w-0">
        <div className={`text-xs ${magical ? "text-magic" : "text-text-primary"}`}>
          {name}
        </div>
        <div className="text-[10px] text-text-mechanical">{detail}</div>
      </div>
    </div>
  );
}
