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
    /** The response's parsed `detail`, when the server sent JSON. */
    public detail?: unknown,
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
    const text = await res.text().catch(() => "");
    let detail: unknown;
    try {
      detail = JSON.parse(text).detail;
    } catch {
      // not JSON
    }
    throw new ApiError(res.status, `${res.status} ${res.statusText}${text ? `: ${text}` : ""}`, detail);
  }
  return res.json() as Promise<T>;
}

/** The player's local calendar date as YYYY-MM-DD (the daily rolls at local midnight). */
export function localDate(d = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Before launch the server has no daily yet; returns the first daily's date. */
export function dailyStartsOn(e: unknown): string | null {
  if (!(e instanceof ApiError) || e.status !== 404) return null;
  const d = e.detail as { error?: string; daily_starts?: string } | undefined;
  return d?.error === "no_daily_yet" && d.daily_starts ? d.daily_starts : null;
}

export const api = {
  dailyGame: (date: string) =>
    request<GameState>("/games", {
      method: "POST",
      body: JSON.stringify({ daily: true, date }),
    }),

  practiceGame: () => request<GameState>("/games", { method: "POST", body: "{}" }),

  getGame: (gameId: string) => request<GameState>(`/games/${gameId}`),

  /** `type` picks which link type to spend (six-type, when a link fits several). */
  submitMove: (gameId: string, word: string, type?: string) =>
    request<MoveResponse>(`/games/${gameId}/moves`, {
      method: "POST",
      body: JSON.stringify(type ? { word, type } : { word }),
    }),

  back: (gameId: string) =>
    request<GameState>(`/games/${gameId}/back`, { method: "POST" }),

  hint: (gameId: string) =>
    request<HintResponse>(`/games/${gameId}/hint`, { method: "POST" }),
};
