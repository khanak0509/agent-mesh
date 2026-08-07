import { useCallback, useMemo, useRef, useState } from "react";
import { ArenaPanel, DailyPanel, ProgressPanel } from "./components/ArenaPanel";
import { CardsPanel, PathPanel, type ChatBubble } from "./components/PathPanel";
import { QuizPanel, type QuizSession } from "./components/QuizPanel";
import { useAgentSocket } from "./hooks/useAgentSocket";
import type { Flashcard, QuizPayload, StudyPlan, Tab, WsMsg } from "./types";
import { USER } from "./types";
import { ThinkingIndicator } from "./components/ThinkingIndicator";
import "./styles.css";

let bubbleSeq = 0;
const nid = () => `b-${++bubbleSeq}`;

export default function App() {
  const [tab, setTab] = useState<Tab>("arena");
  const [pips, setPips] = useState({ quiz: false, cards: false });
  const [bubbles, setBubbles] = useState<ChatBubble[]>([
    {
      id: nid(),
      who: "meta",
      text: "Say “I want to study machine learning” — I’ll propose a full roadmap first. Hit Proceed to start. Quizzes unlock at checkpoints in the Quiz tab.",
    },
  ]);
  const [plan, setPlan] = useState<StudyPlan | null>(null);
  const [advancePlanId, setAdvancePlanId] = useState<string | null>(null);
  const [lessonTargetId, setLessonTargetId] = useState<string | null>(null);
  const [reteachOpen, setReteachOpen] = useState(false);
  const [awaitingReteach, setAwaitingReteach] = useState(false);
  const reteachIdx = useRef<number | null>(null);
  const awaitTimer = useRef<number | null>(null);

  const [quizSessions, setQuizSessions] = useState<QuizSession[]>([]);
  const [activeQuizId, setActiveQuizId] = useState<string | null>(null);
  const [quizNote, setQuizNote] = useState(
    "No active checkpoint yet. Finish path lessons until a quiz unlocks.",
  );

  const [cards, setCards] = useState<Flashcard[]>([]);
  const [ci, setCi] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [cardsNote, setCardsNote] = useState(
    "Cards accumulate from every lesson — review anytime.",
  );

  const [progress, setProgress] = useState<Record<string, unknown> | null>(null);
  const [awaiting, setAwaiting] = useState(false);
  const [awaitLabel, setAwaitLabel] = useState("Thinking");
  const pendingAdvance = useRef<string | null>(null);
  const activeQuizIdRef = useRef<string | null>(null);
  activeQuizIdRef.current = activeQuizId;

  const clearAwait = useCallback(() => {
    setAwaiting(false);
    setAwaitLabel("Thinking");
    if (awaitTimer.current != null) {
      window.clearTimeout(awaitTimer.current);
      awaitTimer.current = null;
    }
  }, []);

  const startAwait = useCallback((label = "Thinking") => {
    setAwaitLabel(label);
    setAwaiting(true);
    if (awaitTimer.current != null) window.clearTimeout(awaitTimer.current);
    awaitTimer.current = window.setTimeout(() => {
      setAwaiting(false);
      setAwaitLabel("Thinking");
      setBubbles((prev) => [
        ...prev,
        {
          id: nid(),
          who: "meta",
          text: "Still working — if nothing appears, check you’re Connected and try again.",
        },
      ]);
    }, 120000);
  }, []);

  const addBubble = useCallback((text: string, who: ChatBubble["who"]) => {
    setBubbles((prev) => [...prev, { id: nid(), who, text }]);
  }, []);

  const patchActiveQuiz = useCallback((fn: (s: QuizSession) => QuizSession) => {
    const id = activeQuizIdRef.current;
    if (!id) return;
    setQuizSessions((prev) => prev.map((s) => (s.payload.quiz_id === id ? fn(s) : s)));
  }, []);

  const onMessage = useCallback(
    (msg: WsMsg) => {
      if (msg.type === "accepted") {
        if (msg.note) addBubble(msg.note, "meta");
        if (msg.intent === "study") setAwaitLabel("Working on it");
        if (msg.intent === "quiz") setAwaitLabel("Building quiz");
        if (msg.intent === "progress") setAwaitLabel("Loading progress");
        return;
      }

      if (msg.type === "followon_pending") {
        if (msg.kind === "quiz") setQuizNote("Checkpoint quiz generating…");
        if (msg.kind === "cards") setCardsNote("Adding cards from this lesson…");
        return;
      }

      if (msg.type === "start" && msg.intent === "study") {
        setAwaitLabel("Writing reply");
        return;
      }

      if (msg.type === "token") {
        return;
      }

      if (msg.type === "error") {
        clearAwait();
        addBubble(msg.detail || "Something went wrong.", "meta");
        return;
      }

      if (msg.type !== "done") return;

      clearAwait();
      const pl = (msg.payload || {}) as Record<string, unknown>;

      if (msg.intent === "study") {
        if (msg.content?.trim()) {
          addBubble(msg.content, "agent");
        }

        if (pl.kind === "plan_proposal" && pl.plan) {
          setPlan(pl.plan as StudyPlan);
          setAdvancePlanId(null);
        }
        if (pl.plan) setPlan(pl.plan as StudyPlan);

        if (pl.kind === "plan_lesson") {
          const p = pl.plan as StudyPlan;
          setAdvancePlanId(p.plan_id);
          setLessonTargetId(`${p.plan_id}:step:${pl.step_index ?? p.current_step}`);
        }
        if (pl.kind === "plan_quiz_gate") {
          setQuizNote("Checkpoint unlocked — open Quiz.");
          setPips((x) => ({ ...x, quiz: true }));
          pendingAdvance.current = (pl.plan as StudyPlan).plan_id;
          setAdvancePlanId(null);
        }
        if (pl.mode === "reteach" && awaitingReteach) {
          setAwaitingReteach(false);
          setReteachOpen(true);
          if (reteachIdx.current != null) {
            const idx = reteachIdx.current;
            patchActiveQuiz((s) => ({
              ...s,
              graded: { ...s.graded, [idx]: "reteach_done" },
            }));
          }
        }
      }

      if (msg.intent === "quiz") {
        if (pl.questions) {
          const payload = pl as unknown as QuizPayload;
          setQuizSessions((prev) => {
            if (prev.some((s) => s.payload.quiz_id === payload.quiz_id)) return prev;
            return [
              ...prev,
              {
                payload,
                qi: 0,
                picks: {},
                graded: {},
                result: null,
              },
            ];
          });
          setActiveQuizId(payload.quiz_id);
          setQuizNote(`Checkpoint · ${payload.topic}`);
          setPips((x) => ({ ...x, quiz: true }));
          addBubble(`Quiz ready on “${payload.topic}” — open Quiz.`, "meta");
        } else if (pl.result) {
          const result = pl.result as QuizSession["result"];
          const qid = (pl.quiz_id as string) || activeQuizIdRef.current;
          if (qid) {
            setQuizSessions((prev) =>
              prev.map((s) =>
                s.payload.quiz_id === qid ? { ...s, result } : s,
              ),
            );
          }
          if (pendingAdvance.current) {
            addBubble("Checkpoint done. Hit Continue on Path when ready.", "meta");
            setAdvancePlanId(pendingAdvance.current);
          }
        }
      }

      if (msg.intent === "flashcard" && Array.isArray(pl.cards)) {
        const list = pl.cards as Flashcard[];
        setCards((prev) => {
          const next = prev.concat(list);
          setCardsNote(
            `${next.length} cards saved` + (pl.topic ? ` · latest: ${pl.topic}` : ""),
          );
          return next;
        });
        setCi(0);
        setFlipped(false);
        if (pl.auto_from_study) {
          setPips((x) => ({ ...x, cards: true }));
          addBubble(`+${list.length} flashcards added.`, "meta");
        }
      }

      if (msg.intent === "progress") setProgress(pl);
      if (msg.status === "error") addBubble(msg.content || msg.error || "failed", "meta");
    },
    [addBubble, awaitingReteach, clearAwait, patchActiveQuiz, startAwait],
  );

  const { live, send } = useAgentSocket({ onMessage });

  const switchTab = (name: Tab) => {
    setTab(name);
    if (name === "quiz") setPips((x) => ({ ...x, quiz: false }));
    if (name === "cards") setPips((x) => ({ ...x, cards: false }));
    if (name === "progress") {
      startAwait("Loading progress");
      send({
        type: "message",
        text: "how am I doing?",
        user_id: USER,
        intent_hint: "progress",
      });
    }
  };

  const onSend = (text: string) => {
    if (awaiting) return;
    addBubble(text, "user");
    startAwait("Thinking");
    const midPath = plan?.status === "active";
    const ok = send({
      type: "message",
      text,
      user_id: USER,
      intent_hint: "study",
      mode: midPath ? "teach" : "plan",
    });
    if (!ok) {
      clearAwait();
      addBubble("Not connected — wait for Connected, then try again.", "meta");
    }
  };

  const activeSession =
    quizSessions.find((s) => s.payload.quiz_id === activeQuizId) || null;

  const gradeCurrent = (label: string) => {
    if (!activeSession) return;
    const quiz = activeSession.payload;
    const qi = activeSession.qi;
    const q = quiz.questions[qi];
    patchActiveQuiz((s) => ({
      ...s,
      picks: { ...s.picks, [qi]: label },
    }));
    const ok = label.toUpperCase() === String(q.correct).toUpperCase();
    if (ok) {
      patchActiveQuiz((s) => ({
        ...s,
        graded: { ...s.graded, [qi]: "correct" },
      }));
      return;
    }
    patchActiveQuiz((s) => ({
      ...s,
      graded: { ...s.graded, [qi]: "wrong" },
    }));
    reteachIdx.current = qi;
    setAwaitingReteach(true);
    const prompt =
      `I missed this quiz on ${quiz.topic}.\nQuestion: ${q.question}\nI picked: ${label}\nCorrect: ${q.correct}\nKey: ${q.explanation || "n/a"}\nRe-teach this.`;
    switchTab("path");
    addBubble("Missed a checkpoint question — reteaching.", "meta");
    startAwait("Re-teaching");
    send({
      type: "message",
      text: prompt,
      user_id: USER,
      intent_hint: "study",
      topic: quiz.topic,
      mode: "reteach",
    });
  };

  const tabs = useMemo(
    () =>
      [
        ["arena", "Problems", "Arena problems"],
        ["path", "Path", "Study path"],
        ["quiz", "Quiz", "Checkpoints"],
        ["cards", "Cards", "Flashcards"],
        ["daily", "Daily", "Daily concept"],
        ["progress", "Progress", "Your stats"],
      ] as const,
    [],
  );

  const pageTitle =
    tabs.find(([id]) => id === tab)?.[2] ||
    tabs.find(([id]) => id === tab)?.[1] ||
    "Desk";

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">D</span>
          <span className="brand-name">
            Desk<span>.</span>
          </span>
        </div>
        <div className="topbar-center">{pageTitle}</div>
        <div className="live">
          {awaiting && <ThinkingIndicator label={awaitLabel} compact />}
          <span className={`d ${live ? "on" : ""}`} />
          <span>{live ? "Connected" : "Offline"}</span>
        </div>
      </header>

      <div className="workspace">
        <aside className="sidenav">
          {tabs.map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={`nav-item ${tab === id ? "on" : ""}`}
              onClick={() => switchTab(id)}
            >
              <span className="nav-label">{label}</span>
              {id === "quiz" && pips.quiz && <span className="nav-dot" />}
              {id === "cards" && pips.cards && <span className="nav-dot" />}
            </button>
          ))}
        </aside>

        <main className="main">
          <div className="stage">
            <div className={`tab-pane ${tab === "path" ? "on" : ""}`}>
              <PathPanel
                bubbles={bubbles}
                plan={plan}
                reteachOpen={reteachOpen}
                advancePlanId={advancePlanId}
                lessonTargetId={lessonTargetId}
                thinking={awaiting}
                thinkLabel={awaitLabel}
                onSend={onSend}
                onStartPlan={(planId) => {
                  setAdvancePlanId(null);
                  startAwait("Starting path");
                  const ok = send({
                    type: "plan_start",
                    user_id: USER,
                    plan_id: planId,
                  });
                  if (!ok) {
                    clearAwait();
                    addBubble("Not connected — wait for Connected, then Proceed again.", "meta");
                  }
                }}
                onAdvance={(planId) => {
                  setAdvancePlanId(null);
                  startAwait("Next step");
                  const ok = send({
                    type: "plan_advance",
                    user_id: USER,
                    plan_id: planId,
                  });
                  if (!ok) {
                    clearAwait();
                    addBubble("Not connected — wait for Connected, then Continue.", "meta");
                  }
                }}
                onBackToQuiz={() => {
                  setReteachOpen(false);
                  switchTab("quiz");
                }}
              />
            </div>
            <div className={`tab-pane ${tab === "quiz" ? "on" : ""}`}>
              <QuizPanel
                note={quizNote}
                sessions={quizSessions}
                activeId={activeQuizId}
                awaitingReteach={awaitingReteach}
                onSelect={setActiveQuizId}
                onPick={gradeCurrent}
                onBack={() =>
                  patchActiveQuiz((s) => ({
                    ...s,
                    qi: Math.max(0, s.qi - 1),
                  }))
                }
                onNext={() => {
                  if (!activeSession || awaitingReteach) return;
                  const { payload: quiz, qi, picks, graded } = activeSession;
                  const g = graded[qi];
                  if (!(g === "correct" || g === "reteach_done")) return;
                  setReteachOpen(false);
                  if (qi < quiz.questions.length - 1) {
                    patchActiveQuiz((s) => ({ ...s, qi: s.qi + 1 }));
                    return;
                  }
                  startAwait("Grading quiz");
                  send({
                    type: "quiz_submit",
                    user_id: USER,
                    quiz_id: quiz.quiz_id,
                    answers: Object.keys(picks).map((k) => ({
                      question_index: Number(k),
                      selected: picks[Number(k)],
                    })),
                  });
                }}
              />
            </div>
            <div className={`tab-pane ${tab === "cards" ? "on" : ""}`}>
              <CardsPanel
                cards={cards}
                note={cardsNote}
                index={ci}
                flipped={flipped}
                onFlip={() => setFlipped((f) => !f)}
                onPrev={() => {
                  setFlipped(false);
                  setCi((x) => Math.max(0, x - 1));
                }}
                onNext={() => {
                  setFlipped(false);
                  setCi((x) => Math.min(cards.length - 1, x + 1));
                }}
              />
            </div>
            <div className={`tab-pane ${tab === "arena" ? "on" : ""}`}>
              <ArenaPanel />
            </div>
            <div className={`tab-pane ${tab === "daily" ? "on" : ""}`}>
              <DailyPanel />
            </div>
            <div className={`tab-pane ${tab === "progress" ? "on" : ""}`}>
              <ProgressPanel
                data={progress as never}
                onRefresh={() =>
                  send({
                    type: "message",
                    text: "how am I doing?",
                    user_id: USER,
                    intent_hint: "progress",
                  })
                }
              />
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
