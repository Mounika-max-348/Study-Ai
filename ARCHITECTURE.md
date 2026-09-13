# Architecture

## System diagram

```
┌──────────────────────┐
│   Frontend (vanilla   │   served at "/" by the same FastAPI app
│   HTML/CSS/JS SPA)    │   talks to the API via fetch(), JWT in
└──────────┬────────────┘   Authorization header
           │ HTTPS/JSON
┌──────────▼────────────┐
│   FastAPI app          │
│   ┌──────────────────┐ │
│   │ Routers           │ │  auth, spaces, projects, materials,
│   │ (thin, validate + │ │  tutor, quiz, mastery, analytics, admin
│   │  authorize)        │ │
│   └────────┬───────────┘ │
│   ┌────────▼───────────┐ │
│   │ Services            │ │  document_processor, retrieval,
│   │ (business logic)    │ │  quiz_engine, mastery_engine,
│   │                      │ │  recommendation_engine, ai_client
│   └────────┬───────────┘ │
└────────────┼──────────────┘
             │
   ┌─────────┼───────────────┐
   │         │               │
┌──▼───┐ ┌───▼────┐   ┌──────▼───────┐
│SQLite│ │ Uploaded │   │  Groq API     │
│  DB  │ │ PDFs on  │   │ (Tutor, quiz  │
│      │ │  disk    │   │ gen/grading,  │
└──────┘ └──────────┘   │ concepts,     │
                          │ recommendations)│
                          └───────────────┘

Background: FastAPI BackgroundTasks run document_processor.process_material()
off the request thread after upload (Queued → Processing → Chunking →
Concept extraction → Ready/Failed).
```

## Data model (SQLite via SQLAlchemy)

`User → Space → Project → {Material → Chunk, Concept, ConversationMessage,
QuizAttempt → Question → QuizAnswer, Recommendation}`, plus cross-cutting
`Event` (activity log) and `AIUsageLog` (observability) tables scoped by
`user_id`/`project_id`. Every project-scoped query filters by `project_id`
and every router checks `project.user_id == current_user.id` (see
`deps.get_owned_project`) — this is the data-isolation mechanism the PRD
calls out as a security requirement.

## Key decisions and why

**FastAPI + SQLite, single deployable process.** The PRD explicitly scopes
this as a 3–4 day prototype, not a production platform. A single Python
service serving both API and static frontend minimizes deployment surface
area (one process, one env file) while the architecture (routers → services
→ models) still separates concerns cleanly enough to swap pieces later
(e.g. SQLite → Postgres is a one-line `DATABASE_URL` change; SQLAlchemy
already abstracts the dialect).

**TF-IDF retrieval instead of vector embeddings.** The PRD leaves retrieval
technology open. TF-IDF (scikit-learn) needs no embeddings API, no vector
database, and no extra infrastructure — it runs entirely in-process and is
good enough to ground Tutor answers and quiz questions in the right PDF
pages for a prototype's material sizes. The tradeoff: it's keyword-based, so
it will miss paraphrased/semantic matches that embeddings would catch. The
`retrieval.retrieve()` function is the single seam where this would be
swapped for an embeddings + vector-index implementation without touching
callers (Tutor, quiz generation).

**FastAPI `BackgroundTasks` instead of Celery/Redis.** Document processing
needs to be asynchronous per the PRD, but it doesn't need to survive a
server restart or run across multiple worker processes for a prototype.
`BackgroundTasks` gives non-blocking async processing with zero extra
infrastructure to run/deploy. Documented tradeoff: no persistence if the
process crashes mid-job, no retry-with-backoff, no multi-worker distribution
— a real deployment would move this to Celery+Redis or an SQS-style queue
behind the same `process_material(material_id)` entry point.

**Structured JSON over free text for every AI call that feeds application
state.** `ai_client.call_ai_json()` instructs the model to return only JSON,
then defensively extracts and parses it. This is the PRD's "AI-generated
structured data should be validated before it's persisted" requirement —
concept names, quiz questions/answers, and grading results are all parsed
data, not prose the UI has to scrape.

**Mastery as an exponential moving average, not a running average.** Each
quiz answer updates `mastery_score = 0.65 * old + 0.35 * new_performance`
(see `mastery_engine.py`), so recent evidence matters more than old evidence
without one lucky/unlucky answer swinging the score wildly — closer to how
the PRD describes mastery as "an estimate... that evolves."

**Adaptive question selection by weakest-concept + attempts, not
last-answer.** `quiz_engine._select_concept()` always targets the lowest-
mastery concept (tie-broken by fewest attempts, so untested concepts aren't
starved), and difficulty is derived from that concept's current mastery
band, not the previous question's result — this directly addresses the
PRD's explicit "not simply wrong→easy, correct→hard" requirement.

