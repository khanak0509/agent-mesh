from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))

from agent_shared.config import settings  # noqa: E402
from agent_shared.llm import build_structured_chain  # noqa: E402
from agent_shared.schemas import JudgeScore, QuizSet, StudyAnswer  # noqa: E402

STUDY_SYSTEM = """You are a patient study tutor. Explain clearly without fluff.
Match depth to the question. Always fill topic with a short normalized label."""

QUIZ_SYSTEM = """You write multiple-choice quizzes for students.
Exactly 4 options A-D, exactly one correct answer, plausible distractors, clear stems."""

JUDGE_SYSTEM = """You grade tutor/quiz outputs for a study platform.
Score 0-10 on correctness, clarity, depth; overall score is their average unless a hard fail.
Hard fail (cap overall at 3): factual errors, multiple correct answers marked, or unusable structure.
Be strict but fair. Notes should be one or two sentences."""


def load_json(path: Path):
    return json.loads(path.read_text())


def judge(output_text: str, criteria: str, kind: str) -> JudgeScore:
    chain = build_structured_chain(JUDGE_SYSTEM, JudgeScore, model=settings.judge_model)
    return chain.invoke(
        {
            "input": (
                f"Kind: {kind}\n"
                f"Rubric criteria: {criteria}\n\n"
                f"Output to grade:\n{output_text}"
            )
        }
    )


def eval_study(prompts: list[dict], limit: int | None) -> list[dict]:
    chain = build_structured_chain(STUDY_SYSTEM, StudyAnswer, model=settings.study_agent_model)
    rows = []
    for item in prompts[: limit or len(prompts)]:
        ans = chain.invoke({"input": item["question"]})
        text = ans.answer + "\n" + "\n".join(ans.key_points)
        score = judge(text, item["criteria"], "study")
        rows.append(
            {
                "id": item["id"],
                "score": score.score,
                "correctness": score.correctness,
                "clarity": score.clarity,
                "depth": score.depth,
                "notes": score.notes,
            }
        )
        print(f"study {item['id']}: {score.score:.1f} - {score.notes}")
    return rows


def eval_quiz(prompts: list[dict], limit: int | None) -> list[dict]:
    chain = build_structured_chain(QUIZ_SYSTEM, QuizSet, model=settings.quiz_agent_model)
    rows = []
    for item in prompts[: limit or len(prompts)]:
        quiz = chain.invoke(
            {
                "input": (
                    f"Topic: {item['topic']}\n"
                    f"Number of questions: {item['num_questions']}\n"
                    f"Difficulty: {item['difficulty']}"
                )
            }
        )
        structural_penalty = 0.0
        for q in quiz.questions:
            labels = [o.label.upper() for o in q.options]
            if len(q.options) != 4 or len(set(labels)) != 4:
                structural_penalty += 3
            if q.correct.upper() not in labels:
                structural_penalty += 4
        blob = quiz.model_dump_json(indent=2)
        score = judge(blob, item["criteria"], "quiz")
        final = max(0.0, score.score - structural_penalty)
        rows.append(
            {
                "id": item["id"],
                "score": final,
                "notes": score.notes,
                "structural_penalty": structural_penalty,
            }
        )
        print(f"quiz {item['id']}: {final:.1f} (penalty {structural_penalty}) - {score.notes}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", choices=["study-agent", "quiz-agent", "both"], default="both")
    parser.add_argument("--threshold", type=float, default=float(os.getenv("EVAL_SCORE_THRESHOLD", "7.0")))
    parser.add_argument("--limit", type=int, default=None, help="cap prompts for cheaper local runs")
    args = parser.parse_args()

    if not settings.openai_api_key:
        print("no OPENAI_API_KEY, can't judge")
        raise SystemExit(2)

    all_scores: list[float] = []

    if args.service in ("study-agent", "both"):
        study_prompts = load_json(Path(__file__).parent / "study_agent_prompts.json")
        rows = eval_study(study_prompts, args.limit)
        avg = sum(r["score"] for r in rows) / len(rows)
        print(f"study avg {avg:.2f}")
        all_scores.append(avg)

    if args.service in ("quiz-agent", "both"):
        quiz_prompts = load_json(Path(__file__).parent / "quiz_agent_prompts.json")
        rows = eval_quiz(quiz_prompts, args.limit)
        avg = sum(r["score"] for r in rows) / len(rows)
        print(f"quiz avg {avg:.2f}")
        all_scores.append(avg)

    overall = sum(all_scores) / len(all_scores)
    print(f"overall {overall:.2f} (need {args.threshold})")
    if overall < args.threshold:
        print("eval failed")
        raise SystemExit(1)
    print("eval passed")


if __name__ == "__main__":
    main()
