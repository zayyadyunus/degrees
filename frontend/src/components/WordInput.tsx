import { useEffect, useMemo, useRef, useState } from "react";

interface Props {
  vocabulary: string[];
  used: Set<string>;
  disabled?: boolean;
  /** Resolves true when the move is accepted; false keeps the word for editing. */
  onSubmit: (word: string) => Promise<boolean>;
}

const MAX_SUGGESTIONS = 8;
// Autocomplete only fixes spelling: it waits for a few letters and only
// completes prefixes, so it can't be used to browse the word list.
const MIN_PREFIX = 3;

/** Free-text word entry with prefix autocomplete over the vocabulary. */
export function WordInput({ vocabulary, used, disabled, onSubmit }: Props) {
  const [value, setValue] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [shaking, setShaking] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const suggestions = useMemo(() => {
    const q = value.trim().toLowerCase();
    if (q.length < MIN_PREFIX) return [];
    const matches: string[] = [];
    for (const w of vocabulary) {
      if (used.has(w) || !w.startsWith(q)) continue;
      matches.push(w);
      if (matches.length >= MAX_SUGGESTIONS) break;
    }
    return matches;
  }, [value, vocabulary, used]);

  useEffect(() => setActive(0), [value]);

  async function commit(word: string) {
    const w = word.trim().toLowerCase();
    if (!w || submitting) return;
    setOpen(false);
    setSubmitting(true);
    const accepted = await onSubmit(w);
    setSubmitting(false);
    if (accepted) {
      setValue("");
    } else {
      // Keep the word so a typo can be fixed; shake to signal the rejection.
      setShaking(true);
    }
    inputRef.current?.focus();
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || suggestions.length === 0) {
      if (e.key === "Enter") void commit(value);
      return;
    }
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setActive((a) => (a + 1) % suggestions.length);
        break;
      case "ArrowUp":
        e.preventDefault();
        setActive((a) => (a - 1 + suggestions.length) % suggestions.length);
        break;
      case "Enter":
        e.preventDefault();
        void commit(suggestions[active] ?? value);
        break;
      case "Escape":
        setOpen(false);
        break;
    }
  }

  return (
    <div className="word-input">
      <div
        className={"entry-row" + (shaking ? " shake" : "")}
        onAnimationEnd={() => setShaking(false)}
      >
        <input
          ref={inputRef}
          type="text"
          value={value}
          disabled={disabled}
          autoFocus
          autoComplete="off"
          spellCheck={false}
          placeholder="next word…"
          onChange={(e) => {
            setValue(e.target.value);
            setOpen(true);
          }}
          onKeyDown={onKeyDown}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
        />
        <button
          className="btn primary"
          disabled={disabled || submitting || !value.trim()}
          onClick={() => void commit(value)}
        >
          Connect
        </button>
      </div>
      {open && suggestions.length > 0 && (
        <ul className="suggestions">
          {suggestions.map((s, i) => (
            <li
              key={s}
              className={i === active ? "active" : ""}
              onMouseDown={(e) => {
                e.preventDefault();
                void commit(s);
              }}
              onMouseEnter={() => setActive(i)}
            >
              {s}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
