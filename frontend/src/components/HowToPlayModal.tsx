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

export function HowToPlayModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  return (
    <Modal open={open} onClose={onClose} title="How to Play">
      <p className="howto-lede">
        Connect the <strong>start</strong> word to the <strong>target</strong>{" "}
        word in 6 associations or fewer. A new daily puzzle every day.
      </p>
      <ol className="howto-rules">
        <li>
          Each word you play must be closely associated with the word before
          it.
        </li>
        <li>Every accepted word uses one of your 6 connections.</li>
        <li>
          <strong>Par</strong> is the fewest connections possible. Match it for
          a ⛳.
        </li>
        <li>
          A real word that doesn’t connect is a <strong>strike</strong>. Three
          strikes and you’re out. Typos are free.
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
