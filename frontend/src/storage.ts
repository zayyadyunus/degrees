// Small persistence helpers. localStorage can throw (private mode, blocked
// storage); everything here is a nicety, so failures read as "nothing saved".

const SEEN_HELP_KEY = "degrees:seen-help";
const CURRENT_KEY = "degrees:current";
const dailyKey = (date: string) => `degrees:daily:${date}`;

export type Mode = "daily" | "practice";

export interface SavedGame {
  mode: Mode;
  id: string;
}

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // ignore
  }
}

export function hasSeenHelp(): boolean {
  return read(SEEN_HELP_KEY) !== null;
}

export function markHelpSeen() {
  write(SEEN_HELP_KEY, "1");
}

/** The game on screen, so a refresh resumes it. */
export function loadCurrent(): SavedGame | null {
  try {
    const parsed = JSON.parse(read(CURRENT_KEY) ?? "null");
    return parsed && typeof parsed.id === "string" ? parsed : null;
  } catch {
    return null;
  }
}

export function saveCurrent(game: SavedGame) {
  write(CURRENT_KEY, JSON.stringify(game));
}

/** The game id for a given day's daily puzzle, so it can't be re-rolled. */
export function loadDaily(date: string): string | null {
  return read(dailyKey(date));
}

export function saveDaily(date: string, id: string) {
  write(dailyKey(date), id);
}
