const BASE = "/api";

export async function createSession(opts?: {
  characters?: unknown[];
  characters_json?: string;
  save_path?: string;
}) {
  const res = await fetch(`${BASE}/session/new`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(opts ?? {}),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to create session");
  }
  return res.json();
}

export async function loadSession(savePath: string) {
  const res = await fetch(`${BASE}/session/load`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ save_path: savePath }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to load session");
  }
  return res.json();
}

export async function searchCompendium(category: string, query: string) {
  const res = await fetch(
    `${BASE}/compendium/${category}?q=${encodeURIComponent(query)}`
  );
  return res.json();
}
