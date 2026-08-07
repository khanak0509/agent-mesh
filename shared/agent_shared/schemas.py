from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class RouterIntent(str, Enum):
    study = "study"
    quiz = "quiz"
    progress = "progress"
    flashcard = "flashcard"


class IntentClassification(BaseModel):
    intent: RouterIntent = Field(description="Which agent should handle this message")
    topic: Optional[str] = Field(default=None, description="Topic if one is clearly mentioned")
    confidence: float = Field(ge=0.0, le=1.0, description="How sure we are")
    rationale: str = Field(description="One short sentence why")


class StudyAnswer(BaseModel):
    topic: str = Field(description="Normalized topic label for progress tracking")
    answer: str = Field(description="Clear explanation suitable for a student")
    key_points: List[str] = Field(description="3-5 bullet takeaways")
    follow_up: Optional[str] = Field(default=None, description="Optional next question to ask")


class QuizOption(BaseModel):
    label: str = Field(description="A, B, C, or D")
    text: str


class QuizQuestion(BaseModel):
    question: str
    options: List[QuizOption] = Field(min_length=4, max_length=4)
    correct: str = Field(description="Label of the single correct option, e.g. A")
    explanation: str


class QuizSet(BaseModel):
    topic: str
    questions: List[QuizQuestion] = Field(min_length=1)


class FlashcardItem(BaseModel):
    front: str = Field(description="Prompt side — short question or term")
    back: str = Field(description="Answer side — concise but complete")
    hint: Optional[str] = None
    topic: str


class FlashcardSet(BaseModel):
    topic: str
    cards: List[FlashcardItem] = Field(min_length=1)


class JudgeScore(BaseModel):
    score: float = Field(ge=0, le=10)
    correctness: float = Field(ge=0, le=10)
    clarity: float = Field(ge=0, le=10)
    depth: float = Field(ge=0, le=10)
    notes: str


class PlanStep(BaseModel):
    kind: str = Field(description="lesson or quiz")
    title: str
    topic: str
    goal: str = Field(description="What the student should understand after this step")


class StudyPlanDraft(BaseModel):
    topic: str
    title: str
    summary: str = Field(description="2-3 sentences on the path")
    steps: List[PlanStep] = Field(
        min_length=4,
        max_length=10,
        description="Mix of lessons and quiz checkpoints. Start with a lesson. Include 2+ quizzes.",
    )


class PracticeOption(BaseModel):
    label: str = Field(description="A, B, C, or D")
    text: str


class PracticeProblemDraft(BaseModel):
    track: str
    difficulty: str = Field(description="easy | medium | hard")
    format: str = Field(description="mcq | short | code — pick what fits the concept best")
    title: str
    prompt: str = Field(description="Clear problem statement. For code, say what to implement.")
    options: List[PracticeOption] = Field(
        default_factory=list,
        description="Required for mcq: exactly 4 options. Empty for short/code.",
    )
    correct_key: Optional[str] = Field(
        default=None,
        description="For mcq: the correct option label e.g. B. Null for short/code.",
    )
    hints: List[str] = Field(min_length=1, max_length=3)
    solution: str = Field(description="Reference answer or code")
    explanation: str = Field(
        description="Teach why the answer is right — shown when the student misses"
    )
    rubric: str = Field(description="How to score short/code answers 0-10")
    tags: List[str]


class PracticeGrade(BaseModel):
    score: float = Field(ge=0, le=10)
    passed: bool
    feedback: str
    explanation: Optional[str] = None
    correct_key: Optional[str] = None


class DailyConceptDraft(BaseModel):
    track: str
    title: str
    body: str
    why_it_matters: str
    try_this: str
