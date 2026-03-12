# Authentifizierungs-Routen: Login und Logout

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from auth import verify_password, create_access_token
from database import get_db
from models import User

router = APIRouter(prefix="/auth", tags=["Authentifizierung"])

templates = Jinja2Templates(directory="templates")


@router.get("/login")
def login_page(request: Request) -> Response:
    """Login-Seite anzeigen."""
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
def login(
    request: Request,
    username: Annotated[str, Form(...)],
    password: Annotated[str, Form(...)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Anmeldedaten prüfen, JWT-Cookie setzen und zum Dashboard weiterleiten."""
    user: User | None = db.query(User).filter(User.username == username).first()

    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Ungültige Anmeldedaten"},
            status_code=401,
        )

    access_token: str = create_access_token(data={"sub": user.username})

    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/logout")
def logout() -> Response:
    """Cookie löschen und zur Login-Seite weiterleiten."""
    response = RedirectResponse(url="/auth/login", status_code=303)
    response.delete_cookie(key="access_token")
    return response
