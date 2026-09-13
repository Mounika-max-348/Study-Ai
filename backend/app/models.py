import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, ForeignKey, Text, DateTime
)
from sqlalchemy.orm import relationship
from .database import Base


def now():
    return datetime.datetime.utcnow()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, default="")
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)

    spaces = relationship("Space", back_populates="owner", cascade="all, delete-orphan")


class Space(Base):
    __tablename__ = "spaces"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=now)

    owner = relationship("User", back_populates="spaces")
    projects = relationship("Project", back_populates="space", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    space_id = Column(Integer, ForeignKey("spaces.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    goal = Column(Text, default="")
    created_at = Column(DateTime, default=now)

    space = relationship("Space", back_populates="projects")
    materials = relationship("Material", back_populates="project", cascade="all, delete-orphan")
    concepts = relationship("Concept", back_populates="project", cascade="all, delete-orphan")
    messages = relationship("ConversationMessage", back_populates="project", cascade="all, delete-orphan")


class Material(Base):
    __tablename__ = "materials"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    filepath = Column(String, nullable=False)
    status = Column(String, default="queued")  # queued|processing|ready|failed
    page_count = Column(Integer, default=0)
    error_message = Column(Text, default="")
    created_at = Column(DateTime, default=now)

    project = relationship("Project", back_populates="materials")
    chunks = relationship("Chunk", back_populates="material", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"
    id = Column(Integer, primary_key=True)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    page_number = Column(Integer, default=1)
    chunk_index = Column(Integer, default=0)

    material = relationship("Material", back_populates="chunks")


class Concept(Base):
    __tablename__ = "concepts"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    mastery_score = Column(Float, default=30.0)
    attempts = Column(Integer, default=0)
    correct = Column(Integer, default=0)
    updated_at = Column(DateTime, default=now)

    project = relationship("Project", back_populates="concepts")


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    role = Column(String, nullable=False)  # user|assistant
    content = Column(Text, nullable=False)
    citations = Column(Text, default="[]")  # JSON string
    insufficient_evidence = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)

    project = relationship("Project", back_populates="messages")


class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    concept_id = Column(Integer, ForeignKey("concepts.id"), nullable=True)
    attempt_id = Column(Integer, ForeignKey("quiz_attempts.id"), nullable=False, index=True)
    type = Column(String, nullable=False)  # mcq|open
    prompt = Column(Text, nullable=False)
    options = Column(Text, default="[]")  # JSON string, mcq only
    correct_answer = Column(Text, default="")
    difficulty = Column(String, default="medium")  # easy|medium|hard
    order_index = Column(Integer, default=0)
    created_at = Column(DateTime, default=now)


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    status = Column(String, default="in_progress")  # in_progress|completed
    started_at = Column(DateTime, default=now)
    completed_at = Column(DateTime, nullable=True)


class QuizAnswer(Base):
    __tablename__ = "quiz_answers"
    id = Column(Integer, primary_key=True)
    attempt_id = Column(Integer, ForeignKey("quiz_attempts.id"), nullable=False, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False, index=True)
    user_answer = Column(Text, default="")
    is_correct = Column(Boolean, nullable=True)
    score = Column(Float, nullable=True)  # 0-100, open-ended
    feedback = Column(Text, default="")
    created_at = Column(DateTime, default=now)


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, index=True)
    type = Column(String, nullable=False)
    payload = Column(Text, default="{}")
    created_at = Column(DateTime, default=now)


class Recommendation(Base):
    __tablename__ = "recommendations"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=now)


class AIUsageLog(Base):
    __tablename__ = "ai_usage_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, index=True)
    feature = Column(String, nullable=False)  # tutor|quiz_gen|quiz_grade|recommendation
    model = Column(String, default="")
    latency_ms = Column(Integer, default=0)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    estimated_cost_usd = Column(Float, default=0.0)
    success = Column(Boolean, default=True)
    error_message = Column(Text, default="")
    created_at = Column(DateTime, default=now)
