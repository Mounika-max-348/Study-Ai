from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from .. import models
from ..database import get_db
from ..deps import get_current_admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overview")
def admin_overview(db: Session = Depends(get_db), admin: models.User = Depends(get_current_admin)):
    total_users = db.query(models.User).count()
    total_spaces = db.query(models.Space).count()
    total_projects = db.query(models.Project).count()
    total_materials = db.query(models.Material).count()
    materials_failed = db.query(models.Material).filter(models.Material.status == "failed").count()
    materials_processing = db.query(models.Material).filter(
        models.Material.status.in_(["queued", "processing"])
    ).count()
    ai_logs = db.query(models.AIUsageLog).all()
    ai_calls = len(ai_logs)
    ai_failures = sum(1 for l in ai_logs if not l.success)
    ai_cost = round(sum(l.estimated_cost_usd for l in ai_logs), 4)
    avg_latency = round(sum(l.latency_ms for l in ai_logs) / ai_calls, 1) if ai_calls else 0

    return {
        "users": total_users,
        "spaces": total_spaces,
        "projects": total_projects,
        "materials": {"total": total_materials, "failed": materials_failed, "in_progress": materials_processing},
        "ai_usage": {
            "total_calls": ai_calls, "failures": ai_failures,
            "estimated_cost_usd": ai_cost, "avg_latency_ms": avg_latency,
        },
    }


@router.get("/users")
def list_users(db: Session = Depends(get_db), admin: models.User = Depends(get_current_admin)):
    users = db.query(models.User).all()
    out = []
    for u in users:
        project_count = db.query(models.Project).filter(models.Project.user_id == u.id).count()
        out.append({
            "id": u.id, "email": u.email, "full_name": u.full_name, "is_admin": u.is_admin,
            "projects": project_count, "created_at": u.created_at.isoformat(),
        })
    return out


@router.get("/users/{user_id}")
def inspect_user(user_id: int, db: Session = Depends(get_db), admin: models.User = Depends(get_current_admin)):
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(404, "User not found")
    projects = db.query(models.Project).filter(models.Project.user_id == user_id).all()
    events = (
        db.query(models.Event).filter(models.Event.user_id == user_id)
        .order_by(models.Event.id.desc()).limit(50).all()
    )
    ai_logs = db.query(models.AIUsageLog).filter(models.AIUsageLog.user_id == user_id).all()
    answers = (
        db.query(models.QuizAnswer)
        .join(models.Question, models.QuizAnswer.question_id == models.Question.id)
        .join(models.Project, models.Question.project_id == models.Project.id)
        .filter(models.Project.user_id == user_id).all()
    )
    avg_score = round(sum(a.score or 0 for a in answers) / len(answers), 1) if answers else None

    return {
        "user": {"id": u.id, "email": u.email, "full_name": u.full_name, "is_admin": u.is_admin},
        "projects": [{"id": p.id, "name": p.name, "space_id": p.space_id} for p in projects],
        "quiz_answers": len(answers),
        "avg_quiz_score": avg_score,
        "ai_calls": len(ai_logs),
        "ai_estimated_cost_usd": round(sum(l.estimated_cost_usd for l in ai_logs), 4),
        "recent_activity": [{"type": e.type, "project_id": e.project_id, "created_at": e.created_at.isoformat()} for e in events],
    }


@router.get("/activity")
def platform_activity(
    user_id: Optional[int] = None,
    project_id: Optional[int] = None,
    type: Optional[str] = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    q = db.query(models.Event)
    if user_id:
        q = q.filter(models.Event.user_id == user_id)
    if project_id:
        q = q.filter(models.Event.project_id == project_id)
    if type:
        q = q.filter(models.Event.type == type)
    events = q.order_by(models.Event.id.desc()).limit(limit).all()
    return [
        {"id": e.id, "user_id": e.user_id, "project_id": e.project_id, "type": e.type,
         "created_at": e.created_at.isoformat()} for e in events
    ]


@router.get("/ai-usage")
def ai_usage(
    feature: Optional[str] = None,
    success: Optional[bool] = None,
    limit: int = Query(200, le=1000),
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    q = db.query(models.AIUsageLog)
    if feature:
        q = q.filter(models.AIUsageLog.feature == feature)
    if success is not None:
        q = q.filter(models.AIUsageLog.success == success)
    logs = q.order_by(models.AIUsageLog.id.desc()).limit(limit).all()
    return [
        {
            "id": l.id, "feature": l.feature, "model": l.model, "latency_ms": l.latency_ms,
            "input_tokens": l.input_tokens, "output_tokens": l.output_tokens,
            "estimated_cost_usd": l.estimated_cost_usd, "success": l.success,
            "error_message": l.error_message, "created_at": l.created_at.isoformat(),
        } for l in logs
    ]


@router.get("/system-health")
def system_health(db: Session = Depends(get_db), admin: models.User = Depends(get_current_admin)):
    materials = db.query(models.Material).all()
    by_status = {}
    for m in materials:
        by_status[m.status] = by_status.get(m.status, 0) + 1
    recent_ai_failures = (
        db.query(models.AIUsageLog)
        .filter(models.AIUsageLog.success == False)  # noqa: E712
        .order_by(models.AIUsageLog.id.desc()).limit(20).all()
    )
    return {
        "materials_by_status": by_status,
        "recent_ai_failures": [
            {"feature": l.feature, "error": l.error_message[:200], "created_at": l.created_at.isoformat()}
            for l in recent_ai_failures
        ],
    }
