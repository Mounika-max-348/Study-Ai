# AI Study Companion

A prototype of an AI-powered learning workspace: upload study material, learn
with a grounded AI Tutor, get quizzed adaptively, track concept mastery, and
get a recommended next step — plus an Admin Dashboard for platform-wide
visibility. Built against the "AI Study Companion" PRD (Candidate Challenge
Edition, v3.0).

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for design decisions, the AI usage
breakdown, evaluation approach, known limitations, and future improvements.

## Stack

- **Backend**: Python, FastAPI, SQLAlchemy, SQLite
- **AI**: Groq API (free, OpenAI-compatible, via the `openai` SDK) — Tutor, quiz generation/grading, recommendations, concept extraction
- **Retrieval**: TF-IDF (scikit-learn) over chunked PDF text — see ARCHITECTURE.md for why
- **Background processing**: FastAPI `BackgroundTasks` for async document processing
- **Frontend**: Vanilla HTML/CSS/JS (no build step), served by the same FastAPI app
- **Auth**: JWT (python-jose) + bcrypt password hashing

## Project layout

```
ai-study-companion/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, mounts routers + serves frontend
│   │   ├── config.py             # env-based settings
│   │   ├── database.py           # SQLAlchemy engine/session
│   │   ├── models.py             # ORM models (User, Space, Project, Material, ...)
│   │   ├── schemas.py            # Pydantic request/response schemas
│   │   ├── security.py           # JWT + bcrypt
│   │   ├── deps.py               # auth dependencies, project-ownership checks
│   │   ├── routers/              # one file per API area
│   │   └── services/
│   │       ├── ai_client.py           # Anthropic wrapper + usage/cost logging
│   │       ├── document_processor.py  # PDF → chunks → concepts (background job)
│   │       ├── retrieval.py           # TF-IDF retrieval
│   │       ├── quiz_engine.py         # adaptive question generation + grading
│   │       ├── mastery_engine.py      # mastery score updates (EMA)
│   │       └── recommendation_engine.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js                    # vanilla JS SPA — no framework/build step
├── README.md
└── ARCHITECTURE.md
```

## Prerequisites

- Python 3.10+
- A free Groq API key ([console.groq.com/keys](https://console.groq.com/keys)) — no credit card required. Needed for the Tutor, quiz generation/grading, concept extraction, and recommendations. Everything else (auth, spaces/projects, PDF upload/chunking, dashboards) works without it.

## Run it locally

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# then edit .env and set GROQ_API_KEY=gsk-... (get one free at console.groq.com/keys)

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000** — the same FastAPI server serves both the API
and the frontend, so there's nothing else to run. Interactive API docs are at
**http://localhost:8000/docs**.

The first account you register becomes the admin automatically (see the
"Create account" tab) — use that account to see the Admin Dashboard link in
the sidebar.

### Quick walkthrough of the core loop

1. Register → you land on Home.
2. **+ New space** (e.g. "Machine Learning") → click it → **+ New project**, give it a name and a learning goal.
3. Open the project → **Materials** tab → upload a PDF. Status moves `queued → processing → ready` (poll happens automatically in the UI).
4. **Tutor** tab → ask a question grounded in that PDF. Ask something the PDF doesn't cover to see the "insufficient evidence" handling.
5. **Quiz** tab → start a quiz → answer a few MCQ/open questions → see mastery update live.
6. **Mastery & Growth** tab → see per-concept mastery, trend, and the generated recommendation.
7. **Analytics** (project tab, and the sidebar's "Global analytics" link) and, if you're the admin, the **Admin dashboard** link.

## Configuration reference (`backend/.env`)

| Variable | Purpose |
|---|---|
| `GROQ_API_KEY` | Required for all AI features — free at console.groq.com/keys |
| `GROQ_MODEL` | Defaults to `llama-3.3-70b-versatile` |
| `GROQ_BASE_URL` | Groq's OpenAI-compatible endpoint — leave as-is |
| `JWT_SECRET` | Sign/verify auth tokens — use a long random string in production |
| `DATABASE_URL` | Defaults to a local SQLite file |
| `UPLOAD_DIR` | Where uploaded PDFs are stored on disk |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT lifetime |

## Testing

A minimal but meaningful smoke-test flow (auth → space → project → PDF
upload/processing → dashboard/analytics/admin endpoints) was run manually
against a live server during development — every endpoint the frontend
depends on returns correct data, and AI-call failures (e.g. an invalid key)
are caught, logged to `AIUsageLog`, and surfaced as clean error messages
rather than crashing the request. For an actual test suite, see
"Known Limitations" in ARCHITECTURE.md for what a `pytest` suite covering
auth/isolation/mastery-updates/adaptive-selection would look like — this
wasn't included in the generated prototype to keep the handoff focused, but
is a natural next addition.

## Deployment

This is a single deployable unit (FastAPI serves the frontend too), so any
platform that runs a Python web service works: Render, Railway, Fly.io, a
plain VM behind nginx, etc. Set the environment variables from the table
above, point `DATABASE_URL` at a persistent volume (or swap SQLite for
Postgres by changing that one setting), and run:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Never commit `.env` — only `.env.example` is checked in.
