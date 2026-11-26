import type { Rules } from "../types";
import { Modal } from "./Modal";

interface Relation {
  name: string;
  examples: string;
}

const RELATIONS: Relation[] = [
  { name: "Same meaning", examples: "sea ↔ ocean · film ↔ movie" },
  { name: "Opposite", examples: "hot ↔ cold · love ↔ hate" },
  { name: "Is a kind of", examples: "dog → animal · apple → fruit" },
  { name: "Same category", examples: "fork ↔ spoon · gold ↔ silver" },
  { name: "Part of", examples: "wheel → car · leaf → tree" },
  { name: "Made of", examples: "wine → grape · glass → sand" },
  { name: "Used for / does", examples: "hammer → nail · lamp → light" },
  { name: "Found together", examples: "bee → flower · sand → beach" },
  { name: "Leads to / from", examples: "fire → smoke · seed → tree" },
  { name: "Stands for", examples: "crown → king · heart → love" },
];

const EXAMPLE_CHAIN = ["night", "dark", "light", "sun"];

const SIX_TYPE_EXAMPLES: [string, string][] = [
  ["Kind of", "eagle → bird · violin → instrument"],
  ["Same family", "lion ↔ tiger · rain ↔ snow"],
  ["Part of / made of", "wheel → car · glass → sand"],
  ["Share a feature", "snow ↔ milk (both white)"],
  ["Used for / makes", "hammer → nail · bee → honey"],
  ["Found with", "fish → sea · star → sky"],
];

export function HowToPlayModal({
  open,
  onClose,
  rules = "classic",
}: {
  open: boolean;
  onClose: () => void;
  rules?: Rules;
}) {
  if (rules === "sixtype") {
    return (
      <Modal open={open} onClose={onClose} title="How to Play">
        <p className="howto-lede">
          Connect the <strong>start</strong> word to the <strong>target</strong> in{" "}
          <strong>six links</strong>: five words in between. A new puzzle every day.
        </p>
        <ol className="howto-rules">
          <li>Tap a tile that links to the last word in your chain.</li>
          <li>
            Every link is one of six types, and <strong>each type can be spent only once</strong>.
            If a link fits two unspent types, you choose which to spend.
          </li>
          <li>
            A tile that doesn’t link, or a link whose type is already spent, is a{" "}
            <strong>mistake</strong>. Three mistakes and the board is over.
          </li>
          <li>
            Tap a word in your chain, or <strong>Back</strong>, to undo. Its type comes back.
          </li>
          <li>A hint names the type to spend next. Hints show on your result.</li>
        </ol>
        <p className="howto-heading">The six types</p>
        <ul className="relation-list">
          {SIX_TYPE_EXAMPLES.map(([name, ex]) => (
            <li key={name}>
              <span className="relation-name">{name}</span>
              <span className="relation-ex">{ex}</span>
            </li>
          ))}
        </ul>
      </Modal>
    );
  }
  return (
    <Modal open={open} onClose={onClose} title="How to Play">
      <p className="howto-lede">
        Link the <strong>start</strong> word to the <strong>target</strong>{" "}
        using the tiles on the board. A new daily puzzle every day.
      </p>
      <ol className="howto-rules">
        <li>
          Tap a tile to add it to your chain. Each one must be closely
          associated with the word before it.
        </li>
        <li>
          <strong>Par</strong> is the fewest moves possible. Match it for a ⛳.
        </li>
        <li>
          Not every tile helps — some lead nowhere. <strong>Back</strong>{" "}
          undoes a step, but the move still counts.
        </li>
        <li>
          A tile that doesn’t connect is a <strong>strike</strong>. Three
          strikes and you’re out.
        </li>
        <li>Hints are always there, but they show on your result.</li>
      </ol>
      <div className="howto-example" aria-label="Example chain">
        {EXAMPLE_CHAIN.map((word, i) => (
          <span key={word} style={{ display: "contents" }}>
            {i > 0 && <span className="mini-arrow">→</span>}
            <span
              className={
                "mini-tile" +
                (i === 0 ? " first" : "") +
                (i === EXAMPLE_CHAIN.length - 1 ? " last" : "")
              }
            >
              {word}
            </span>
          </span>
        ))}
      </div>
      <p className="howto-heading">What counts as a connection</p>
      <p className="howto-lede" style={{ fontSize: "0.9rem" }}>
        Words connect when they relate in one of these ways, or are strongly
        associated for most people. Rhymes, spelling, and “it just reminds me
        of…” don’t count.
      </p>
      <ul className="relation-list">
        {RELATIONS.map((r) => (
          <li key={r.name}>
            <span className="relation-name">{r.name}</span>
            <span className="relation-ex">{r.examples}</span>
          </li>
        ))}
      </ul>
    </Modal>
  );
}
