import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { formatRichText, splitPromptAndHints } from "../lib/richText";
import type { DailyConcept, PracticeProblem } from "../types";
import { RatingStars } from "./RatingStars";

type Grade = {
  score: number;
  passed: boolean;
  feedback: string;
  explanation?: string;
  correct_key?: string | null;
  format?: string;
};

type ArenaSnap = {
  problem: PracticeProblem | null;
  answer: string;
  picked: string | null;
  grade: Grade | null;
};

const ARENA_KEY = "desk.arena.temp.v1";

function readArenaSnap(): ArenaSnap | null {
  try {
    const raw = sessionStorage.getItem(ARENA_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as ArenaSnap;
  } catch {
    return null;
  }
}

function writeArenaSnap(snap: ArenaSnap) {
  try {
    sessionStorage.setItem(ARENA_KEY, JSON.stringify(snap));
  } catch {
    /* ignore quota */
  }
}

export function ArenaPanel() {
  const saved = readArenaSnap();
  const [problem, setProblem] = useState<PracticeProblem | null>(saved?.problem ?? null);
  const [answer, setAnswer] = useState(saved?.answer ?? "");
  const [picked, setPicked] = useState<string | null>(saved?.picked ?? null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [grade, setGrade] = useState<Grade | null>(saved?.grade ?? null);
  const [hydrated] = useState(() => !!saved?.problem);

  useEffect(() => {
    writeArenaSnap({ problem, answer, picked, grade });
  }, [problem, answer, picked, grade]);

  useEffect(() => {
    if (hydrated) return;
    loadDaily();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function resetSolve() {
    setAnswer("");
    setPicked(null);
    setGrade(null);
  }

  async function loadDaily() {
    setBusy(true);
    setErr("");
    resetSolve();
    try {
      setProblem(await api.dailyProblem());
    } catch (e) {
      setErr(String(e));
      setProblem(null);
    } finally {
      setBusy(false);
    }
  }

  async function nextProblem() {
    setBusy(true);
    setErr("");
    resetSolve();
    try {
      setProblem(await api.generateProblem());
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function submit(selected?: string) {
    if (!problem) return;
    const payload =
      problem.format === "mcq" ? (selected || picked || "").trim() : answer.trim();
    if (!payload) return;
    setBusy(true);
    try {
      const g = await api.submitPractice(problem.id, payload);
      setGrade(g);
      if (problem.format === "mcq") setPicked(payload.toUpperCase());
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  const fmt = problem?.format || "short";
  const locked = !!grade;
  const parsed = useMemo(() => {
    if (!problem) return { prompt: "", hints: [] as string[] };
    return splitPromptAndHints(problem.prompt, problem.hints);
  }, [problem]);

  return (
    <section className="panel on">
      <div className="toolbar">
        <button className="btn ghost sm" type="button" onClick={loadDaily} disabled={busy}>
          Today’s problem
        </button>
        <button className="btn sm" type="button" onClick={nextProblem} disabled={busy}>
          {busy ? "Loading…" : "Another problem"}
        </button>
      </div>

      <div className="arena">
        <div className="board enter">
          {err && (
            <p className="muted" style={{ color: "var(--bad)" }}>
              {err}
            </p>
          )}
          {problem ? (
            <>
              {problem.is_daily && problem.slug_day ? (
                <header className="problem-head">
                  <div className="problem-date">{formatDay(problem.slug_day)}</div>
                  <div className="problem-topic">{prettyTrack(problem.track)}</div>
                </header>
              ) : (
                <div className="meta-row">
                  <span className={`tag ${problem.difficulty}`}>{problem.difficulty}</span>
                  <span className="tag">{prettyTrack(problem.track)}</span>
                  <span className="tag">{fmt}</span>
                </div>
              )}
              <h2>{problem.title}</h2>
              {problem.is_daily && (
                <div className="meta-row" style={{ marginTop: -4 }}>
                  <span className={`tag ${problem.difficulty}`}>{problem.difficulty}</span>
                  <span className="tag">{fmt}</span>
                </div>
              )}

              <div className="prob-section">
                <div className="field-label">Problem</div>
                <div className="prompt">{formatRichText(parsed.prompt)}</div>
              </div>

              {parsed.hints.length > 0 && (
                <div className="prob-section hints-box">
                  <div className="field-label">Hints</div>
                  <ol className="hint-list">
                    {parsed.hints.map((h) => (
                      <li key={h}>{formatRichText(h)}</li>
                    ))}
                  </ol>
                </div>
              )}

              <RatingStars targetType="arena" targetId={problem.id} label="Rate problem" />
            </>
          ) : (
            <>
              <h2>{busy ? "Loading…" : "No problem yet"}</h2>
              <p className="muted">Pull today’s problem — the model picks MCQ, typed, or code.</p>
            </>
          )}
        </div>

        <div className="work">
          {!problem ? (
            <p className="muted">Waiting for a problem…</p>
          ) : fmt === "mcq" ? (
            <>
              <label className="field-label">Pick an answer</label>
              <div className="opts" style={{ marginTop: 8 }}>
                {(problem.options || []).map((opt) => {
                  let cls = "opt";
                  if (picked === opt.label) cls += " picked";
                  if (locked && grade?.correct_key === opt.label) cls += " right";
                  if (
                    locked &&
                    picked === opt.label &&
                    grade &&
                    !grade.passed &&
                    grade.correct_key !== opt.label
                  ) {
                    cls += " wrong";
                  }
                  return (
                    <button
                      key={opt.label}
                      type="button"
                      className={cls}
                      disabled={locked || busy}
                      onClick={() => {
                        setPicked(opt.label);
                        submit(opt.label);
                      }}
                    >
                      {opt.label}. {formatRichText(opt.text)}
                    </button>
                  );
                })}
              </div>
            </>
          ) : (
            <>
              <label className="field-label">
                {fmt === "code" ? "Your code" : "Your answer"}
              </label>
              <textarea
                className="box"
                value={answer}
                disabled={locked || busy}
                onChange={(e) => setAnswer(e.target.value)}
                placeholder={
                  fmt === "code"
                    ? "# write a short python snippet…"
                    : "Type your answer…"
                }
              />
              <button
                className="btn"
                type="button"
                disabled={locked || busy || !answer.trim()}
                onClick={() => submit()}
              >
                {busy ? "Checking…" : "Submit"}
              </button>
            </>
          )}

          {grade && (
            <div className={`grade-box show ${grade.passed ? "pass" : "fail"} enter`}>
              <strong>
                {grade.passed ? "Correct" : "Not quite"}
                {fmt !== "mcq" ? ` · ${grade.score}/10` : ""}
              </strong>
              <div style={{ marginTop: 6 }}>{grade.feedback}</div>
              {grade.explanation && !grade.passed && (
                <div style={{ marginTop: 10 }}>
                  <div className="field-label" style={{ marginBottom: 4 }}>
                    Explanation
                  </div>
                  <div style={{ whiteSpace: "pre-wrap" }}>{grade.explanation}</div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

export function DailyPanel() {
  const [c, setC] = useState<DailyConcept | null>(null);
  const [err, setErr] = useState("");

  async function load() {
    setErr("");
    try {
      setC(await api.dailyConcept());
    } catch (e) {
      setErr(String(e));
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <section className="panel on">
      <div className="toolbar">
        <button className="btn ghost sm" type="button" onClick={load}>
          Refresh
        </button>
      </div>
      <div className="scroll">
        {err && <p className="muted">{err}</p>}
        {c && (
          <div className="daily-hero enter">
            <div className="day">
              {c.day} · {c.track}
            </div>
            <h2>{c.title}</h2>
            <div>{c.body}</div>
            <div className="daily-block">
              <h4>Why it matters</h4>
              <div>{c.why_it_matters}</div>
            </div>
            <div className="daily-block">
              <h4>Try this</h4>
              <div>{c.try_this}</div>
            </div>
            <RatingStars targetType="daily" targetId={c.id} label="Rate today’s concept" />
          </div>
        )}
      </div>
    </section>
  );
}

export function ProgressPanel({
  onRefresh,
  data,
}: {
  onRefresh: () => void;
  data: {
    streak_days?: number;
    total_interactions?: number;
    avg_quiz_score?: number | null;
    quiz_scores?: Array<{ score: number }>;
    topics?: Array<{ name: string; count: number }>;
  } | null;
}) {
  const values = (data?.quiz_scores || []).map((s) => s.score);
  return (
    <section className="panel on">
      <div className="toolbar">
        <button className="btn ghost sm" type="button" onClick={onRefresh}>
          Refresh
        </button>
      </div>
      <div className="scroll">
        <div className="stats">
          <div className="stat">
            <div className="n">{data?.streak_days ?? 0}</div>
            <div className="l">day streak</div>
          </div>
          <div className="stat">
            <div className="n">{data?.total_interactions ?? 0}</div>
            <div className="l">study turns</div>
          </div>
          <div className="stat">
            <div className="n">
              {data?.avg_quiz_score != null ? data.avg_quiz_score : "—"}
            </div>
            <div className="l">avg quiz %</div>
          </div>
        </div>
        <div className="chart-wrap">
          <div className="muted" style={{ marginBottom: 8 }}>
            Quiz scores
          </div>
          <ScoreChart values={values} />
        </div>
        <div className="topics">
          <div className="muted" style={{ marginBottom: 8 }}>
            Topics
          </div>
          <ul>
            {(data?.topics || []).length ? (
              data!.topics!.map((t) => (
                <li key={t.name}>
                  <span>{t.name}</span>
                  <span style={{ color: "var(--brass)" }}>{t.count}</span>
                </li>
              ))
            ) : (
              <li className="muted">Nothing yet.</li>
            )}
          </ul>
        </div>
      </div>
    </section>
  );
}

function formatDay(iso: string): string {
  const d = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

function prettyTrack(track: string): string {
  return (track || "")
    .split(/[-_]/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function ScoreChart({ values }: { values: number[] }) {
  if (!values.length) {
    return (
      <svg viewBox="0 0 320 120" width="100%" height="120">
        <text x="12" y="64" fill="#84968c" fontSize="13">
          No quiz scores yet
        </text>
      </svg>
    );
  }
  const w = 320,
    h = 120,
    pad = 12;
  const step = values.length === 1 ? 0 : (w - pad * 2) / (values.length - 1);
  const pts = values.map((v, i) => [
    pad + i * step,
    h - pad - (Math.min(v, 100) / 100) * (h - pad * 2),
  ]);
  const line = pts
    .map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`)
    .join(" ");
  const area = `${line} L${pts[pts.length - 1][0]},${h - pad} L${pts[0][0]},${h - pad} Z`;
  return (
    <svg viewBox="0 0 320 120" width="100%" height="120">
      <path d={area} fill="rgba(201,162,39,.12)" />
      <path d={line} fill="none" stroke="#c9a227" strokeWidth="2" />
      {pts.map((p, i) => (
        <circle key={i} cx={p[0]} cy={p[1]} r="3" fill="#c9a227" />
      ))}
    </svg>
  );
}
