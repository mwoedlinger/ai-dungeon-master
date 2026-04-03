interface MechanicalEventProps {
  eventType: string;
  data: Record<string, unknown>;
}

export function MechanicalEvent({ eventType, data }: MechanicalEventProps) {
  const inputs = (data.inputs ?? {}) as Record<string, unknown>;
  const result = (data.result ?? {}) as Record<string, unknown>;

  switch (eventType) {
    case "attack":
      return <AttackEvent inputs={inputs} result={result} />;
    case "roll_dice":
      return <RollDiceEvent inputs={inputs} result={result} />;
    case "cast_spell":
      return <CastSpellEvent inputs={inputs} result={result} />;
    case "ability_check":
      return <CheckEvent label="check" inputs={inputs} result={result} />;
    case "saving_throw":
      return <CheckEvent label="save" inputs={inputs} result={result} />;
    default:
      return <GenericEvent eventType={eventType} result={result} />;
  }
}

function EventWrapper({
  children,
  variant = "default",
}: {
  children: React.ReactNode;
  variant?: "default" | "crit" | "spell";
}) {
  const borderColor = {
    default: "border-border/50",
    crit: "border-crit/40",
    spell: "border-magic/40",
  }[variant];

  const bgColor = {
    default: "bg-surface/50",
    crit: "bg-crit/5",
    spell: "bg-magic/5",
  }[variant];

  return (
    <div className={`my-2 px-3 py-2 rounded-md border-l-2 ${borderColor} ${bgColor} animate-fade-in`}>
      {children}
    </div>
  );
}

function AttackEvent({
  inputs,
  result,
}: {
  inputs: Record<string, unknown>;
  result: Record<string, unknown>;
}) {
  const attacker = (result.attacker ?? inputs.attacker_id ?? "?") as string;
  const target = (result.target ?? inputs.target_id ?? "?") as string;
  const total = String(result.total_attack ?? "?");
  const ac = String(result.target_ac ?? "?");
  const hits = result.hits as boolean;
  const isCrit = result.is_crit as boolean;
  const damage = result.damage as number | undefined;
  const damageType = (result.damage_type ?? "") as string;
  const hpRemaining = result.hp_remaining as number | undefined;

  if (isCrit) {
    return (
      <EventWrapper variant="crit">
        <div className="font-mono text-xs">
          <span className="text-crit font-bold text-glow-danger">★ CRITICAL HIT</span>
          <span className="text-text-mechanical ml-2">
            {attacker} → {target}
          </span>
        </div>
        <div className="font-mono text-xs text-text-mechanical mt-1">
          d20 = <span className="text-text-primary font-bold animate-dice-bounce inline-block">{total}</span> vs AC {ac}
          {damage != null && (
            <span className="ml-2">
              — <span className="text-danger font-bold">{damage}</span> {damageType}
              {hpRemaining != null && <span className="text-text-mechanical"> → {hpRemaining} HP</span>}
            </span>
          )}
        </div>
      </EventWrapper>
    );
  }

  const hitColor = hits ? "text-heal" : "text-danger";
  const hitIcon = hits ? "✓" : "✗";

  return (
    <div className="my-1.5 px-3 py-1.5 font-mono text-xs text-text-mechanical animate-fade-in">
      <span className="text-gold-dim/60">⚔</span>{" "}
      <span className="text-text-secondary">{attacker}</span>
      <span className="text-text-mechanical/40"> → </span>
      <span className="text-text-secondary">{target}</span>
      <span className="text-text-mechanical/40"> : </span>
      <span className="text-gold font-bold">{total}</span> vs AC {ac}{" "}
      <span className={hitColor}>{hitIcon}</span>
      {damage != null && (
        <span>
          {" "}— <span className="text-danger font-bold">{damage}</span> {damageType}
          {hpRemaining != null && <span> → {hpRemaining} HP</span>}
        </span>
      )}
    </div>
  );
}

