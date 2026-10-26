import { Fragment } from "react";
import type { GameState } from "../types";

interface Props {
  game: GameState;
  /** Relation label per accepted edge: relations[i] joins path[i] → path[i+1]. */
  relations: (string | null)[];
  /** Current hint word (rendered as a ghost tile in the next open slot). */
  hint: string | null;
  onPlayHint: (word: string) => void;
}

// Humanize the typed-overlay relation names for connector captions.
const RELATION_LABELS: Record<string, string> = {
  Synonym: "same meaning",
  Antonym: "opposite",
  IsA: "is a kind of",
  SameCategory: "same category",
  PartOf: "part of",
  MadeOf: "made of",
  UsedFor: "used for",
  AtLocation: "found together",
  Causes: "leads to",
  HasProperty: "feature of",
  Related: "related",
};

function labelFor(relation: string | null | undefined): string | null {
  if (!relation) return null;
  return RELATION_LABELS[relation] ?? relation.toLowerCase();
}

/**
 * The vertical ladder: start word pinned on top, target pinned on the
 * bottom, the player's chain growing between them through dashed slots
 * that make the remaining budget visible.
 */
export function Board({ game, relations, hint, onPlayHint }: Props) {
  const inProgress = game.status === "in_progress";
  const won = game.status === "won";
  const lost = game.status === "lost";

  // Intermediate words exclude the start; on a win the final path word is
  // the target itself, which renders as the bottom tile instead of a slot.
  const steps = won ? game.path.slice(1, -1) : game.path.slice(1);

  // The last connection is reserved for reaching the target, so the open
  // intermediate slots are one fewer than the connections left.
  const showHint = inProgress && hint !== null;
  const emptyCount = inProgress
    ? Math.max(game.connections_left - 1 - (showHint ? 1 : 0), 0)
    : 0;

  const targetIndex = steps.length + (showHint ? 1 : 0) + 1;

  return (
    <div className={"board" + (won ? " won" : "")}>
      <div className="tile start" style={{ "--i": 0 } as React.CSSProperties}>
        {game.path[0]}
      </div>

      {steps.map((word, i) => (
        <Fragment key={`${word}-${i}`}>
          <Connector solid label={labelFor(relations[i])} />
          <div
            className={
              "tile played" +
              (inProgress && i === steps.length - 1 ? " current" : "")
            }
            style={{ "--i": i + 1 } as React.CSSProperties}
          >
            {word}
          </div>
        </Fragment>
      ))}

      {showHint && (
        <>
          <Connector />
          <button className="tile hint" onClick={() => onPlayHint(hint)}>
            ✦ {hint}
          </button>
        </>
      )}

      {Array.from({ length: emptyCount }, (_, i) => (
        <Fragment key={`slot-${i}`}>
          <Connector />
          <div className="slot" />
        </Fragment>
      ))}

      <Connector
        solid={won}
        pulse={inProgress}
        label={won ? labelFor(relations[relations.length - 1]) : null}
      />
      <div
        className={
          "tile target" + (won ? " reached" : "") + (lost ? " missed" : "")
        }
        style={{ "--i": targetIndex } as React.CSSProperties}
      >
        {game.target}
      </div>
    </div>
  );
}

function Connector({
  solid,
  pulse,
  label,
}: {
  solid?: boolean;
  pulse?: boolean;
  label?: string | null;
}) {
  return (
    <div
      className={
        "connector" + (solid ? " solid" : "") + (pulse ? " pulse" : "")
      }
    >
      <span className="connector-line" />
      {label && <span className="connector-label">{label}</span>}
    </div>
  );
}
