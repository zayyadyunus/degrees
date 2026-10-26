import { useCallback, useEffect, useMemo, useState } from "react";
import { api, localDate } from "./api";
import type { GameState } from "./types";
import { Header } from "./components/Header";
import { Board } from "./components/Board";
import { WordInput } from "./components/WordInput";
import { Toast, type ToastData } from "./components/Toast";
import { HowToPlayModal } from "./components/HowToPlayModal";
import { Modal } from "./components/Modal";
import {
  hasSeenHelp,
  loadCurrent,
  loadDaily,
  markHelpSeen,
  saveCurrent,
  saveDaily,
  type Mode,
} from "./storage";
import { share, shareText } from "./share";

function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export default function App() {
  const [vocabulary, setVocabulary] = useState<string[]>([]);
  const [game, setGame] = useState<GameState | null>(null);
  const [mode, setMode] = useState<Mode>("daily");
  const [hint, setHint] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastData | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  const [confirmNew, setConfirmNew] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function showToast(text: string) {
    setToast({ id: Date.now(), text });
  }

  // Auto-dismiss the toast.
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2400);
    return () => clearTimeout(t);
  }, [toast]);

  /** Swap in a game and remember it so a refresh resumes it. */
  const show = useCallback((next: GameState, nextMode: Mode) => {
    setGame(next);
    setMode(nextMode);
    setHint(null);
    setToast(null);
    setError(null);
    saveCurrent({ mode: nextMode, id: next.id });
  }, []);

  const withBusy = useCallback(async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }, []);

  /** Today's daily: resume the saved game for this date, else start it. */
  const openDaily = useCallback(
    () =>
      withBusy(async () => {
        const date = localDate();
        const savedId = loadDaily(date);
        if (savedId) {
          // The server forgets games on restart; fall through to a fresh one.
          const saved = await api.getGame(savedId).catch(() => null);
          if (saved) return show(saved, "daily");
        }
        const fresh = await api.dailyGame(date);
        saveDaily(date, fresh.id);
        show(fresh, "daily");
      }),
    [show, withBusy],
  );

  const startPractice = useCallback(
    () =>
      withBusy(async () => {
        show(await api.practiceGame(), "practice");
      }),
    [show, withBusy],
  );

  // Initial load: vocabulary (for autocomplete), then resume an unfinished
  // practice game if there is one, otherwise today's daily.
  useEffect(() => {
    api
      .vocabulary()
      .then((v) => setVocabulary(v.words))
      .catch((e) => setError(errorText(e)));
    const current = loadCurrent();
    void (async () => {
      if (current?.mode === "practice") {
        const saved = await api.getGame(current.id).catch(() => null);
        if (saved?.status === "in_progress") return show(saved, "practice");
      }
      await openDaily();
    })();
    if (!hasSeenHelp()) setShowHelp(true);
  }, [openDaily, show]);

  function closeHelp() {
    markHelpSeen();
    setShowHelp(false);
  }

  /** New practice puzzle; confirm first if it would throw away progress. */
  function requestPractice() {
    const inProgress = game?.status === "in_progress" && game.events.length > 0;
    if (inProgress && mode === "practice") {
      setConfirmNew(true);
      return;
    }
    if (inProgress && mode === "daily") showToast("Today's puzzle is saved — come back any time");
    void startPractice();
  }

  const used = useMemo(() => new Set(game?.path ?? []), [game]);

  async function submit(word: string): Promise<boolean> {
    if (!game || game.status !== "in_progress") return false;
    try {
      const res = await api.submitMove(game.id, word);
      setGame(res.game);
      if (!res.accepted) {
        const reason = res.reason ?? "Invalid move";
        showToast(
          res.strike && res.game.status === "in_progress"
            ? `${reason} — strike ${res.game.strikes} of ${res.game.max_strikes}`
            : reason,
        );
        return false;
      }
      setHint(null);
      return true;
    } catch (e) {
      showToast(errorText(e));
      return false;
    }
  }

  async function getHint() {
    if (!game || game.status !== "in_progress") return;
    try {
      const res = await api.hint(game.id);
      setGame(res.game);
      if (!res.hint) {
        showToast(res.message ?? "No hint available");
      } else if (res.hint === game.target) {
        showToast("One connection away — go for the target!");
      } else {
        setHint(res.hint);
      }
    } catch (e) {
      showToast(errorText(e));
    }
  }

  async function onShare() {
    if (!game) return;
    const outcome = await share(shareText(game, window.location.origin));
    if (outcome === "copied") showToast("Result copied to clipboard");
    else if (outcome === "failed") showToast("Couldn't share — try copying manually");
  }

  return (
    <div className="app">
      <Header onHelp={() => setShowHelp(true)} onNewGame={requestPractice} />
      <Toast toast={toast} />
      <HowToPlayModal open={showHelp} onClose={closeHelp} />
      <Modal open={confirmNew} onClose={() => setConfirmNew(false)} title="New puzzle?">
        <p className="howto-lede">You'll lose your progress on this practice puzzle.</p>
        <div className="actions">
          <button className="btn secondary" onClick={() => setConfirmNew(false)}>
            Keep playing
          </button>
          <button
            className="btn secondary"
            onClick={() => {
              setConfirmNew(false);
              void startPractice();
            }}
          >
            New puzzle
          </button>
        </div>
      </Modal>

      <main className="main">
        {error && <div className="banner error">{error}</div>}

        {game && (
          <>
            <div className="meter">
              <span>
                {game.daily_number ? (
                  <>
                    Daily <strong>#{game.daily_number}</strong>
                  </>
                ) : (
                  <>
                    <strong>Practice</strong>
                    {" · "}
                    <button className="link-btn" onClick={() => void openDaily()}>
                      Today's puzzle
                    </button>
                  </>
                )}
              </span>
              <span>
                Par <strong>{game.optimal_distance}</strong>
                <Strikes used={game.strikes} max={game.max_strikes} />
              </span>
            </div>

            <Board game={game} hint={hint} onPlayHint={(w) => void submit(w)} />

            {game.status === "in_progress" ? (
              <>
                <WordInput
                  vocabulary={vocabulary}
                  used={used}
                  disabled={busy}
                  onSubmit={submit}
                />
                <div className="actions">
                  <button className="btn secondary" onClick={getHint}>
                    Hint{game.hints_used > 0 && ` · ${game.hints_used} used`}
                  </button>
                </div>
                <p className="fine-print">Hints show on your result.</p>
              </>
            ) : (
              <ResultCard
                game={game}
                mode={mode}
                onShare={onShare}
                onPractice={requestPractice}
                onDaily={() => void openDaily()}
              />
            )}
          </>
        )}
      </main>
    </div>
  );
}

