import type { GameState } from "./types";

const EMOJI = { move: "🟩", strike: "🟥", hint: "💡", back: "↩️" } as const;

/**
 * Spoiler-free result text, e.g.
 *
 *   Degrees #12  4/4 ⛳
 *   🟩🟥🟩💡🟩🟩
 *   https://degrees.example
 */
export function shareText(game: GameState, url: string): string {
  const title = game.daily_number ? `Degrees #${game.daily_number}` : "Degrees (practice)";
  const used = game.moves;
  const par = game.optimal_distance;
  let score: string;
  if (game.status === "won") {
    // ⛳ is for par without help; hints already show in the grid.
    score = used === par ? `${used}/${par}${game.hints_used === 0 ? " ⛳" : ""}` : `${used} (par ${par})`;
  } else {
    score = `X (par ${par})`;
  }
  const grid = game.events.map((e) => EMOJI[e]).join("");
  return `${title}  ${score}\n${grid}\n${url}`;
}

/** Native share sheet on touch devices, else copy to clipboard. */
export async function share(text: string): Promise<"shared" | "copied" | "failed"> {
  // Desktop browsers may support navigator.share too, but players there
  // expect a copy they can paste.
  const touch = window.matchMedia?.("(pointer: coarse)").matches;
  if (touch && navigator.share) {
    try {
      await navigator.share({ text });
      return "shared";
    } catch (e) {
      // User dismissed the sheet: not an error worth a fallback.
      if (e instanceof DOMException && e.name === "AbortError") return "shared";
    }
  }
  try {
    await navigator.clipboard.writeText(text);
    return "copied";
  } catch {
    return "failed";
  }
}
