import os
import uuid
from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, get_owned_project
from ..config import settings
from ..services.document_processor import process_material

router = APIRouter(prefix="/projects/{project_id}/materials", tags=["materials"])


@router.post("", response_model=schemas.MaterialOut)
def upload_material(
    project_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    project = get_owned_project(project_id, db, user)
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF materials are supported in this prototype")

    project_dir = os.path.join(settings.upload_dir, str(project.id))
    os.makedirs(project_dir, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}_{file.filename}"
    filepath = os.path.join(project_dir, stored_name)
    with open(filepath, "wb") as f:
        f.write(file.file.read())

    material = models.Material(
        project_id=project.id, filename=file.filename, filepath=filepath, status="queued",
    )
    db.add(material)
    db.add(models.Event(user_id=user.id, project_id=project.id, type="material.uploaded",
                         payload="{}"))
    db.commit()
    db.refresh(material)

    background_tasks.add_task(process_material, material.id)
    return material


@router.get("", response_model=List[schemas.MaterialOut])
def list_materials(project_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    get_owned_project(project_id, db, user)
    return (
        db.query(models.Material)
        .filter(models.Material.project_id == project_id)
        .order_by(models.Material.id.desc()).all()
    )


@router.get("/{material_id}", response_model=schemas.MaterialOut)
def get_material(project_id: int, material_id: int, db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    get_owned_project(project_id, db, user)
    material = db.query(models.Material).filter(
        models.Material.id == material_id, models.Material.project_id == project_id
    ).first()
    if not material:
        raise HTTPException(404, "Material not found")
    return material


@router.delete("/{material_id}", status_code=204)
def delete_material(project_id: int, material_id: int, db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)):
    project = get_owned_project(project_id, db, user)
    material = db.query(models.Material).filter(
        models.Material.id == material_id, models.Material.project_id == project_id
    ).first()
    if not material:
        raise HTTPException(404, "Material not found")

    # Remove retrieval chunks tied to this material (concepts/mastery/quiz history
    # stay intact -- they represent the learner's progress, not the source file).
    db.query(models.Chunk).filter(models.Chunk.material_id == material.id).delete()

    if material.filepath and os.path.exists(material.filepath):
        try:
            os.remove(material.filepath)
        except OSError:
            pass  # file already gone / permissions issue -- don't block the delete

    db.add(models.Event(user_id=user.id, project_id=project.id, type="material.deleted",
                         payload=f'{{"filename": {material.filename!r}}}'))
    db.delete(material)
    db.commit()
    return None
