import { useGameStore } from "../../store/gameStore";
import { CharacterCard } from "./CharacterCard";

export function PartyTab() {
  const characters = useGameStore((s) => s.characters);

  if (characters.length === 0) {
    return (
      <p className="text-sm text-text-mechanical italic p-2">
        No characters loaded.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {characters.map((c) => (
        <CharacterCard key={c.id} character={c} />
      ))}
    </div>
  );
}
