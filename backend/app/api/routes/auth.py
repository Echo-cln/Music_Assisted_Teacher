from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.security import clear_login_session, create_login_session, get_current_teacher, hash_password, verify_password
from app.db.session import get_db
from app.models.entities import Teacher
from app.schemas.auth import LoginRequest, RegisterRequest, TeacherRead

router = APIRouter(prefix="/auth", tags=["账号"])


def _teacher_read(teacher: Teacher) -> TeacherRead:
    return TeacherRead(
        id=teacher.id,
        username=teacher.username,
        display_name=teacher.display_name,
        email=teacher.email,
        school=teacher.school,
    )


@router.post("/register", response_model=TeacherRead, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    normalized_email = payload.email.strip().lower() if payload.email else None
    existing = db.scalar(
        select(Teacher).where(
            or_(
                Teacher.username == payload.username,
                Teacher.email == normalized_email if normalized_email else False,
            )
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="用户名或邮箱已被使用")
    password_hash, password_salt = hash_password(payload.password)
    teacher = Teacher(
        username=payload.username,
        email=normalized_email,
        display_name=payload.display_name.strip(),
        school=payload.school.strip(),
        password_hash=password_hash,
        password_salt=password_salt,
    )
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    create_login_session(db, teacher, response)
    return _teacher_read(teacher)


@router.post("/login", response_model=TeacherRead)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    account = payload.account.strip()
    teacher = db.scalar(select(Teacher).where(or_(Teacher.username == account, Teacher.email == account.lower())))
    if not teacher or not verify_password(payload.password, teacher.password_hash, teacher.password_salt):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    create_login_session(db, teacher, response)
    return _teacher_read(teacher)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    clear_login_session(db, request, response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return None


@router.get("/me", response_model=TeacherRead)
def me(teacher: Teacher = Depends(get_current_teacher)):
    return _teacher_read(teacher)