**Grounded Tutor with a hard insufficient-evidence path.** The Tutor prompt
instructs the model to answer only from retrieved material and to set
`insufficient_evidence: true` rather than fill gaps from outside knowledge;
the frontend visually distinguishes these responses and suppresses
citations on them. Untrusted-content handling: the same system prompt tells
the model to treat material excerpts and conversation history as data, not
instructions, addressing the PRD's prompt-injection concern for
learner-uploaded content.

**Conversation continuity without full history.** The Tutor includes only
the last few turns (`RECENT_TURNS = 4`) rather than the full conversation,
per the PRD's "persistent but relevant" principle — this keeps prompts
small and avoids one Project's chat history silently growing every request.

**Observability centralized in one wrapper.** Every AI call — Tutor, quiz
generation, quiz grading, concept extraction, recommendations — goes
through `ai_client.call_ai()`/`call_ai_json()`, which logs feature, model,
latency, token counts, an estimated cost, and success/failure to
`AIUsageLog` regardless of outcome. This is what powers both the per-project
Analytics tab and the Admin "AI usage" / "System health" views, and it's
also why a bad API key degrades gracefully (a clear 502 with a readable
message) instead of crashing requests — verified during development by
running the whole flow against an intentionally invalid key.

## AI usage documentation

**AI used to build this product:** Claude (via this chat/agent environment)
was used to scaffold, write, and iteratively test the entire backend and
frontend in this repository.

**AI used by the running product** (all via the Groq API — chosen because
it's genuinely free with no credit card, fast, and OpenAI-compatible so it
drops in through the standard `openai` SDK; model configured through
`GROQ_MODEL`, default `llama-3.3-70b-versatile`):
- **Tutor** — grounded Q&A with citations / insufficient-evidence detection
- **Concept extraction** — proposes concepts from uploaded material during processing
- **Quiz generation** — writes MCQ/open-ended questions targeted at a concept + difficulty
- **Quiz grading** — scores open-ended answers with explanatory feedback
- **Recommendations** — turns mastery + recent performance into a next-step suggestion

## Evaluation approach

Not included as an automated suite in this handoff, but the design supports
one directly: because every AI call is JSON-structured and logged, a
regression check is "run a curated set of (project, question) or (project,
material) fixtures through the Tutor/quiz/recommendation functions and
assert on `insufficient_evidence` correctness, citation page-number
validity against known source chunks, and JSON-schema conformance" — all
checkable without a human in the loop. Retrieval quality can be spot-checked
by asserting the top-`k` chunks for a known query contain the expected page.
This is the natural next addition (see Future Improvements).

## Known limitations

- **No automated test suite included** — endpoints were verified manually end-to-end during development (see README "Testing"), but there's no `pytest` suite in the repo yet.
- **TF-IDF retrieval is keyword-based**, not semantic — paraphrased questions may retrieve weaker evidence than an embeddings-based approach would.
- **Background jobs use in-process `BackgroundTasks`**, not a durable queue — a crash mid-processing leaves a material stuck in `processing` with no automatic retry.
- **No OCR** — scanned/image-only PDF pages produce no extractable text and the material is marked `failed` with an explanit message rather than silently losing content.
- **Growth trend is derived from lifetime attempts vs. current EMA**, not a stored historical time series — there's no true "mastery over time" chart, only a per-concept improving/stable/needs-attention classification.
- **Global Analytics is user-scoped**; only the Admin Dashboard aggregates across all users, matching the PRD's split between per-user "Global Analytics" and platform-wide Admin visibility.
- **Single API key/provider model** — no per-request model/provider switching or fallback if Groq is unavailable. `ai_client.py` is the single seam where a paid provider (Anthropic, OpenAI) could be swapped in or added as a fallback later.
- **Groq's free tier has rate limits** (requests/tokens per minute) — under heavy concurrent use (e.g. many quiz questions generated back-to-back) calls may need retry/backoff, which isn't implemented yet.
- **No rate limiting or caching** on AI calls.

## Future improvements

- Real automated test suite (auth/isolation, mastery update math, adaptive selection, background job retry/failure).
- Swap TF-IDF for embeddings + a vector index behind the same `retrieve()` interface.
- Celery/Redis (or SQS) for durable background processing with retries and multi-worker scaling.
- Streaming Tutor responses (SSE) instead of a single blocking call.
- Store periodic mastery snapshots for a true growth-over-time chart.
- Automated regression evaluation harness using the JSON-structured AI outputs described above.
- OCR fallback for scanned pages (e.g. via a hosted OCR API or `pytesseract`).
