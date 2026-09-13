"""
Thin wrapper around the AI provider.

This is the single place every AI-powered feature (Tutor, quiz generation,
quiz grading, recommendations, concept extraction) goes through. Centralizing
it here gives us one spot to add observability (latency, token usage,
estimated cost, success/failure) as required by the PRD's "Observable AI"
principle, and one spot to swap providers.

Provider: Groq (https://console.groq.com), chosen because it's genuinely
free (no credit card, generous rate limits) and OpenAI-compatible, so we
call it with the standard `openai` SDK pointed at Groq's base_url. Swapping
to Anthropic, OpenAI, or any other OpenAI-compatible provider later only
means changing config.py + the client construction below - every caller
(tutor, quiz_engine, recommendation_engine, document_processor) is unaffected.
"""
import json
import time
import re
from openai import OpenAI
from sqlalchemy.orm import Session
from ..config import settings
from .. import models

# Groq's free tier has no per-token cost; cost logging is kept at 0 so the
# Analytics/Admin "estimated cost" fields stay meaningful if a paid provider
# is swapped in later.
_INPUT_COST_PER_M = 0.0
_OUTPUT_COST_PER_M = 0.0

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not settings.groq_api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Get a free key at https://console.groq.com/keys "
                "and copy backend/.env.example to backend/.env."
            )
        _client = OpenAI(api_key=settings.groq_api_key, base_url=settings.groq_base_url)
    return _client


def _log_usage(db: Session, feature: str, model: str, latency_ms: int,
               input_tokens: int, output_tokens: int, success: bool,
               error_message: str = "", user_id: int | None = None,
               project_id: int | None = None):
    cost = (input_tokens / 1_000_000) * _INPUT_COST_PER_M + \
           (output_tokens / 1_000_000) * _OUTPUT_COST_PER_M
    log = models.AIUsageLog(
        user_id=user_id, project_id=project_id, feature=feature, model=model,
        latency_ms=latency_ms, input_tokens=input_tokens, output_tokens=output_tokens,
        estimated_cost_usd=round(cost, 6), success=success, error_message=error_message,
    )
    db.add(log)
    db.commit()


def call_ai(
    db: Session,
    feature: str,
    system: str,
    user_message: str,
    max_tokens: int = 1024,
    user_id: int | None = None,
    project_id: int | None = None,
) -> str:
    """Call the model with a system+user prompt. Logs usage regardless of outcome."""
    model = settings.groq_model
    start = time.time()
    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
        )
        latency_ms = int((time.time() - start) * 1000)
        text = resp.choices[0].message.content or ""
        usage = resp.usage
        _log_usage(
            db, feature, model, latency_ms,
            usage.prompt_tokens if usage else 0,
            usage.completion_tokens if usage else 0,
            True, user_id=user_id, project_id=project_id,
        )
        return text
    except Exception as e:  # noqa: BLE001 - want to log and re-raise any provider failure
        latency_ms = int((time.time() - start) * 1000)
        _log_usage(
            db, feature, model, latency_ms, 0, 0, False,
            error_message=str(e), user_id=user_id, project_id=project_id,
        )
        raise


def call_ai_json(
    db: Session,
    feature: str,
    system: str,
    user_message: str,
    max_tokens: int = 1500,
    user_id: int | None = None,
    project_id: int | None = None,
) -> dict:
    """Call the model and parse a JSON object out of the response.

    We instruct the model to return only JSON and defensively extract the
    first {...} block in case it adds stray text, since AI-generated
    structured data must be validated before it's used (PRD section 8).
    """
    json_system = system + "\n\nRespond with ONLY a single valid JSON object. No prose, no markdown fences."
    raw = call_ai(db, feature, json_system, user_message, max_tokens, user_id, project_id)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"AI response for '{feature}' did not contain JSON: {raw[:200]}")
    return json.loads(match.group(0))
