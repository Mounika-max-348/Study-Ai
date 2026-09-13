from collections import Counter
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from .. import models
from ..database import get_db
from ..deps import get_current_user, get_owned_project

router = APIRouter(tags=["analytics"])


@router.get("/projects/{project_id}/analytics")
def project_analytics(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    project = get_owned_project(project_id, db, user)

    events = db.query(models.Event).filter(models.Event.project_id == project_id).all()
    event_counts = Counter(e.type for e in events)

    answers = (
        db.query(models.QuizAnswer)
        .join(models.Question, models.QuizAnswer.question_id == models.Question.id)
        .filter(models.Question.project_id == project_id).all()
    )
    avg_quiz_score = round(sum(a.score or 0 for a in answers) / len(answers), 1) if answers else None

    ai_logs = db.query(models.AIUsageLog).filter(models.AIUsageLog.project_id == project_id).all()
    ai_calls = len(ai_logs)
    ai_success_rate = round(sum(1 for l in ai_logs if l.success) / ai_calls * 100, 1) if ai_calls else None
    ai_cost = round(sum(l.estimated_cost_usd for l in ai_logs), 4)

    concepts = db.query(models.Concept).filter(models.Concept.project_id == project_id).all()

    return {
        "activity_by_type": dict(event_counts),
        "total_events": len(events),
        "avg_quiz_score": avg_quiz_score,
        "quiz_answers_recorded": len(answers),
        "concept_mastery": [{"concept": c.name, "mastery": round(c.mastery_score, 1)} for c in concepts],
        "ai_calls": ai_calls,
        "ai_success_rate_pct": ai_success_rate,
        "ai_estimated_cost_usd": ai_cost,
    }


@router.get("/analytics/global")
def global_analytics(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    spaces = db.query(models.Space).filter(models.Space.user_id == user.id).all()
    projects = db.query(models.Project).filter(models.Project.user_id == user.id).all()
    project_ids = [p.id for p in projects]

    concepts = db.query(models.Concept).filter(models.Concept.project_id.in_(project_ids)).all() if project_ids else []
    avg_mastery = round(sum(c.mastery_score for c in concepts) / len(concepts), 1) if concepts else 0.0

    events = db.query(models.Event).filter(models.Event.user_id == user.id).all()

    return {
        "total_spaces": len(spaces),
        "total_projects": len(projects),
        "total_concepts_tracked": len(concepts),
        "average_mastery": avg_mastery,
        "total_activity_events": len(events),
        "projects_overview": [
            {"id": p.id, "name": p.name, "space_id": p.space_id} for p in projects
        ],
    }
