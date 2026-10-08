import hashlib
import secrets
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.security import clear_login_session, create_login_session, get_current_teacher, hash_password, verify_password
from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import Teacher, VerificationCode
from app.schemas.auth import LoginRequest, RegisterRequest, TeacherRead, VerificationRequest

router = APIRouter(prefix="/auth", tags=["账号"])


def _teacher_read(teacher: Teacher) -> TeacherRead:
    return TeacherRead(
        id=teacher.id,
        username=teacher.username,
        display_name=teacher.display_name,
        email=teacher.email,
        school=teacher.school,
        role=teacher.role,
        verification_status=teacher.verification_status,
    )


def _code_hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


@router.post("/verification/email")
def request_email_verification(payload: VerificationRequest, db: Session = Depends(get_db)):
    settings = get_settings()
    if not all([settings.smtp_host, settings.smtp_username, settings.smtp_password, settings.smtp_from]):
        raise HTTPException(status_code=503, detail="邮件验证码服务尚未配置；请在 backend/.env 配置 SMTP_HOST、SMTP_USERNAME、SMTP_PASSWORD、SMTP_FROM")
    email = payload.email.strip().lower()
    now = datetime.utcnow()
    recent = db.scalar(select(VerificationCode.created_at).where(
        VerificationCode.target == email,
        VerificationCode.channel == "email",
        VerificationCode.created_at >= now - timedelta(minutes=1),
    ).order_by(VerificationCode.created_at.desc()).limit(1))
    if recent:
        retry_after = max(1, 60 - int((now - recent).total_seconds()))
        raise HTTPException(status_code=429, detail="验证码已发送，请稍后再试", headers={"Retry-After": str(retry_after)})
    issued_last_hour = db.scalar(select(func.count()).select_from(VerificationCode).where(
        VerificationCode.target == email,
        VerificationCode.channel == "email",
        VerificationCode.created_at >= now - timedelta(hours=1),
    )) or 0
    if issued_last_hour >= 5:
        raise HTTPException(status_code=429, detail="此邮箱一小时内的验证码请求已达上限，请稍后再试", headers={"Retry-After": "3600"})
    code = f"{secrets.randbelow(1_000_000):06d}"
    verification = VerificationCode(target=email, channel="email", code_hash=_code_hash(code), expires_at=now + timedelta(minutes=10))
    message = EmailMessage()
    message["Subject"] = "乡音智谱注册验证码"
    message["From"], message["To"] = settings.smtp_from, email
    message.set_content(f"您的乡音智谱注册验证码为：{code}\n有效期 10 分钟。请勿向他人泄露。")
    try:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"邮件发送失败：{str(exc)[:120]}")
    db.execute(delete(VerificationCode).where(
        VerificationCode.expires_at <= now,
    ))
    db.add(verification)
    db.commit()
    return {"message": "验证码已发送，请在 10 分钟内填写"}


@router.post("/register", response_model=TeacherRead, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    normalized_email = payload.email.strip().lower()
    if payload.password != payload.password_confirm:
        raise HTTPException(status_code=422, detail="两次输入的密码不一致")
    verification = db.scalar(select(VerificationCode).where(VerificationCode.target == normalized_email, VerificationCode.channel == "email", VerificationCode.consumed_at.is_(None), VerificationCode.expires_at > datetime.utcnow()).order_by(VerificationCode.created_at.desc()))
    if not verification or verification.code_hash != _code_hash(payload.verification_code):
        raise HTTPException(status_code=422, detail="邮箱验证码无效或已过期")
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
        verification_status="email_verified",
    )
    db.add(teacher)
    verification.consumed_at = datetime.utcnow()
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
