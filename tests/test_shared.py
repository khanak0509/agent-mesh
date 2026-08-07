import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "quiz-agent"))

from agent_shared.messages import Intent, StudyRequest, new_request_id
from agent_shared.schemas import IntentClassification, QuizOption, QuizQuestion
from app.grading import grade_answers


def test_request_id_unique():
    a = new_request_id()
    b = new_request_id()
    assert a != b
    assert len(a) > 10


def test_study_request_roundtrip():
    req = StudyRequest(request_id=new_request_id(), user_id="u1", question="what is osmosis?")
    again = StudyRequest.model_validate(req.model_dump())
    assert again.question.startswith("what")


def test_intent_enum():
    assert Intent.STUDY.value == "study"
    assert Intent("quiz") is Intent.QUIZ


def test_intent_classification_schema():
    obj = IntentClassification(
        intent="study",
        topic="osmosis",
        confidence=0.9,
        rationale="asks for an explanation",
    )
    assert obj.intent.value == "study"


def test_quiz_question_shape():
    q = QuizQuestion(
        question="What is 2+2?",
        options=[
            QuizOption(label="A", text="3"),
            QuizOption(label="B", text="4"),
            QuizOption(label="C", text="5"),
            QuizOption(label="D", text="22"),
        ],
        correct="B",
        explanation="Basic arithmetic.",
    )
    assert q.correct == "B"
    assert len(q.options) == 4


def test_grade_logic():
    questions = [
        {"question": "q1", "correct": "A", "explanation": "because"},
        {"question": "q2", "correct": "C", "explanation": "yes"},
    ]
    answers = [
        {"question_index": 0, "selected": "A"},
        {"question_index": 1, "selected": "B"},
    ]
    result = grade_answers(questions, answers)
    assert result["correct_count"] == 1
    assert result["total"] == 2
    assert result["score"] == 50.0
