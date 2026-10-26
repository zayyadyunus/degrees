interface Props {
  onHelp: () => void;
  onNewGame: () => void;
}

export function Header({ onHelp, onNewGame }: Props) {
  return (
    <header className="appbar">
      <div className="appbar-side left" />
      <h1 className="wordmark">Degrees</h1>
      <div className="appbar-side right">
        <button
          className="icon-btn"
          aria-label="New puzzle"
          title="New puzzle"
          onClick={onNewGame}
        >
          <RefreshIcon />
        </button>
        <button
          className="icon-btn"
          aria-label="How to play"
          title="How to play"
          onClick={onHelp}
        >
          <HelpIcon />
        </button>
      </div>
    </header>
  );
}

function HelpIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="12" r="9.25" />
      <path
        d="M9.4 9.3a2.7 2.7 0 0 1 5.3.7c0 1.8-2.7 2.2-2.7 3.7"
        strokeLinecap="round"
      />
      <circle cx="12" cy="17" r="1.1" fill="currentColor" stroke="none" />
    </svg>
  );
}

function RefreshIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path
        d="M20 12a8 8 0 1 1-2.34-5.66M20 4v4h-4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
