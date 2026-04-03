import { useGameStore } from "../store/gameStore";
import type { GameStateSnapshot, TurnPrompt } from "../store/types";

let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

export function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${protocol}//${window.location.host}/api/ws`;

  ws = new WebSocket(url);

  ws.onopen = () => {
    useGameStore.getState().setConnected(true);
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  };

  ws.onclose = () => {
    useGameStore.getState().setConnected(false);
    ws = null;
    reconnectTimer = setTimeout(() => connectWebSocket(), 2000);
  };

  ws.onerror = () => {
    ws?.close();
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleMessage(msg);
    } catch {
      console.error("Failed to parse WebSocket message:", event.data);
    }
  };
}

function handleMessage(msg: Record<string, unknown>) {
  const store = useGameStore.getState();

  switch (msg.type) {
    case "narrative_chunk":
      store.appendNarrativeChunk(msg.text as string);
      break;

    case "narrative_end":
      store.finalizeNarrative();
      break;

    case "event":
      store.addEventMessage(
        msg.event_type as string,
        msg.data as Record<string, unknown>
      );
      break;

    case "state_update":
      store.applyStateUpdate(msg.payload as GameStateSnapshot);
      break;

    case "mode_change":
      store.setMode(msg.mode as "exploration" | "combat");
      break;

    case "turn_prompt":
      store.setCurrentTurn(msg as unknown as TurnPrompt);
      break;

    case "location_change":
      // Handled via state_update
      break;

    case "command_result":
      // Could show a toast notification
      break;

    case "error":
      console.error("Server error:", msg.message);
      break;
  }
}

export function sendPlayerInput(text: string) {
  if (ws?.readyState === WebSocket.OPEN) {
    useGameStore.getState().addPlayerMessage(text);
    ws.send(JSON.stringify({ type: "player_input", text }));
  }
}

export function sendCommand(name: string, args = "") {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "command", name, args }));
  }
}

export function disconnectWebSocket() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  ws?.close();
  ws = null;
}

export function isConnected(): boolean {
  return ws?.readyState === WebSocket.OPEN;
}
