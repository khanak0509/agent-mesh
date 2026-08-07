import { useEffect, useRef } from "react";
import type { Flashcard, StudyPlan } from "../types";
import { Markdown } from "../lib/Markdown";
import { RatingStars } from "./RatingStars";
import { ThinkingIndicator } from "./ThinkingIndicator";

export type ChatBubble = {
  id: string;
  who: "user" | "agent" | "meta";
  text: string;
  streaming?: boolean;
};

type Props = {
  bubbles: ChatBubble[];
  plan: StudyPlan | null;
  reteachOpen: boolean;
  thinking?: boolean;
  thinkLabel?: string;
  onSend: (text: string) => void;
  onStartPlan: (planId: string) => void;
  onAdvance: (planId: string) => void;
  onBackToQuiz: () => void;
  advancePlanId: string | null;
  lessonTargetId: string | null;
};

export function PathPanel({
  bubbles,
  plan,
  reteachOpen,
  thinking = false,
  thinkLabel = "Thinking",
  onSend,
  onStartPlan,
  onAdvance,
  onBackToQuiz,
  advancePlanId,
  lessonTargetId,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [bubbles, thinking, plan?.status, advancePlanId]);

  return (
    <section className="panel on">
      {reteachOpen && (
        <div className="banner show">
          Missed a quiz item — reteach below.
          <button className="btn sm" type="button" onClick={onBackToQuiz}>
            Continue quiz
          </button>
        </div>
      )}

      {plan && plan.status !== "proposed" && (
        <div className="path-rail">
          {plan.steps.map((s, i) => {
            let cls = "chip";
            if (i < plan.current_step) cls += " done";
            if (i === plan.current_step && plan.status === "active") cls += " now";
            return (
              <span key={`${s.title}-${i}`} className={cls}>
                {i + 1}. {s.kind}
              </span>
            );
          })}
        </div>
      )}

      <div className="scroll" id="threadWrap">
        <div className="thread">
          {bubbles.map((b) => (
            <div key={b.id} className={`bubble ${b.who}`}>
              {b.who === "agent" ? <Markdown text={b.text} /> : b.text}
            </div>
          ))}

          {thinking && <ThinkingIndicator label={thinkLabel} />}

          {plan?.status === "proposed" && (
            <div className="plan-card enter">
              <h3>{plan.title}</h3>
              <p className="muted">{plan.summary}</p>
              <div className="field-label" style={{ marginTop: 12 }}>
                Full roadmap
              </div>
              <ul className="plan-steps">
                {plan.steps.map((s, i) => (
                  <li key={`${s.title}-${i}`}>
                    <span className={`k ${s.kind}`}>
                      {s.kind === "quiz" ? "quiz" : "lesson"}
                    </span>
                    <div>
                      <strong>
                        {i + 1}. {s.title}
                      </strong>
                      <div className="muted">{s.goal}</div>
                    </div>
                  </li>
                ))}
              </ul>
              <div className="plan-actions">
                <button
                  className="btn"
                  type="button"
                  disabled={thinking}
                  onClick={() => onStartPlan(plan.plan_id)}
                >
                  {thinking ? "Starting…" : "Proceed"}
                </button>
              </div>
              <RatingStars targetType="path" targetId={plan.plan_id} label="Rate plan" />
            </div>
          )}

          {advancePlanId && !thinking && (
            <div className="plan-actions enter">
              <button className="btn" type="button" onClick={() => onAdvance(advancePlanId)}>
                Continue
              </button>
            </div>
          )}

          {lessonTargetId && !thinking && (
            <div className="enter" style={{ marginTop: 8 }}>
              <RatingStars targetType="lesson" targetId={lessonTargetId} label="Rate lesson" />
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          if (thinking) return;
          const fd = new FormData(e.currentTarget);
          const text = String(fd.get("q") || "").trim();
          if (!text) return;
          onSend(text);
          e.currentTarget.reset();
        }}
      >
        <input
          name="q"
          placeholder="Type a topic to study…"
          autoComplete="off"
          disabled={thinking}
        />
        <button className="btn" type="submit" disabled={thinking}>
          {thinking ? "…" : "Send"}
        </button>
      </form>
    </section>
  );
}

export function CardsPanel({
  cards,
  note,
  index,
  flipped,
  onFlip,
  onPrev,
  onNext,
}: {
  cards: Flashcard[];
  note: string;
  index: number;
  flipped: boolean;
  onFlip: () => void;
  onPrev: () => void;
  onNext: () => void;
}) {
  const c = cards[index];
  return (
    <section className="panel on">
      <p className="muted">{note}</p>
      <div className="scroll">
        {!c ? (
          <p className="muted pad">No cards yet — they accumulate as you study.</p>
        ) : (
          <div className="enter">
            <div className="muted center">
              {index + 1} / {cards.length} · {c.topic || ""}
            </div>
            <div className="card-stage">
              <button
                type="button"
                className={`flash ${flipped ? "flipped" : ""}`}
                onClick={onFlip}
              >
                <div className="face front">{c.front}</div>
                <div className="face back">{c.back}</div>
              </button>
            </div>
            <div className="muted center hint">{c.hint ? `hint: ${c.hint}` : ""}</div>
            <div className="card-actions">
              <button className="btn ghost" type="button" onClick={onPrev}>
                Prev
              </button>
              <button className="btn ghost" type="button" onClick={onFlip}>
                Flip
              </button>
              <button className="btn" type="button" onClick={onNext}>
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
