import { RatingStars } from "./RatingStars";
import type { QuizPayload } from "../types";

export type QuizSession = {
  payload: QuizPayload;
  qi: number;
  picks: Record<number, string>;
  graded: Record<number, string>;
  result: {
    correct_count: number;
    total: number;
    score: number;
    details?: Array<{
      question: string;
      selected: string;
      correct: string;
      is_correct: boolean;
      explanation?: string;
    }>;
  } | null;
};

type Props = {
  note: string;
  sessions: QuizSession[];
  activeId: string | null;
  awaitingReteach: boolean;
  onSelect: (quizId: string) => void;
  onPick: (label: string) => void;
  onBack: () => void;
  onNext: () => void;
};

export function QuizPanel({
  note,
  sessions,
  activeId,
  awaitingReteach,
  onSelect,
  onPick,
  onBack,
  onNext,
}: Props) {
  const session = sessions.find((s) => s.payload.quiz_id === activeId) || null;
  const quiz = session?.payload || null;
  const result = session?.result || null;
  const qi = session?.qi ?? 0;
  const picks = session?.picks || {};
  const graded = session?.graded || {};

  return (
    <section className="panel on">
      {sessions.length > 0 && (
        <div className="quiz-list">
          {sessions.map((s, i) => {
            const id = s.payload.quiz_id;
            const done = !!s.result;
            let cls = "quiz-pill";
            if (id === activeId) cls += " on";
            if (done) cls += " done";
            return (
              <button
                key={id}
                type="button"
                className={cls}
                onClick={() => onSelect(id)}
              >
                Quiz {i + 1}
                <span className="muted"> · {s.payload.topic}</span>
                {done ? " · done" : id === activeId ? " · open" : ""}
              </button>
            );
          })}
        </div>
      )}

      {!quiz ? (
        <>
          <p className="muted">{note}</p>
          <p className="muted pad">
            Waiting for a checkpoint — quizzes appear here one at a time when your path unlocks
            them.
          </p>
        </>
      ) : result ? (
        <div className="scroll">
          <div className="score-big enter">
            {result.correct_count}/{result.total}
          </div>
          <p className="muted">
            {result.score}% · {quiz.topic}
          </p>
          {result.details?.map((d, i) => (
            <div className="result-card enter" key={i}>
              <strong>
                {i + 1}. {d.question}
              </strong>
              <div
                style={{
                  color: d.is_correct ? "var(--ok)" : "var(--bad)",
                  margin: "6px 0",
                }}
              >
                {d.is_correct ? "Correct" : "Missed"} — {d.selected || "—"} / {d.correct}
              </div>
              <div className="muted">{d.explanation || ""}</div>
            </div>
          ))}
          <RatingStars targetType="quiz" targetId={quiz.quiz_id} label="Rate quiz" />
        </div>
      ) : (
        <>
          <p className="muted">
            Checkpoint · {quiz.topic} · Question {qi + 1} / {quiz.questions.length}
          </p>
          <div className="scroll">
            <div className="enter">
              <div className="q-prompt">{quiz.questions[qi].question}</div>
              <div className="opts">
                {quiz.questions[qi].options.map((opt) => {
                  const q = quiz.questions[qi];
                  const locked = !!graded[qi];
                  let cls = "opt";
                  if (picks[qi] === opt.label) cls += " picked";
                  if (locked && opt.label === q.correct) cls += " right";
                  if (locked && picks[qi] === opt.label && opt.label !== q.correct) {
                    cls += " wrong";
                  }
                  return (
                    <button
                      key={opt.label}
                      type="button"
                      className={cls}
                      disabled={locked || awaitingReteach}
                      onClick={() => onPick(opt.label)}
                    >
                      {opt.label}. {opt.text}
                    </button>
                  );
                })}
              </div>
              {graded[qi] === "correct" && (
                <div className="quiz-feedback show ok">
                  {quiz.questions[qi].explanation || "Correct."}
                </div>
              )}
              {(graded[qi] === "wrong" || graded[qi] === "reteach_done") && (
                <div className="quiz-feedback show bad">
                  Answer: {quiz.questions[qi].correct}.{" "}
                  {quiz.questions[qi].explanation || ""}
                </div>
              )}
              <div className="quiz-nav">
                <button
                  className="btn ghost"
                  type="button"
                  disabled={qi === 0 || awaitingReteach}
                  onClick={onBack}
                >
                  Back
                </button>
                <button
                  className="btn"
                  type="button"
                  disabled={
                    !(graded[qi] === "correct" || graded[qi] === "reteach_done") ||
                    awaitingReteach
                  }
                  onClick={onNext}
                >
                  {qi === quiz.questions.length - 1 ? "Submit" : "Next"}
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
