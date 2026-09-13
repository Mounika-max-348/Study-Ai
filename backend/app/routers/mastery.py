from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, get_owned_project
from ..services.recommendation_engine import generate_recommendation

router = APIRouter(prefix="/projects/{project_id}", tags=["mastery"])


@router.get("/mastery", response_model=List[schemas.ConceptOut])
def get_mastery(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    get_owned_project(project_id, db, user)
    return (
        db.query(models.Concept).filter(models.Concept.project_id == project_id)
        .order_by(models.Concept.mastery_score.asc()).all()
    )


@router.get("/growth")
def get_growth(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Per-concept trend, derived from each concept's attempt/correct history.

    A full historical time series would need periodic mastery snapshots; for
    this prototype we classify trend from the running attempts/correct ratio
    versus the current EMA score, which is enough to answer "improving /
    stable / needs attention" per concept as the PRD asks for.
    """
    get_owned_project(project_id, db, user)
    concepts = db.query(models.Concept).filter(models.Concept.project_id == project_id).all()
    growth = []
    for c in concepts:
        lifetime_rate = (c.correct / c.attempts * 100) if c.attempts else c.mastery_score
        delta = c.mastery_score - lifetime_rate
        if c.attempts < 2:
            trend = "stable"
        elif delta > 4:
            trend = "improving"
        elif delta < -4:
            trend = "requires_attention"
        else:
            trend = "stable"
        growth.append({
            "concept": c.name, "mastery_score": round(c.mastery_score, 1),
            "attempts": c.attempts, "correct": c.correct, "trend": trend,
        })
    return growth


@router.get("/recommendations", response_model=List[schemas.RecommendationOut])
def list_recommendations(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    get_owned_project(project_id, db, user)
    return (
        db.query(models.Recommendation).filter(models.Recommendation.project_id == project_id)
        .order_by(models.Recommendation.id.desc()).limit(10).all()
    )


@router.post("/recommendations/generate", response_model=schemas.RecommendationOut)
def generate_recommendation_now(project_id: int, db: Session = Depends(get_db),
                                 user: models.User = Depends(get_current_user)):
    project = get_owned_project(project_id, db, user)
    try:
        return generate_recommendation(db, project)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"AI recommendation service is temporarily unavailable: {e}")