function Strikes({ used, max }: { used: number; max: number }) {
  return (
    <span className="strikes" aria-label={`${used} of ${max} strikes used`}>
      {Array.from({ length: max }, (_, i) => (
        <span key={i} className={"strike" + (i < used ? " used" : "")}>
          ✕
        </span>
      ))}
    </span>
  );
}

function ResultCard({
  game,
  mode,
  onShare,
  onPractice,
  onDaily,
}: {
  game: GameState;
  mode: Mode;
  onShare: () => void;
  onPractice: () => void;
  onDaily: () => void;
}) {
  const won = game.status === "won";
  const used = game.connections_used;
  const par = game.optimal_distance;
  const matchedPar = won && used === par;
  const unaidedPar = matchedPar && game.hints_used === 0;
  const struckOut = game.strikes >= game.max_strikes;

  const extras = [
    game.hints_used > 0 && `${game.hints_used} hint${game.hints_used > 1 ? "s" : ""}`,
    game.strikes > 0 && `${game.strikes} strike${game.strikes > 1 ? "s" : ""}`,
  ].filter(Boolean);

  // Reveal a par route unless the player's own chain was one.
  const solution = game.solution;
  const showSolution =
    solution !== null && !(matchedPar && solution.join() === game.path.join());

  return (
    <div className="result-card">
      <h2>{unaidedPar ? "Par! ⛳" : won ? "Connected!" : struckOut ? "Three strikes" : "Out of connections"}</h2>
      <p className="result-line">
        {won
          ? matchedPar
            ? `You matched par in ${used} connections.`
            : `${used} connections — par was ${par}.`
          : `It could be done in ${par}.`}
        {extras.length > 0 && <span className="result-extras"> {extras.join(" · ")}</span>}
      </p>

      {showSolution && (
        <div className="solution">
          <p className="howto-heading">{won ? "A par route" : "Here's how"}</p>
          <div className="howto-example">
            {solution.map((word, i) => (
              <span key={word} style={{ display: "contents" }}>
                {i > 0 && <span className="mini-arrow">→</span>}
                <span
                  className={
                    "mini-tile" +
                    (i === 0 ? " first" : "") +
                    (i === solution.length - 1 ? " last" : "")
                  }
                >
                  {word}
                </span>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="actions">
        <button className="btn primary" onClick={onShare}>
          Share
        </button>
        <button className="btn secondary" onClick={onPractice}>
          Practice puzzle
        </button>
        {mode === "practice" && (
          <button className="btn secondary" onClick={onDaily}>
            Today's puzzle
          </button>
        )}
      </div>
    </div>
  );
}
