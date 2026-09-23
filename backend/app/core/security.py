from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import AuthSession, Teacher

SESSION_COOKIE = "zhiban_session"
SESSION_DAYS = 7
PBKDF2_ITERATIONS = 240_000


def hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return digest.hex(), salt.hex()


def verify_password(password: str, expected_hash: str, salt_hex: str) -> bool:
    actual_hash, _ = hash_password(password, salt_hex)
    return hmac.compare_digest(actual_hash, expected_hash)


def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_login_session(db: Session, teacher: Teacher, response: Response) -> None:
    raw_token = secrets.token_urlsafe(40)
    expires_at = datetime.utcnow() + timedelta(days=SESSION_DAYS)
    db.add(AuthSession(teacher_id=teacher.id, token_hash=_token_hash(raw_token), expires_at=expires_at))
    db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        raw_token,
        max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )


def clear_login_session(db: Session, request: Request, response: Response) -> None:
    raw_token = request.cookies.get(SESSION_COOKIE)
    if raw_token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == _token_hash(raw_token)))
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


def get_current_teacher(request: Request, db: Session = Depends(get_db)) -> Teacher:
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    now = datetime.utcnow()
    session = db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == _token_hash(raw_token),
            AuthSession.expires_at > now,
        )
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效，请重新登录")
    teacher = db.get(Teacher, session.teacher_id)
    if not teacher:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不存在")
    return teacher
