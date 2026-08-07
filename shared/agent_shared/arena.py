from datetime import date
import re
from uuid import uuid4

from sqlalchemy import delete, select

from agent_shared.config import settings
from agent_shared.db import session_scope
from agent_shared.idempotency import ensure_user
from agent_shared.llm import build_structured_chain
from agent_shared.models import DailyConcept, PracticeAttempt, PracticeProblem
from agent_shared.schemas import DailyConceptDraft, PracticeGrade, PracticeProblemDraft

TRACKS = [
    "python",
    "machine-learning",
    "deep-learning",
    "prompt-engineering",
    "llms",
    "inference",
    "benchmarking",
    "ai-safety",
    "embeddings",
]

PRACTICE_SYSTEM = """You write one practice problem for an AI/ML arena.
YOU decide the format — the student does not choose:
- mcq: 4 options A-D, exactly one correct_key, good for concepts
- short: typed short answer / reasoning
- code: short Python snippet (not a full project)

Pick track + difficulty + format yourself based on what makes a sharp problem today.
Tracks: python, machine-learning, deep-learning, prompt-engineering, llms, inference, benchmarking, ai-safety, embeddings.
For mcq: fill options (4) and correct_key. For short/code: leave options empty and correct_key null.
Always write explanation that teaches when they get it wrong.

STRUCTURE (important — UI renders these as separate sections):
- title: short topic name only (2–6 words). Never include dates or "Daily Problem".
- prompt: the question ONLY. One or two short paragraphs. No hints, no tips, no "compute X then Y".
- hints: 0–2 short tip strings in the hints array — NOT inside prompt.
- Do not paste markdown dumps. No bullet lists inside prompt unless the question needs them.
Keep formulas plain ASCII (e.g. lr_t = lr0 * gamma^t)."""

GRADE_SYSTEM = """Grade a student's short/code practice answer against the rubric.
Be fair. Pass if score >= 7.
feedback = short verdict. explanation = teach the right approach (especially if they missed)."""

DAILY_SYSTEM = """You write one sharp daily concept for AI/ML learners.
One idea, concrete, memorable. Include why it matters and a tiny try-this exercise.
Vary tracks across days when possible."""


def _day_key() -> str:
    return date.today().isoformat()


def get_or_create_daily_concept() -> dict:
    day = _day_key()
    with session_scope() as session:
        row = session.execute(select(DailyConcept).where(DailyConcept.day == day)).scalar_one_or_none()
        if row:
            return {
                "id": row.id,
                "day": row.day,
                "track": row.track,
                "title": row.title,
                "body": row.body,
                "why_it_matters": row.why_it_matters,
                "try_this": row.try_this,
            }

    track = TRACKS[date.today().timetuple().tm_yday % len(TRACKS)]
    chain = build_structured_chain(DAILY_SYSTEM, DailyConceptDraft, model=settings.study_agent_model)
    draft = chain.invoke({"input": f"Today is {day}. Write a daily concept in the {track} track."})
    cid = str(uuid4())
    with session_scope() as session:
        session.add(
            DailyConcept(
                id=cid,
                day=day,
                track=draft.track or track,
                title=draft.title,
                body=draft.body,
                why_it_matters=draft.why_it_matters,
                try_this=draft.try_this,
            )
        )
    return {
        "id": cid,
        "day": day,
        "track": draft.track or track,
        "title": draft.title,
        "body": draft.body,
        "why_it_matters": draft.why_it_matters,
        "try_this": draft.try_this,
    }


def _normalize_format(raw: str) -> str:
    f = (raw or "short").strip().lower()
    if f in ("mcq", "multiple_choice", "multiple-choice"):
        return "mcq"
    if f in ("code", "coding", "python"):
        return "code"
    return "short"


def _sanitize_prompt_hints(prompt: str, hints: list | None) -> tuple[str, list[str]]:
    given = [h.strip() for h in (hints or []) if h and str(h).strip()]
    lines = [ln.strip() for ln in (prompt or "").splitlines() if ln.strip()]
    tip_re = re.compile(
        r"^(hint|tip|use |compute |think |remember |consider |try )\b", re.I
    )
    if not lines:
        return "", given

    body: list[str] = []
    peeled: list[str] = []
    for i, ln in enumerate(lines):
        if i > 0 and tip_re.search(ln) and not given:
            peeled.append(re.sub(r"^(hint|tip)\s*[:.—-]\s*", "", ln, flags=re.I))
        else:
            body.append(ln)

    clean_prompt = "\n\n".join(body).strip()
    merged = given + [p for p in peeled if p and p not in given]
    return clean_prompt, merged[:3]


def _draft_to_problem(draft: PracticeProblemDraft, *, slug_day: str | None, is_daily: bool) -> PracticeProblem:
    fmt = _normalize_format(draft.format)
    options = [o.model_dump() for o in (draft.options or [])]
    correct = (draft.correct_key or "").strip().upper() or None
    if fmt == "mcq":
        if len(options) != 4:
            while len(options) < 4:
                options.append({"label": chr(65 + len(options)), "text": "Option"})
            options = options[:4]
        if not correct:
            correct = options[0]["label"].upper()
    else:
        options = []
        correct = None

    prompt, hints = _sanitize_prompt_hints(draft.prompt or "", draft.hints or [])

    return PracticeProblem(
        id=str(uuid4()),
        slug_day=slug_day,
        track=draft.track or "machine-learning",
        difficulty=(draft.difficulty or "medium").lower(),
        title=_clean_title(draft.title),
        prompt=prompt,
        hints=hints,
        solution=draft.solution,
        rubric=draft.rubric,
        tags=draft.tags or [],
        format=fmt,
        options=options,
        correct_key=correct,
        explanation=draft.explanation,
        is_daily=is_daily,
    )


