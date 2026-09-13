"""
Material processing pipeline:
  Queued -> Processing/OCR (text extraction) -> Chunking -> Concept extraction -> Ready

Runs in a FastAPI BackgroundTask so the upload request returns immediately
and the user can poll /materials/{id} for status. See README "Known
Limitations" for why this is BackgroundTasks rather than a real job queue.
"""
import json
import traceback
from pypdf import PdfReader
from sqlalchemy.orm import Session
from .. import models
from .ai_client import call_ai_json
from ..database import SessionLocal

CHUNK_SIZE = 900
CHUNK_OVERLAP = 150


def _chunk_page_text(text: str):
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - CHUNK_OVERLAP
    return chunks


def _log_event(db: Session, user_id: int, project_id: int, type_: str, payload: dict):
    db.add(models.Event(user_id=user_id, project_id=project_id, type=type_,
                         payload=json.dumps(payload)))
    db.commit()


def _extract_concepts(db: Session, project_id: int, user_id: int, sample_text: str):
    """Ask the AI to propose the key concepts covered by this material.

    Concepts are the unit mastery/quiz/growth all track against, so this is
    the bridge between raw material and the learning-state side of the
    product.
    """
    try:
        result = call_ai_json(
            db, "concept_extraction",
            system=(
                "You are an expert curriculum designer. Given study material, extract 4-8 "
                "distinct, well-scoped concepts a learner should master. Keep names short "
                "(2-5 words)."
            ),
            user_message=(
                f"Study material excerpt:\n\n{sample_text[:6000]}\n\n"
                'Return JSON: {"concepts": ["Concept Name", ...]}'
            ),
            user_id=user_id, project_id=project_id,
        )
        names = result.get("concepts", [])[:8]
    except Exception:
        names = []

    existing = {c.name.lower() for c in db.query(models.Concept)
                .filter(models.Concept.project_id == project_id).all()}
    for name in names:
        if name.lower() not in existing:
            db.add(models.Concept(project_id=project_id, name=name, mastery_score=30.0))
            existing.add(name.lower())
    db.commit()


def process_material(material_id: int):
    """Entry point invoked as a background task. Owns its own DB session
    since it runs outside the request's dependency-injected session."""
    db: Session = SessionLocal()
    try:
        material = db.query(models.Material).filter(models.Material.id == material_id).first()
        if not material:
            return
        project = db.query(models.Project).filter(models.Project.id == material.project_id).first()

        material.status = "processing"
        db.commit()
        _log_event(db, project.user_id, project.id, "material.processing_started",
                   {"material_id": material.id})

        reader = PdfReader(material.filepath)
        material.page_count = len(reader.pages)
        db.commit()

        chunk_index = 0
        all_text_sample = []
        for page_num, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if not text:
                continue  # scanned/image page with no extractable text (OCR would go here)
            if len(all_text_sample) < 3:
                all_text_sample.append(text)
            for piece in _chunk_page_text(text):
                db.add(models.Chunk(
                    material_id=material.id, project_id=project.id,
                    content=piece, page_number=page_num, chunk_index=chunk_index,
                ))
                chunk_index += 1
        db.commit()

        if chunk_index == 0:
            material.status = "failed"
            material.error_message = "No extractable text found (scanned pages need OCR, not supported in this prototype)."
            db.commit()
            _log_event(db, project.user_id, project.id, "material.processing_failed",
                       {"material_id": material.id, "reason": "no_text"})
            return

        _extract_concepts(db, project.id, project.user_id, "\n\n".join(all_text_sample))

        material.status = "ready"
        db.commit()
        _log_event(db, project.user_id, project.id, "material.ready",
                   {"material_id": material.id, "chunks": chunk_index})
    except Exception as e:  # noqa: BLE001
        db.rollback()
        material = db.query(models.Material).filter(models.Material.id == material_id).first()
        if material:
            material.status = "failed"
            material.error_message = f"{e}\n{traceback.format_exc()[:500]}"
            db.commit()
    finally:
        db.close()
