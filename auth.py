# JWT-Authentifizierung und Passwort-Hashing für Memory Tree

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import User

_AUTH_ERROR = "Nicht authentifiziert"


def hash_password(password: str) -> str:
    """Passwort mit bcrypt hashen."""
    password_bytes: bytes = password.encode("utf-8")
    salt: bytes = bcrypt.gensalt()
    hashed: bytes = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Passwort gegen Hash prüfen."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt: str = jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
    return encoded_jwt


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token: str | None = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail=_AUTH_ERROR)
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        username: str | None = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail=_AUTH_ERROR)
    except JWTError:
        raise HTTPException(status_code=401, detail=_AUTH_ERROR)
    user: User | None = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(status_code=401, detail=_AUTH_ERROR)
    return user
