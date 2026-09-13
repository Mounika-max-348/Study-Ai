from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from . import models
from .database import get_db
from .security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    email = decode_access_token(token)
    if not email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


def get_current_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user


def get_owned_project(project_id: int, db: Session, user: models.User) -> models.Project:
    """Enforce project-level data isolation: a user may only touch their own projects."""
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    if project.user_id != user.id and not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this project")
    return project
