import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from .database import Base, engine
from . import models  # noqa: F401 - ensures models are registered before create_all
from .routers import auth, spaces, projects, materials, tutor, quiz, mastery, analytics, admin

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Study Companion", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(spaces.router)
app.include_router(projects.router)
app.include_router(materials.router)
app.include_router(tutor.router)
app.include_router(quiz.router)
app.include_router(mastery.router)
app.include_router(analytics.router)
app.include_router(admin.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve the vanilla frontend from the same origin so the whole app is a
# single deployable unit (no separate frontend server / CORS setup needed).
_FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
if os.path.isdir(_FRONTEND_DIR):
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIR), name="assets")

    @app.get("/")
    def serve_index():
        return FileResponse(os.path.join(_FRONTEND_DIR, "index.html"))
