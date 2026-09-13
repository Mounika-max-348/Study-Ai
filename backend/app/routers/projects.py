from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, get_owned_project

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=schemas.ProjectOut)
def create_project(payload: schemas.ProjectCreate, db: Session = Depends(get_db),
                    user: models.User = Depends(get_current_user)):
    space = db.query(models.Space).filter(models.Space.id == payload.space_id).first()
    if not space or space.user_id != user.id:
        raise HTTPException(404, "Space not found")
    project = models.Project(
        space_id=space.id, user_id=user.id, name=payload.name,
        description=payload.description, goal=payload.goal,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    db.add(models.Event(user_id=user.id, project_id=project.id, type="project.created", payload="{}"))
    db.commit()
    return project


@router.get("", response_model=List[schemas.ProjectOut])
def list_projects(space_id: int | None = None, db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)):
    q = db.query(models.Project).filter(models.Project.user_id == user.id)
    if space_id:
        q = q.filter(models.Project.space_id == space_id)
    return q.order_by(models.Project.id.desc()).all()


@router.get("/{project_id}", response_model=schemas.ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return get_owned_project(project_id, db, user)


@router.get("/{project_id}/dashboard")
def project_dashboard(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    project = get_owned_project(project_id, db, user)
    concepts = db.query(models.Concept).filter(models.Concept.project_id == project_id).all()
    materials = db.query(models.Material).filter(models.Material.project_id == project_id).all()
    recent_events = (
        db.query(models.Event)
        .filter(models.Event.project_id == project_id)
        .order_by(models.Event.id.desc()).limit(10).all()
    )
    latest_rec = (
        db.query(models.Recommendation)
        .filter(models.Recommendation.project_id == project_id)
        .order_by(models.Recommendation.id.desc()).first()
    )
    avg_mastery = round(sum(c.mastery_score for c in concepts) / len(concepts), 1) if concepts else 0.0
    weak = sorted(concepts, key=lambda c: c.mastery_score)[:3]

    return {
        "project": schemas.ProjectOut.model_validate(project),
        "overall_progress": avg_mastery,
        "materials_ready": sum(1 for m in materials if m.status == "ready"),
        "materials_total": len(materials),
        "areas_requiring_attention": [{"concept": c.name, "mastery": round(c.mastery_score, 1)} for c in weak],
        "recent_activity": [{"type": e.type, "created_at": e.created_at.isoformat()} for e in recent_events],
        "recommended_next_step": latest_rec.text if latest_rec else None,
    }


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    project = get_owned_project(project_id, db, user)
    db.delete(project)
    db.commit()
    return {"deleted": True}
