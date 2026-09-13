import json
from sqlalchemy.orm import Session
from .. import models
from .ai_client import call_ai


def generate_recommendation(db: Session, project: models.Project) -> models.Recommendation:
    concepts = db.query(models.Concept).filter(models.Concept.project_id == project.id).all()
    recent_answers = (
        db.query(models.QuizAnswer)
        .join(models.Question, models.QuizAnswer.question_id == models.Question.id)
        .filter(models.Question.project_id == project.id)
        .order_by(models.QuizAnswer.id.desc())
        .limit(10)
        .all()
    )

    concept_summary = "\n".join(
        f"- {c.name}: {c.mastery_score:.0f}% mastery ({c.attempts} attempts)" for c in concepts
    ) or "No concepts assessed yet."
    mistake_summary = "\n".join(
        f"- got {'low score' if (a.score or 0) < 60 else 'high score'} on a question" for a in recent_answers
    ) or "No quiz attempts yet."

    if not concepts:
        text = (
            "Upload a material and start the Tutor or a quiz to begin building your learning "
            "profile — there isn't enough evidence yet to recommend a specific next step."
        )
    else:
        text = call_ai(
            db, "recommendation",
            system=(
                "You are a learning coach. Given a learner's per-concept mastery and recent quiz "
                "performance, write ONE short, specific, actionable recommendation (2-3 sentences) "
                "for what they should do next. Reference the actual weakest concept by name."
            ),
            user_message=f"Goal: {project.goal or project.description}\n\nMastery:\n{concept_summary}\n\nRecent performance:\n{mistake_summary}",
            user_id=project.user_id, project_id=project.id,
        ).strip()

    rec = models.Recommendation(project_id=project.id, text=text)
    db.add(rec)
    db.add(models.Event(user_id=project.user_id, project_id=project.id,
                         type="recommendation.generated", payload=json.dumps({"text": text[:200]})))
    db.commit()
    db.refresh(rec)
    return rec
