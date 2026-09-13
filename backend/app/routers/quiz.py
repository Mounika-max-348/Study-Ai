import json
import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, get_owned_project
from ..services.quiz_engine import start_quiz_attempt, grade_answer
from ..services.mastery_engine import update_mastery
from ..services.recommendation_engine import generate_recommendation

router = APIRouter(prefix="/projects/{project_id}/quiz", tags=["quiz"])


@router.post("/start", response_model=schemas.QuizAttemptOut)
def start_quiz(project_id: int, payload: schemas.QuizStartRequest, db: Session = Depends(get_db),
               user: models.User = Depends(get_current_user)):
    project = get_owned_project(project_id, db, user)
    attempt = start_quiz_attempt(db, project, max(1, min(payload.num_questions, 10)))
    questions = (
        db.query(models.Question).filter(models.Question.attempt_id == attempt.id)
        .order_by(models.Question.order_index.asc()).all()
    )
    if not questions:
        raise HTTPException(400, "Could not generate any questions. Make sure a material has finished processing.")

    db.add(models.Event(user_id=user.id, project_id=project.id, type="quiz.started",
                         payload=json.dumps({"attempt_id": attempt.id, "num_questions": len(questions)})))
    db.commit()

    out_questions = []
    for q in questions:
        concept = db.query(models.Concept).filter(models.Concept.id == q.concept_id).first() if q.concept_id else None
        out_questions.append(schemas.QuestionOut(
            id=q.id, type=q.type, prompt=q.prompt, options=json.loads(q.options or "[]"),
            difficulty=q.difficulty, concept=concept.name if concept else None,
        ))
    return schemas.QuizAttemptOut(attempt_id=attempt.id, questions=out_questions)


@router.post("/{attempt_id}/answer", response_model=schemas.AnswerResultOut)
def submit_answer(project_id: int, attempt_id: int, payload: schemas.AnswerSubmitRequest,
                   db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    project = get_owned_project(project_id, db, user)
    attempt = db.query(models.QuizAttempt).filter(
        models.QuizAttempt.id == attempt_id, models.QuizAttempt.project_id == project.id
    ).first()
    if not attempt:
        raise HTTPException(404, "Quiz attempt not found")
    question = db.query(models.Question).filter(
        models.Question.id == payload.question_id, models.Question.attempt_id == attempt.id
    ).first()
    if not question:
        raise HTTPException(404, "Question not found in this attempt")

    try:
        result = grade_answer(db, project, question, payload.answer)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"AI grading is temporarily unavailable: {e}")

    answer_row = models.QuizAnswer(
        attempt_id=attempt.id, question_id=question.id, user_answer=payload.answer,
        is_correct=result["is_correct"], score=result["score"], feedback=result["feedback"],
    )
    db.add(answer_row)

    if question.concept_id:
        concept = db.query(models.Concept).filter(models.Concept.id == question.concept_id).first()
        if concept:
            update_mastery(db, concept, result["score"])

    db.add(models.Event(user_id=user.id, project_id=project.id, type="quiz.answered",
                         payload=json.dumps({"question_id": question.id, "score": result["score"]})))
    db.commit()

    return schemas.AnswerResultOut(
        question_id=question.id, is_correct=result["is_correct"], score=result["score"],
        feedback=result["feedback"], correct_answer=question.correct_answer,
    )


@router.post("/{attempt_id}/complete")
def complete_quiz(project_id: int, attempt_id: int, db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)):
    project = get_owned_project(project_id, db, user)
    attempt = db.query(models.QuizAttempt).filter(
        models.QuizAttempt.id == attempt_id, models.QuizAttempt.project_id == project.id
    ).first()
    if not attempt:
        raise HTTPException(404, "Quiz attempt not found")
    attempt.status = "completed"
    attempt.completed_at = datetime.datetime.utcnow()
    db.commit()

    answers = (
        db.query(models.QuizAnswer)
        .join(models.Question, models.QuizAnswer.question_id == models.Question.id)
        .filter(models.Question.attempt_id == attempt.id).all()
    )
    avg_score = round(sum(a.score or 0 for a in answers) / len(answers), 1) if answers else 0.0

    db.add(models.Event(user_id=user.id, project_id=project.id, type="quiz.completed",
                         payload=json.dumps({"attempt_id": attempt.id, "avg_score": avg_score})))
    db.commit()

    # Completing a quiz is exactly the kind of event that should trigger the
    # downstream "evaluate -> update mastery -> recommend" workflow (PRD sec 13).
    try:
        rec = generate_recommendation(db, project)
        rec_text = rec.text
    except Exception:  # noqa: BLE001 - don't fail quiz completion if AI recommendation fails
        rec_text = None

    return {"attempt_id": attempt.id, "avg_score": avg_score, "recommendation": rec_text}
