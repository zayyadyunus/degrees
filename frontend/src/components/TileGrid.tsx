interface Props {
  tiles: string[];
  target: string;
  /** Words already in the chain: can't be played again. */
  used: Set<string>;
  hint: string | null;
  /** The tile that just cost a strike: it shakes. */
  struck: string | null;
  disabled?: boolean;
  onPlay: (word: string) => void;
}

/** The board's tiles: tap one to play it next. The target sits last. */
export function TileGrid({ tiles, target, used, hint, struck, disabled, onPlay }: Props) {
  return (
    <div className="tile-grid" role="group" aria-label="Word tiles">
      {[...tiles, target].map((word) => (
        <button
          key={word}
          className={
            "pick" +
            (word === target ? " target" : "") +
            (word === hint ? " hinted" : "") +
            (word === struck ? " struck" : "")
          }
          disabled={disabled || used.has(word)}
          onClick={() => onPlay(word)}
        >
          {word}
        </button>
      ))}
    </div>
  );
}
