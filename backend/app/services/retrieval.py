"""
Search/retrieval representation for the Tutor and quiz generator.

Design choice: TF-IDF keyword retrieval (scikit-learn) instead of vector
embeddings. This keeps the prototype fully self-contained (no embeddings
API, no vector DB) while still satisfying the requirement that the Tutor
can "retrieve relevant information and trace it back to its source."
A production version would swap this for embeddings + a vector index
(pgvector / Pinecone / etc.) behind the same retrieve() interface.
"""
from dataclasses import dataclass
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy.orm import Session
from .. import models


@dataclass
class RetrievedChunk:
    material_filename: str
    page: int
    content: str
    score: float


def retrieve(db: Session, project_id: int, query: str, top_k: int = 4) -> list[RetrievedChunk]:
    chunks = (
        db.query(models.Chunk, models.Material)
        .join(models.Material, models.Chunk.material_id == models.Material.id)
        .filter(models.Chunk.project_id == project_id, models.Material.status == "ready")
        .all()
    )
    if not chunks:
        return []

    corpus = [c.content for c, _ in chunks]
    try:
        vectorizer = TfidfVectorizer(stop_words="english", max_features=5000)
        matrix = vectorizer.fit_transform(corpus + [query])
        scores = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
    except ValueError:
        return []  # e.g. query/corpus is entirely stop words

    ranked = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
    results = []
    for score, (chunk, material) in ranked[:top_k]:
        if score <= 0:
            continue
        results.append(RetrievedChunk(
            material_filename=material.filename,
            page=chunk.page_number,
            content=chunk.content,
            score=float(score),
        ))
    return results
