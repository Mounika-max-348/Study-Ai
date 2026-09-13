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


# TF-IDF is keyword-overlap matching, so a document-level request like
# "explain the pdf briefly" shares almost no vocabulary with the actual
# content and scores ~0 everywhere -- even though the material genuinely
# covers it. Detect that kind of "give me an overview" intent so it falls
# back to the material's leading chunks instead of a false "insufficient
# evidence". This does NOT apply to genuinely out-of-scope questions
# (e.g. "what's the capital of France"), which should still correctly
# report insufficient evidence.
_OVERVIEW_PHRASES = (
    "summarize", "summarise", "summary", "overview", "explain the pdf",
    "explain this pdf", "explain the document", "explain this document",
    "explain the material", "explain this material", "what is this document",
    "what is this pdf", "what is this material", "what does this cover",
    "what's this about", "what is this about", "tell me about this material",
    "tell me about this document", "tell me about this pdf", "briefly explain",
)


def _is_overview_query(query: str) -> bool:
    q = query.lower()
    return any(phrase in q for phrase in _OVERVIEW_PHRASES)


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
        scores = [0.0] * len(chunks)  # e.g. query/corpus is entirely stop words

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

    if not results and _is_overview_query(query):
        # Fall back to the material's own leading chunks (by page order) so a
        # genuine "what's in this document" request gets grounded context
        # instead of a false insufficient-evidence response.
        ordered = sorted(chunks, key=lambda pair: (pair[1].id, pair[0].page_number))
        for chunk, material in ordered[:top_k]:
            results.append(RetrievedChunk(
                material_filename=material.filename,
                page=chunk.page_number,
                content=chunk.content,
                score=0.0,
            ))

    return results
