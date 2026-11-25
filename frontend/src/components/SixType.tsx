import type { Choice, GameState } from "../types";
import type { Mode } from "../storage";

/** The six link types in key order. Mirrors app/sixtype/links.py TYPES. */
export const SIX_TYPES: { type: string; name: string }[] = [
  { type: "kind", name: "kind of" },
  { type: "family", name: "same family" },
  { type: "part", name: "part of / made of" },
  { type: "feature", name: "share a feature" },
  { type: "use", name: "used for / makes" },
  { type: "found", name: "found with" },
];

export const CHAIN = 6;

export function typeName(type: string): string {
  return SIX_TYPES.find((t) => t.type === type)?.name ?? type;
}

interface BoardProps {
  game: GameState;
  /** The type a hint said to spend next: its key is outlined. */
  hintType: string | null;
  /** The tile that just cost a strike: it shakes. */
  struck: string | null;
  busy: boolean;
  onPlay: (word: string) => void;
  /** Keep the first n + 1 words of the chain (undoing the rest). */
  onBackTo: (n: number) => void;
  onHint: () => void;
}

/**
 * One screen: the prompt, the chain strip (start, five slots, target), the
 * latest link's sentence, the six type keys, the tiles, mistakes left and
 * Back / Hint. State is shown by fill (empty / filled / spent), not colour.
 */
