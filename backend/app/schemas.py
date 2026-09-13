from pydantic import BaseModel, EmailStr
from typing import Optional, List
import datetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str = ""


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    is_admin: bool

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class SpaceCreate(BaseModel):
    name: str
    description: str = ""


class SpaceOut(BaseModel):
    id: int
    name: str
    description: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class ProjectCreate(BaseModel):
    space_id: int
    name: str
    description: str = ""
    goal: str = ""


class ProjectOut(BaseModel):
    id: int
    space_id: int
    name: str
    description: str
    goal: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class MaterialOut(BaseModel):
    id: int
    project_id: int
    filename: str
    status: str
    page_count: int
    error_message: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class TutorAskRequest(BaseModel):
    question: str


class CitationOut(BaseModel):
    source: str
    page: int
    snippet: str


class TutorAskResponse(BaseModel):
    answer: str
    citations: List[CitationOut]
    insufficient_evidence: bool


class ConceptOut(BaseModel):
    id: int
    name: str
    mastery_score: float
    attempts: int
    correct: int

    class Config:
        from_attributes = True


class QuizStartRequest(BaseModel):
    num_questions: int = 5


class QuestionOut(BaseModel):
    id: int
    type: str
    prompt: str
    options: List[str]
    difficulty: str
    concept: Optional[str] = None


class QuizAttemptOut(BaseModel):
    attempt_id: int
    questions: List[QuestionOut]


class AnswerSubmitRequest(BaseModel):
    question_id: int
    answer: str


class AnswerResultOut(BaseModel):
    question_id: int
    is_correct: Optional[bool]
    score: Optional[float]
    feedback: str
    correct_answer: str


class RecommendationOut(BaseModel):
    id: int
    text: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True
