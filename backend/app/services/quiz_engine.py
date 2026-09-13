"""
Adaptive quiz engine.

Selection strategy (deliberately more than "wrong -> easy, right -> hard"):
each question targets the concept with the lowest mastery score, weighted
so concepts with fewer attempts also get picked (so new concepts aren't
starved). Difficulty is derived from that concept's *current mastery
estimate*, not from the single previous answer.
"""
import json
import random
from sqlalchemy.orm import Session
from .. import models
from .ai_client import call_ai_json
from .retrieval import retrieve


def _difficulty_for_mastery(score: float) -> str:
    if score < 40:
        return "easy"
    if score < 75:
        return "medium"
    return "hard"


def _select_concept(db: Session, project_id: int, exclude_ids: set[int]) -> models.Concept | None:
    concepts = (
        db.query(models.Concept)
        .filter(models.Concept.project_id == project_id)
        .all()
    )
    candidates = [c for c in concepts if c.id not in exclude_ids] or concepts
    if not candidates:
        return None
    # Sort by mastery ascending, then by fewer attempts first -> weakest/least-evidenced concept first
    candidates.sort(key=lambda c: (c.mastery_score, c.attempts))
    return candidates[0]


def _generate_question(db: Session, project: models.Project, concept: models.Concept,
                        difficulty: str, qtype: str) -> dict:
    context_chunks = retrieve(db, project.id, concept.name, top_k=3)
    context_text = "\n\n".join(f"[p.{c.page}] {c.content}" for c in context_chunks) or \
        "(no material excerpts found for this concept; write a general question about it)"

    if qtype == "mcq":
        schema = ('{"prompt": "...", "options": ["A", "B", "C", "D"], '
                   '"correct_answer": "the exact text of the correct option"}')
    else:
        schema = '{"prompt": "...", "correct_answer": "a model answer used only for grading reference"}'

    result = call_ai_json(
        db, "quiz_generation",
        system=(
            f"You are writing a {difficulty} difficulty {'multiple-choice' if qtype == 'mcq' else 'open-ended'} "
            f"quiz question testing the concept '{concept.name}' for a learner working toward: "
            f"'{project.goal or project.description}'. Base the question on the material excerpts given. "
            f"Return ONLY JSON matching: {schema}"
        ),
        user_message=f"Material excerpts:\n{context_text}",
        user_id=project.user_id, project_id=project.id,
    )
    return result


def start_quiz_attempt(db: Session, project: models.Project, num_questions: int) -> models.QuizAttempt:
    attempt = models.QuizAttempt(project_id=project.id, status="in_progress")
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    used_concepts: set[int] = set()
    for i in range(num_questions):
        concept = _select_concept(db, project.id, used_concepts)
        qtype = "mcq" if i % 2 == 0 else "open"
        if concept is None:
            # No concepts extracted yet (e.g. no ready materials) - fall back to a general question
            difficulty = "medium"
            concept_name = project.goal or project.name
            concept_id = None
        else:
            used_concepts.add(concept.id)
            difficulty = _difficulty_for_mastery(concept.mastery_score)
            concept_name = concept.name
            concept_id = concept.id

        try:
            gen = _generate_question(
                db, project,
                concept or models.Concept(id=None, name=concept_name, mastery_score=30),
                difficulty, qtype,
            )
        except Exception:
            continue  # skip a question if AI generation failed; don't fail the whole quiz

        q = models.Question(
            project_id=project.id,
            concept_id=concept_id,
            attempt_id=attempt.id,
            type=qtype,
            prompt=gen.get("prompt", "").strip(),
            options=json.dumps(gen.get("options", [])) if qtype == "mcq" else "[]",
            correct_answer=gen.get("correct_answer", ""),
            difficulty=difficulty,
            order_index=i,
        )
        db.add(q)
    db.commit()
    return attempt


def grade_answer(db: Session, project: models.Project, question: models.Question, user_answer: str) -> dict:
    if question.type == "mcq":
        is_correct = user_answer.strip().lower() == question.correct_answer.strip().lower()
        return {
            "is_correct": is_correct,
            "score": 100.0 if is_correct else 0.0,
            "feedback": "Correct." if is_correct else f"Not quite. The correct answer was: {question.correct_answer}",
        }

    result = call_ai_json(
        db, "quiz_grading",
        system=(
            "You are grading a learner's open-ended answer. Evaluate understanding, accuracy, "
            "relevance, key concepts covered, and what's missing. Be constructive, not just a score. "
            'Return ONLY JSON: {"score": 0-100, "feedback": "what they understood and what is missing"}'
        ),
        user_message=(
            f"Question: {question.prompt}\n"
            f"Reference/model answer: {question.correct_answer}\n"
            f"Learner's answer: {user_answer}"
        ),
        user_id=project.user_id, project_id=project.id,
    )
    score = float(result.get("score", 0))
    return {
        "is_correct": score >= 60,
        "score": score,
        "feedback": result.get("feedback", ""),
    }
