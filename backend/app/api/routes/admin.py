from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.models.entities import Teacher

router = APIRouter(prefix="/admin", tags=["系统管理"])

class UserUpdate(BaseModel):
    role: str | None = None
    verification_status: str | None = None

@router.get("/users")
def users(db: Session = Depends(get_db), admin: Teacher = Depends(require_admin)):
    return [{"id": item.id, "username": item.username, "display_name": item.display_name, "email": item.email, "school": item.school, "role": item.role, "verification_status": item.verification_status, "created_at": item.created_at.isoformat(timespec="seconds")} for item in db.scalars(select(Teacher).order_by(Teacher.created_at.desc())).all()]

@router.patch("/users/{user_id}")
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db), admin: Teacher = Depends(require_admin)):
    item = db.get(Teacher, user_id)
    if not item: raise HTTPException(status_code=404, detail="用户不存在")
    if payload.role is not None:
        if payload.role not in {"teacher", "admin"}: raise HTTPException(status_code=422, detail="不支持的角色")
        item.role = payload.role
    if payload.verification_status is not None:
        if payload.verification_status not in {"unverified", "email_verified", "verified", "suspended"}: raise HTTPException(status_code=422, detail="不支持的认证状态")
        item.verification_status = payload.verification_status
    db.commit()
    return {"id": item.id, "role": item.role, "verification_status": item.verification_status}
