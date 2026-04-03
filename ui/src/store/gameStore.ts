import { create } from "zustand";
import type {
  Character,
  CombatState,
  WorldState,
  WorldJournal,
  NarrativeMessage,
  TurnPrompt,
  GameStateSnapshot,
} from "./types";

interface GameStore {
  // Connection
  connected: boolean;
  sessionActive: boolean;

  // Game state (from server state_update pushes)
  characters: Character[];
  combat: CombatState | null;
  world: WorldState | null;
  journal: WorldJournal | null;
  mode: "exploration" | "combat";
  currentTurn: TurnPrompt | null;

  // Narrative
  messages: NarrativeMessage[];
  streamingBuffer: string;
  isStreaming: boolean;

  // UI state
  sidebarTab: "party" | "map" | "quests" | "journal" | "compendium";
  inspectedCharacterId: string | null;
  inventoryDrawerCharacterId: string | null;

  // Actions
  setConnected: (v: boolean) => void;
  setSessionActive: (v: boolean) => void;
  applyStateUpdate: (snapshot: GameStateSnapshot) => void;
  appendNarrativeChunk: (text: string) => void;
  finalizeNarrative: () => void;
  addEventMessage: (eventType: string, data: Record<string, unknown>) => void;
  addPlayerMessage: (text: string) => void;
  setMode: (mode: "exploration" | "combat") => void;
  setCurrentTurn: (turn: TurnPrompt | null) => void;
  setSidebarTab: (tab: GameStore["sidebarTab"]) => void;
  setInspectedCharacter: (id: string | null) => void;
  setInventoryDrawer: (id: string | null) => void;
}

export const useGameStore = create<GameStore>((set) => ({
  connected: false,
  sessionActive: false,
  characters: [],
  combat: null,
  world: null,
  journal: null,
  mode: "exploration",
  currentTurn: null,
  messages: [],
  streamingBuffer: "",
  isStreaming: false,
  sidebarTab: "party",
  inspectedCharacterId: null,
  inventoryDrawerCharacterId: null,

  setConnected: (v) => set({ connected: v }),
  setSessionActive: (v) => set({ sessionActive: v }),

  applyStateUpdate: (snapshot) =>
    set({
      characters: snapshot.characters,
      combat: snapshot.combat,
      world: snapshot.world,
      journal: snapshot.journal,
      mode: snapshot.mode as "exploration" | "combat",
      currentTurn: snapshot.current_turn,
      sessionActive: true,
    }),

  appendNarrativeChunk: (text) =>
    set((s) => ({
      streamingBuffer: s.streamingBuffer + text,
      isStreaming: true,
    })),

  finalizeNarrative: () =>
    set((s) => {
      if (!s.streamingBuffer) return { isStreaming: false };
      const msg: NarrativeMessage = {
        id: crypto.randomUUID(),
        type: "prose",
        text: s.streamingBuffer,
        timestamp: Date.now(),
      };
      return {
        messages: [...s.messages, msg],
        streamingBuffer: "",
        isStreaming: false,
      };
    }),

  addEventMessage: (eventType, data) =>
    set((s) => ({
      messages: [
        ...s.messages,
        {
          id: crypto.randomUUID(),
          type: "event",
          text: "",
          eventType,
          eventData: data,
          timestamp: Date.now(),
        },
      ],
    })),

  addPlayerMessage: (text) =>
    set((s) => ({
      messages: [
        ...s.messages,
        {
          id: crypto.randomUUID(),
          type: "player_input",
          text,
          timestamp: Date.now(),
        },
      ],
    })),

  setMode: (mode) => {
    set({ mode });
    if (mode === "combat") set({ sidebarTab: "party" });
  },
  setCurrentTurn: (turn) => set({ currentTurn: turn }),
  setSidebarTab: (tab) => set({ sidebarTab: tab }),
  setInspectedCharacter: (id) => set({ inspectedCharacterId: id }),
  setInventoryDrawer: (id) => set({ inventoryDrawerCharacterId: id }),
}));