def _generate_draft(extra: str = "") -> PracticeProblemDraft:
    chain = build_structured_chain(
        PRACTICE_SYSTEM, PracticeProblemDraft, model=settings.study_agent_model
    )
    return chain.invoke(
        {
            "input": (
                "Create one arena problem. YOU pick track, difficulty, and format "
                "(mcq or short or code).\n"
                f"{extra}"
            )
        }
    )


def _prompt_is_meta(prompt: str) -> bool:
    p = (prompt or "").strip().lower()
    return p.startswith("this is the official daily") or "official daily problem for" in p[:80]


def _clean_title(title: str) -> str:
    t = (title or "").strip()
    t = re.sub(r"^Daily Problem\s+\d{4}-\d{2}-\d{2}\s*:\s*", "", t, flags=re.I)
    t = re.sub(r"^Daily\s*:\s*", "", t, flags=re.I)
    return t.strip() or title


def get_or_create_daily_problem() -> dict:
    day = _day_key()
    with session_scope() as session:
        row = session.execute(
            select(PracticeProblem).where(PracticeProblem.slug_day == day)
        ).scalar_one_or_none()
        if (
            row
            and row.explanation is not None
            and (row.format or "short") in ("mcq", "short", "code")
            and not _prompt_is_meta(row.prompt or "")
        ):
            if row.format != "mcq" or len(row.options or []) >= 4:
                return _problem_public(row)
        if row:
            session.execute(delete(PracticeAttempt).where(PracticeAttempt.problem_id == row.id))
            session.delete(row)
            session.flush()

    draft = _generate_draft(
        "This is today's featured daily challenge. "
        "Write a clean title and prompt with no date or 'daily problem' wording — "
        "the UI shows the date separately."
    )
    problem = _draft_to_problem(draft, slug_day=day, is_daily=True)
    problem.title = _clean_title(problem.title)
    with session_scope() as session:
        session.add(problem)
        session.flush()
        return _problem_public(problem)


def generate_practice(_track: str | None = None, _difficulty: str | None = None) -> dict:
    draft = _generate_draft("Fresh practice problem (not the daily).")
    problem = _draft_to_problem(draft, slug_day=None, is_daily=False)
    with session_scope() as session:
        session.add(problem)
        session.flush()
        return _problem_public(problem)


def _problem_public(row: PracticeProblem) -> dict:
    prompt, hints = _sanitize_prompt_hints(row.prompt or "", row.hints or [])
    if _prompt_is_meta(prompt):
        parts = prompt.split("\n", 1)
        prompt = parts[1].strip() if len(parts) > 1 else prompt
        prompt, hints = _sanitize_prompt_hints(prompt, hints)
    return {
        "id": row.id,
        "track": row.track,
        "difficulty": row.difficulty,
        "format": row.format or "short",
        "title": _clean_title(row.title or ""),
        "prompt": prompt,
        "options": row.options or [],
        "hints": hints,
        "tags": row.tags or [],
        "is_daily": bool(row.is_daily),
        "slug_day": row.slug_day,
    }


def grade_practice(user_id: str, problem_id: str, answer: str, request_id: str) -> dict:
    with session_scope() as session:
        ensure_user(session, user_id)
        problem = session.get(PracticeProblem, problem_id)
        if not problem:
            raise ValueError("problem not found")
        fmt = problem.format or "short"
        prompt = problem.prompt
        rubric = problem.rubric or ""
        solution = problem.solution or ""
        explanation = problem.explanation or solution
        correct_key = (problem.correct_key or "").upper()
        options = problem.options or []

    if fmt == "mcq":
        picked = (answer or "").strip().upper()
        passed = picked == correct_key and bool(correct_key)
        score = 10.0 if passed else 0.0
        if passed:
            feedback = "Correct."
            teach = explanation
        else:
            feedback = f"Not quite — correct answer is {correct_key}."
            teach = explanation or "Review the concept and try again tomorrow."
        result = {
            "score": score,
            "passed": passed,
            "feedback": feedback,
            "explanation": teach,
            "correct_key": correct_key,
            "format": "mcq",
            "problem_id": problem_id,
        }
    else:
        chain = build_structured_chain(GRADE_SYSTEM, PracticeGrade, model=settings.study_agent_model)
        grade = chain.invoke(
            {
                "input": (
                    f"Format: {fmt}\nProblem:\n{prompt}\n\nRubric:\n{rubric}\n\n"
                    f"Reference solution:\n{solution}\n\nStudent answer:\n{answer}"
                )
            }
        )
        result = {
            "score": grade.score,
            "passed": grade.passed,
            "feedback": grade.feedback,
            "explanation": grade.explanation or explanation,
            "correct_key": None,
            "format": fmt,
            "problem_id": problem_id,
        }

    with session_scope() as session:
        session.add(
            PracticeAttempt(
                request_id=request_id,
                problem_id=problem_id,
                user_id=user_id,
                answer=answer,
                score=result["score"],
                feedback=result["feedback"] + "\n" + (result.get("explanation") or ""),
                passed=result["passed"],
            )
        )

    return result


def list_tracks() -> list[str]:
    return list(TRACKS)
