def grade_answers(quiz_questions: list[dict], answers: list[dict]) -> dict:
    by_index = {a["question_index"]: str(a["selected"]).strip().upper() for a in answers}
    details = []
    correct_count = 0
    for i, q in enumerate(quiz_questions):
        selected = by_index.get(i, "")
        expected = str(q["correct"]).strip().upper()
        ok = selected == expected
        if ok:
            correct_count += 1
        details.append(
            {
                "index": i,
                "question": q["question"],
                "selected": selected,
                "correct": expected,
                "is_correct": ok,
                "explanation": q.get("explanation", ""),
            }
        )
    total = len(quiz_questions)
    score = (correct_count / total * 100.0) if total else 0.0
    return {
        "score": round(score, 1),
        "correct_count": correct_count,
        "total": total,
        "details": details,
    }