function RollDiceEvent({
  inputs,
  result,
}: {
  inputs: Record<string, unknown>;
  result: Record<string, unknown>;
}) {
  const expr = (inputs.dice_expr ?? "?") as string;
  const reason = inputs.reason as string | undefined;
  const total = result.total ?? "?";
  const rolls = (result.rolls ?? []) as number[];
  const mod = (result.modifier ?? 0) as number;
  const rollStr = rolls.join("+");
  const modStr = mod ? (mod > 0 ? `+${mod}` : `${mod}`) : "";

  return (
    <div className="my-1.5 px-3 py-1.5 font-mono text-xs text-text-mechanical animate-fade-in">
      <span className="text-gold-dim/60">⊞</span>{" "}
      {reason && <span className="text-text-secondary">{reason}: </span>}
      <span className="text-gold">{expr}</span>
      <span className="text-text-mechanical/40"> → </span>
      [{rollStr}]{modStr} ={" "}
      <span className="text-text-primary font-bold animate-dice-bounce inline-block">{String(total)}</span>
    </div>
  );
}

function CastSpellEvent({
  inputs,
  result,
}: {
  inputs: Record<string, unknown>;
  result: Record<string, unknown>;
}) {
  const spell = (result.spell ?? inputs.spell_name ?? "?") as string;
  const success = result.success as boolean;
  const targets = (result.targets ?? []) as Record<string, unknown>[];
  const healed = result.healed as number | undefined;

  if (!success) {
    return (
      <div className="my-1.5 px-3 py-1.5 font-mono text-xs text-text-mechanical animate-fade-in">
        <span className="text-magic/60">✦</span>{" "}
        <span className="text-magic">{spell}</span>
        <span className="text-text-mechanical/40"> — </span>
        <span className="text-danger">fizzled</span>
      </div>
    );
  }

  return (
    <EventWrapper variant="spell">
      <div className="font-mono text-xs">
        <span className="text-magic font-bold text-glow-magic">✦ {spell}</span>
      </div>
      {targets.map((t, i) => (
        <div key={i} className="font-mono text-xs text-text-mechanical mt-0.5">
          <span className="text-text-secondary">{t.target as string}</span>
          <span className="text-text-mechanical/40">: </span>
          <span className="text-danger font-bold">{t.damage as number}</span> dmg
          {t.hp_remaining != null && (
            <span> → {t.hp_remaining as number} HP</span>
          )}
        </div>
      ))}
      {healed != null && (
        <div className="font-mono text-xs text-heal mt-0.5">
          Healed: <span className="font-bold">{healed}</span> HP
        </div>
      )}
    </EventWrapper>
  );
}

function CheckEvent({
  label,
  inputs,
  result,
}: {
  label: string;
  inputs: Record<string, unknown>;
  result: Record<string, unknown>;
}) {
  const skill = (inputs.skill ?? inputs.ability ?? "?") as string;
  const char = (inputs.character_id ?? "?") as string;
  const total = result.total ?? "?";
  const dc = result.dc ?? "?";
  const success = result.success as boolean;
  const mark = success ? "✓" : "✗";
  const color = success ? "text-heal" : "text-danger";

  return (
    <div className="my-1.5 px-3 py-1.5 font-mono text-xs text-text-mechanical animate-fade-in">
      <span className="text-gold-dim/60">⊞</span>{" "}
      <span className="text-text-secondary">{char}</span>{" "}
      <span className="text-gold/80">{skill}</span> {label}
      <span className="text-text-mechanical/40">: </span>
      <span className="text-text-primary font-bold">{String(total)}</span> vs DC{" "}
      {String(dc)} <span className={`font-bold ${color}`}>{mark}</span>
    </div>
  );
}

function GenericEvent({
  eventType,
  result,
}: {
  eventType: string;
  result: Record<string, unknown>;
}) {
  if (!result.success) return null;
  return (
    <div className="my-1.5 px-3 py-1.5 font-mono text-xs text-text-mechanical animate-fade-in">
      <span className="text-gold-dim/60">⚙</span>{" "}
      <span className="text-text-secondary">{eventType}</span>
    </div>
  );
}
