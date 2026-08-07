from agent_shared.config import settings
from agent_shared.llm import build_structured_chain
from agent_shared.schemas import IntentClassification

SYSTEM = """You route student messages in a study platform.
Pick exactly one intent:
- study: they want an explanation, help with a concept, or a question answered
- quiz: they want a quiz, practice test, multiple choice, or to be tested
- progress: they ask how they're doing, streaks, scores, history
- flashcard: they want flashcards, spaced recall, or cards for a topic

If ambiguous, prefer study. Extract a short topic when obvious.
Respond only via the structured schema."""

_chain = None


def classify_intent(text: str) -> IntentClassification:
    global _chain
    if _chain is None:
        _chain = build_structured_chain(
            SYSTEM,
            IntentClassification,
            model=settings.router_model,
        )
    return _chain.invoke({"input": text})
