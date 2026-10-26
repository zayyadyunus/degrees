import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type { GameState, ScoreResponse } from "./types";
import { Header } from "./components/Header";
import { Board } from "./components/Board";
import { WordInput } from "./components/WordInput";
import { Toast, type ToastData } from "./components/Toast";
import { HowToPlayModal } from "./components/HowToPlayModal";

const SEEN_HELP_KEY = "degrees:seen-help";

// localStorage can throw (private mode, blocked storage); the help flag is a
// nicety, so treat any failure as "not seen" and ignore failed writes.
function hasSeenHelp(): boolean {
  try {
    return localStorage.getItem(SEEN_HELP_KEY) !== null;
  } catch {
    return false;
  }
}

function markHelpSeen() {
  try {
    localStorage.setItem(SEEN_HELP_KEY, "1");
  } catch {
    // ignore
  }
}

export default function App() {
  const [vocabulary, setVocabulary] = useState<string[]>([]);
  const [game, setGame] = useState<GameState | null>(null);
  const [relations, setRelations] = useState<(string | null)[]>([]);
  const [score, setScore] = useState<ScoreResponse | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastData | null>(null);
  const [showHelp, setShowHelp] = useState(false);
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

  const startNewGame = useCallback(async () => {
    setBusy(true);
    setError(null);
    setScore(null);
    setRelations([]);
    setHint(null);
    setToast(null);
    try {
      setGame(await api.newGame());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  // Initial load: vocabulary (for autocomplete) + first puzzle.
  useEffect(() => {
    api
      .vocabulary()
      .then((v) => setVocabulary(v.words))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    void startNewGame();
    if (!hasSeenHelp()) setShowHelp(true);
  }, [startNewGame]);

  function closeHelp() {
    markHelpSeen();
    setShowHelp(false);
  }

  const used = useMemo(() => new Set(game?.path ?? []), [game]);

  async function submit(word: string): Promise<boolean> {
    if (!game || game.status !== "in_progress") return false;
    try {
      const res = await api.submitMove(game.id, word);
      if (!res.accepted) {
        showToast(res.reason ?? "Invalid move");
        return false;
      }
      setGame(res.game);
      setRelations((r) => [...r, res.relation]);
      setHint(null);
      if (res.game.status !== "in_progress") {
        api.score(game.id).then(setScore).catch(() => {});
      }
      return true;
    } catch (e) {
      showToast(e instanceof Error ? e.message : String(e));
      return false;
    }
  }

  async function getHint() {
    if (!game || game.status !== "in_progress") return;
    try {
      const res = await api.hint(game.id);
      if (!res.hint) {
        showToast(res.message ?? "No hint available");
      } else if (res.hint === game.target) {
        showToast("One connection away — go for the target!");
      } else {
        setHint(res.hint);
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="app">
      <Header onHelp={() => setShowHelp(true)} onNewGame={startNewGame} />
      <Toast toast={toast} />
      <HowToPlayModal open={showHelp} onClose={closeHelp} />

      <main className="main">
        {error && <div className="banner error">{error}</div>}

        {game && (
          <>
            <div className="meter">
              Best possible: <strong>{game.optimal_distance}</strong>
            </div>

            <Board
              game={game}
              relations={relations}
              hint={hint}
              onPlayHint={(w) => void submit(w)}
            />

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
                    Hint
                  </button>
                </div>
              </>
            ) : (
              <ResultCard game={game} score={score} onNewGame={startNewGame} />
            )}
          </>
        )}
      </main>
    </div>
  );
}

function ResultCard({
  game,
  score,
  onNewGame,
}: {
  game: GameState;
  score: ScoreResponse | null;
  onNewGame: () => void;
}) {
  const won = game.status === "won";
  return (
    <div className="result-card">
      <h2>{won ? "Connected!" : "Out of connections"}</h2>
      {score && (
        <p className="result-line">
          {won ? (
            score.is_optimal ? (
              <>You found the shortest path — {score.connections_used} connections.</>
            ) : (
              <>
                {score.connections_used} connections (best possible:{" "}
                {score.optimal_distance}, {score.over_optimal} over).
              </>
            )
          ) : (
            <>
              You used all {game.max_connections} connections. It was solvable
              in {score.optimal_distance}.
            </>
          )}
        </p>
      )}
      <button className="btn primary" onClick={onNewGame}>
        New puzzle
      </button>
    </div>
  );
}
