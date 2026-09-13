from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/spaces", tags=["spaces"])


@router.post("", response_model=schemas.SpaceOut)
def create_space(payload: schemas.SpaceCreate, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    space = models.Space(user_id=user.id, name=payload.name, description=payload.description)
    db.add(space)
    db.add(models.Event(user_id=user.id, type="space.created", payload="{}"))
    db.commit()
    db.refresh(space)
    return space


@router.get("", response_model=List[schemas.SpaceOut])
def list_spaces(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return db.query(models.Space).filter(models.Space.user_id == user.id).order_by(models.Space.id.desc()).all()


@router.get("/{space_id}", response_model=schemas.SpaceOut)
def get_space(space_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    space = db.query(models.Space).filter(models.Space.id == space_id).first()
    if not space or (space.user_id != user.id and not user.is_admin):
        raise HTTPException(404, "Space not found")
    return space


@router.delete("/{space_id}")
def delete_space(space_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    space = db.query(models.Space).filter(models.Space.id == space_id).first()
    if not space or space.user_id != user.id:
        raise HTTPException(404, "Space not found")
    db.delete(space)
    db.commit()
    return {"deleted": True}