export function SixTypeBoard({ game, hintType, struck, busy, onPlay, onBackTo, onHint }: BoardProps) {
  const path = game.path;
  const spent = game.spent ?? [];
  const whys = game.whys ?? [];
  const over = game.status !== "in_progress";
  const onPath = new Set(path);
  const n = spent.length;
  const targetLive = !over && path.length === CHAIN;

  const cells = [];
  for (let i = 0; i <= CHAIN; i++) {
    if (i > 0) cells.push(<li key={`sep-${i}`} className="st-sep" aria-hidden="true">›</li>);
    if (i === 0 || i === CHAIN) {
      const word = i === 0 ? game.start : game.target;
      const reached = i === CHAIN && game.status === "won";
      cells.push(
        <li key={i}>
          {i === CHAIN && targetLive ? (
            <button className="st-cell end live" onClick={() => onPlay(word)} disabled={busy}
              aria-label={`Play ${word}`}>
              {word}
            </button>
          ) : (
            <span className={"st-cell end" + (reached ? " reached" : "")}>{word}</span>
          )}
        </li>,
      );
    } else if (i < path.length) {
      const last = i === path.length - 1;
      cells.push(
        <li key={i}>
          {over ? (
            <span className="st-cell word">{path[i]}</span>
          ) : (
            <button className="st-cell word" disabled={busy}
              title={last ? "Take back" : "Go back to here"}
              aria-label={`${path[i]}: ${last ? "take back" : "go back to here"}`}
              onClick={() => onBackTo(last ? i - 1 : i)}>
              {path[i]}
            </button>
          )}
        </li>,
      );
    } else {
      cells.push(
        <li key={i}>
          <span className={"st-cell empty" + (i === path.length && !over ? " next" : "")} aria-label="empty" />
        </li>,
      );
    }
  }

  return (
    <div className="st">
      <p className="st-prompt">
        Connect <b>{game.start}</b> to <b>{game.target}</b> in {CHAIN} links
      </p>
      <ol className="st-chain" aria-label="Your chain">{cells}</ol>
      <p className="st-last" aria-live="polite">
        {n > 0 ? (
          <>
            <b>{typeName(spent[n - 1])}</b>
            {whys[n - 1]}
          </>
        ) : over ? null : (
          "Tap a tile that links to the last word in your chain."
        )}
      </p>

      <div className="st-keys" aria-label="Link types, each spent once">
        {SIX_TYPES.map(({ type, name }) => {
          const k = spent.indexOf(type);
          return (
            <div key={type}
              className={"st-key" + (k >= 0 ? " spent" : "") + (hintType === type ? " hint" : "")}
              aria-label={name + (k >= 0 ? ", spent" : "")}>
              {name}
              {k >= 0 && <small>{path[k]} – {path[k + 1]}</small>}
            </div>
          );
        })}
      </div>

      {!over && (
        <>
          <div className="st-tiles" role="group" aria-label="Word tiles">
            {game.tiles.map((w) => (
              <button key={w} className={"st-tile" + (w === struck ? " shake" : "")}
                disabled={busy || onPath.has(w)} onClick={() => onPlay(w)}>
                {w}
              </button>
            ))}
          </div>

          <div className="st-mistakes" aria-label={`${game.max_strikes - game.strikes} mistakes remaining`}>
            Mistakes remaining:
            {Array.from({ length: game.max_strikes }, (_, i) => (
              <i key={i} className={i < game.max_strikes - game.strikes ? "" : "gone"} />
            ))}
          </div>

          <div className="st-pills">
            <button className="st-pill" disabled={busy || path.length < 2} onClick={() => onBackTo(path.length - 2)}>
              Back
            </button>
            <button className="st-pill" disabled={busy} onClick={onHint}>
              Hint{game.hints_used > 0 && ` · ${game.hints_used} used`}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

/** The picker shown when a link fits more than one unspent type. */
export function TypeChoice({
  from,
  word,
  choices,
  onPick,
}: {
  from: string;
  word: string;
  choices: Choice[];
  onPick: (type: string) => void;
}) {
  return (
    <>
      <p className="howto-lede">
        <strong>{from} → {word}</strong> fits more than one type. Which will you spend?
      </p>
      <div className="st-choices">
        {choices.map((c) => (
          <button key={c.type} className="st-choice" onClick={() => onPick(c.type)}>
            <b>{c.name}</b>
            {c.why}
          </button>
        ))}
      </div>
    </>
  );
}

function Steps({ path, types, whys }: { path: string[]; types: string[]; whys: string[] }) {
  return (
    <ol className="st-steps">
      {types.map((t, i) => (
        <li key={i}>
          <b>{typeName(t)}</b>
          <span>{whys[i] ?? `${path[i]} → ${path[i + 1]}`}</span>
        </li>
      ))}
    </ol>
  );
}

const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;

export function SixTypeResult({
  game,
  mode,
  dailyAvailable,
  onShare,
  onPractice,
  onDaily,
}: {
  game: GameState;
  mode: Mode;
  dailyAvailable: boolean;
  onShare: () => void;
  onPractice: () => void;
  onDaily: () => void;
}) {
  const won = game.status === "won";
  const backs = game.events.filter((e) => e === "back").length;
  const clean = won && game.strikes === 0 && backs === 0 && game.hints_used === 0;
  const solution = game.solution ?? [];
  const yours = won && solution.join() === game.path.join();

  return (
    <div className="result-card st-result">
      <h2>{clean ? "Clean solve" : won ? "Connected!" : "Next time"}</h2>
      <p className="result-line">
        {won
          ? clean
            ? "No mistakes, backs or hints."
            : `${plural(game.strikes, "mistake")}, ${plural(backs, "back")}, ${plural(game.hints_used, "hint")}.`
          : `You made ${game.spent?.length ?? 0} of ${CHAIN} links.`}
      </p>
      {won && !yours && (
        <>
          <p className="howto-heading">Your chain</p>
          <Steps path={game.path} types={game.spent ?? []} whys={game.whys ?? []} />
        </>
      )}
      {solution.length > 0 && (
        <>
          <p className="howto-heading">{yours ? "Your chain: the intended route" : "The intended route"}</p>
          <Steps path={solution} types={game.solution_types ?? []} whys={game.solution_whys ?? []} />
        </>
      )}
      <div className="actions">
        <button className="btn primary" onClick={onShare}>Share</button>
        <button className="btn secondary" onClick={onPractice}>Practice puzzle</button>
        {mode === "practice" && dailyAvailable && (
          <button className="btn secondary" onClick={onDaily}>Today's puzzle</button>
        )}
      </div>
    </div>
  );
}
