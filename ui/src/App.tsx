import { useCallback, useEffect, useState } from "react";
import { connectWebSocket, disconnectWebSocket } from "./api/websocket";
import { createSession, loadSession } from "./api/rest";
import { useGameStore } from "./store/gameStore";
import { HeaderBar } from "./components/layout/HeaderBar";
import { MainLayout } from "./components/layout/MainLayout";
import { InputBar } from "./components/layout/InputBar";
import { CombatOverlay } from "./components/combat/CombatOverlay";
import { CharacterSheetModal } from "./components/character/CharacterSheetModal";
import { InventoryDrawer } from "./components/character/InventoryDrawer";

function App() {
  const sessionActive = useGameStore((s) => s.sessionActive);
  const connected = useGameStore((s) => s.connected);
  const mode = useGameStore((s) => s.mode);
  const inspectedCharacterId = useGameStore((s) => s.inspectedCharacterId);
  const inventoryDrawerCharacterId = useGameStore(
    (s) => s.inventoryDrawerCharacterId
  );

  const [setupState, setSetupState] = useState<
    "idle" | "loading" | "error"
  >("idle");
  const [errorMsg, setErrorMsg] = useState("");

  // Close modals on Escape
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        const store = useGameStore.getState();
        if (store.inspectedCharacterId) {
          store.setInspectedCharacter(null);
        } else if (store.inventoryDrawerCharacterId) {
          store.setInventoryDrawer(null);
        }
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const startNewGame = useCallback(async () => {
    setSetupState("loading");
    setErrorMsg("");
    try {
      await createSession();
      connectWebSocket();
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : String(e));
      setSetupState("error");
    }
  }, []);

  const loadGame = useCallback(async () => {
    setSetupState("loading");
    setErrorMsg("");
    try {
      await loadSession("saves/autosave.json");
      connectWebSocket();
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : String(e));
      setSetupState("error");
    }
  }, []);

  // Cleanup
  useEffect(() => {
    return () => disconnectWebSocket();
  }, []);

  // Session setup screen — dramatic title
  if (!sessionActive) {
    return (
      <div className="relative flex items-center justify-center min-h-screen bg-atmosphere overflow-hidden">
        {/* Ambient glow orbs */}
        <div className="absolute inset-0 pointer-events-none overflow-hidden">
          <div className="absolute top-1/4 left-1/4 w-96 h-96 rounded-full bg-magic/5 blur-[120px] animate-pulse-glow" />
          <div className="absolute bottom-1/3 right-1/4 w-80 h-80 rounded-full bg-accent/5 blur-[100px] animate-pulse-glow" style={{ animationDelay: '1s' }} />
          <div className="absolute top-1/2 left-1/2 w-64 h-64 rounded-full bg-gold/5 blur-[80px] animate-pulse-glow" style={{ animationDelay: '0.5s' }} />
        </div>

        {/* Vignette */}
        <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(ellipse_at_center,transparent_30%,rgba(0,0,0,0.6)_100%)]" />

        <div className="relative z-10 text-center max-w-md p-8 animate-slide-up">
          {/* Decorative top rule */}
          <div className="flex items-center justify-center gap-3 mb-6 opacity-40">
            <div className="h-px w-16 bg-gradient-to-r from-transparent to-gold-dim" />
            <span className="text-gold-dim text-[10px] tracking-[0.3em] font-display">✦</span>
            <div className="h-px w-16 bg-gradient-to-l from-transparent to-gold-dim" />
          </div>

          {/* Title */}
          <h1 className="font-display-decorative text-3xl text-gold text-glow-gold tracking-[0.15em] mb-2">
            DUNGEON WEAVER
          </h1>
          <p className="font-display text-[11px] tracking-[0.25em] text-text-mechanical uppercase mb-1">
            Tales Spun in Shadow & Flame
          </p>

          {/* Decorative bottom rule */}
          <div className="flex items-center justify-center gap-3 mt-4 mb-10 opacity-40">
            <div className="h-px w-24 bg-gradient-to-r from-transparent to-gold-dim" />
            <span className="text-gold-dim text-[8px] tracking-[0.3em] font-display">◆ ◆ ◆</span>
            <div className="h-px w-24 bg-gradient-to-l from-transparent to-gold-dim" />
          </div>

          {/* Action buttons */}
          <div className="space-y-3">
            <button
              onClick={startNewGame}
              disabled={setupState === "loading"}
              className="group w-full px-6 py-3.5 rounded-lg btn-primary font-display text-sm tracking-wider
                relative overflow-hidden"
            >
              <span className="relative z-10">
                {setupState === "loading" ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="inline-block w-3 h-3 border border-accent/50 border-t-accent rounded-full animate-spin" />
                    Weaving...
                  </span>
                ) : "Begin New Tale"}
              </span>
            </button>
            <button
              onClick={loadGame}
              disabled={setupState === "loading"}
              className="w-full px-6 py-3.5 rounded-lg btn-ghost font-display text-sm tracking-wider"
            >
              Continue Journey
            </button>
          </div>

          {/* Error */}
          {errorMsg && (
            <div className="mt-4 px-4 py-2 rounded-lg bg-danger/10 border border-danger/20">
              <p className="text-xs text-danger">{errorMsg}</p>
            </div>
          )}

          {/* Connection status */}
          {connected && (
            <div className="mt-4 flex items-center justify-center gap-2">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-heal shadow-[0_0_6px_var(--color-heal)]" />
              <span className="text-[10px] text-heal tracking-wider font-display">CONNECTED</span>
            </div>
          )}

          {/* Bottom flavor text */}
          <p className="mt-12 text-[10px] text-text-mechanical/50 italic font-['Crimson_Text',serif] tracking-wide">
            "The loom awaits. Threads of fate are yet unspun."
          </p>
        </div>
      </div>
    );
  }

  // Game UI
  return (
    <div className="flex flex-col h-screen bg-atmosphere">
      {mode === "combat" ? <CombatOverlay /> : <HeaderBar />}
      <MainLayout />
      <InputBar />

      {/* Overlays */}
      {inspectedCharacterId && <CharacterSheetModal />}
      {inventoryDrawerCharacterId && <InventoryDrawer />}
    </div>
  );
}

export default App;
