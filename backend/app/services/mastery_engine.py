"""
Mastery is an *estimate*, updated incrementally as new evidence (quiz
answers) arrives, not recomputed from scratch. We use an exponential
moving average so recent performance matters more than old performance,
but a single lucky/unlucky answer doesn't swing the score wildly.
"""
from sqlalchemy.orm import Session
from .. import models

LEARNING_RATE = 0.35


def update_mastery(db: Session, concept: models.Concept, performance_0_100: float):
    concept.attempts += 1
    if performance_0_100 >= 60:
        concept.correct += 1
    concept.mastery_score = (
        (1 - LEARNING_RATE) * concept.mastery_score + LEARNING_RATE * performance_0_100
    )
    concept.mastery_score = max(0.0, min(100.0, concept.mastery_score))
    db.commit()


def growth_trend(mastery_now: float, mastery_before: float) -> str:
    delta = mastery_now - mastery_before
    if delta > 4:
        return "improving"
    if delta < -4:
        return "requires_attention"
    return "stable"
