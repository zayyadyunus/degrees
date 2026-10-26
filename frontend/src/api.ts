import type {
  GameState,
  HintResponse,
  MoveResponse,
  ScoreResponse,
} from "./types";

// Dev talks to the local backend; production builds default to the same
// origin (the backend serves the UI). Override with VITE_API_URL at build time
// when the API lives elsewhere.
const BASE =
  import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${detail ? `: ${detail}` : ""}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  vocabulary: () => request<{ words: string[] }>("/vocabulary"),

  newGame: () =>
    request<GameState>("/games", { method: "POST", body: "{}" }),

  submitMove: (gameId: string, word: string) =>
    request<MoveResponse>(`/games/${gameId}/moves`, {
      method: "POST",
      body: JSON.stringify({ word }),
    }),

  hint: (gameId: string) => request<HintResponse>(`/games/${gameId}/hint`),

  score: (gameId: string) => request<ScoreResponse>(`/games/${gameId}/score`),
};
