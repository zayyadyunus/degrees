import type { GameState, HintResponse, MoveResponse } from "./types";

// Dev talks to the local backend; production builds default to the same
// origin (the backend serves the UI). Override with VITE_API_URL at build time
// when the API lives elsewhere.
const BASE =
  import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : "");

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    if (res.status === 429) {
      throw new ApiError(429, "You're going a bit fast — wait a moment and try again.");
    }
    const detail = await res.text().catch(() => "");
    throw new ApiError(res.status, `${res.status} ${res.statusText}${detail ? `: ${detail}` : ""}`);
  }
  return res.json() as Promise<T>;
}

/** The player's local calendar date as YYYY-MM-DD (the daily rolls at local midnight). */
export function localDate(d = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export const api = {
  vocabulary: () => request<{ words: string[] }>("/vocabulary"),

  dailyGame: (date: string) =>
    request<GameState>("/games", {
      method: "POST",
      body: JSON.stringify({ daily: true, date }),
    }),

  practiceGame: () => request<GameState>("/games", { method: "POST", body: "{}" }),

  getGame: (gameId: string) => request<GameState>(`/games/${gameId}`),

  submitMove: (gameId: string, word: string) =>
    request<MoveResponse>(`/games/${gameId}/moves`, {
      method: "POST",
      body: JSON.stringify({ word }),
    }),

  hint: (gameId: string) =>
    request<HintResponse>(`/games/${gameId}/hint`, { method: "POST" }),
};
