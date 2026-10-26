// Mirrors the backend pydantic schemas (app/models.py).

export type GameStatus = "in_progress" | "won" | "lost";

export interface GameState {
  id: string;
  start: string;
  target: string;
  current_word: string;
  path: string[];
  status: GameStatus;
  connections_used: number;
  connections_left: number;
  max_connections: number;
  optimal_distance: number;
}

export interface MoveResponse {
  accepted: boolean;
  reason: string | null;
  similarity: number | null;
  relation: string | null;
  game: GameState;
}

export interface HintResponse {
  hint: string | null;
  message: string | null;
}

export interface ScoreResponse {
  status: GameStatus;
  connections_used: number;
  optimal_distance: number;
  over_optimal: number | null;
  is_optimal: boolean;
}
