// Mirrors the backend pydantic schemas (app/models.py).

export type GameStatus = "in_progress" | "won" | "lost";

export type GameEvent = "move" | "strike" | "hint" | "back";

/** "classic" (par, move budget) or "sixtype" (six links, each type spent once). */
export type Rules = "classic" | "sixtype";

/** One of the six link types, e.g. { type: "kind", name: "kind of" }. */
export interface LinkType {
  type: string;
  name: string;
}

/** A link type a move could spend, with the sentence that explains it. */
export interface Choice extends LinkType {
  why: string;
}

export interface GameState {
  id: string;
  rules: Rules;
  start: string;
  target: string;
  current_word: string;
  path: string[];
  /** relations[i] names the edge path[i] → path[i+1]. */
  relations: string[];
  status: GameStatus;
  /** The board's middle tiles, in display order. */
  tiles: string[];
  /** Words in the chain now. */
  connections_used: number;
  /** Accepted moves, including taken-back ones: the score. */
  moves: number;
  /** Classic only: the move budget and what's left of it. */
  max_moves: number | null;
  connections_left: number | null;
  optimal_distance: number;
  strikes: number;
  max_strikes: number;
  hints_used: number;
  events: GameEvent[];
  daily_number: number | null;
  /** A par route; only present once the game is over. */
  solution: string[] | null;
  // Six-type only (null for classic games).
  /** spent[i] is the type link i spent; whys[i] the sentence explaining it. */
  spent?: string[] | null;
  whys?: string[] | null;
  /** Unspent types, in key order. */
  types_left?: LinkType[] | null;
  /** The intended route's types and sentences, once the game is over. */
  solution_types?: string[] | null;
  solution_whys?: string[] | null;
}

export interface MoveResponse {
  accepted: boolean;
  reason: string | null;
  similarity: number | null;
  relation: string | null;
  strike: boolean;
  /** Six-type: the type spent and why; or the choices when it fits several. */
  type?: string | null;
  why?: string | null;
  choices?: Choice[];
  game: GameState;
}

export interface HintResponse {
  hint: string | null;
  message: string | null;
  game: GameState;
}
