// Mirrors the backend pydantic schemas (app/models.py).

export type GameStatus = "in_progress" | "won" | "lost";

export type GameEvent = "move" | "strike" | "hint";

export interface GameState {
  id: string;
  start: string;
  target: string;
  current_word: string;
  path: string[];
  /** relations[i] names the edge path[i] → path[i+1]. */
  relations: string[];
  status: GameStatus;
  connections_used: number;
  connections_left: number;
  max_connections: number;
  optimal_distance: number;
  strikes: number;
  max_strikes: number;
  hints_used: number;
  events: GameEvent[];
  daily_number: number | null;
  /** A par route; only present once the game is over. */
  solution: string[] | null;
}

export interface MoveResponse {
  accepted: boolean;
  reason: string | null;
  similarity: number | null;
  relation: string | null;
  strike: boolean;
  game: GameState;
}

export interface HintResponse {
  hint: string | null;
  message: string | null;
  game: GameState;
}
