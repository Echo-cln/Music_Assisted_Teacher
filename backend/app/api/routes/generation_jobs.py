from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import get_current_teacher
from app.models.entities import Teacher
from app.schemas.lesson import LessonGenerateRequest
from app.services.generation_service import create_generation_job, get_generation_job, list_generation_jobs

router = APIRouter(prefix="/generation-jobs", tags=["AI生成任务"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def create_job(payload: LessonGenerateRequest, teacher: Teacher = Depends(get_current_teacher)):
    try:
        return create_generation_job(teacher.id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("")
def list_jobs(
    limit: int = Query(default=10, ge=1, le=30),
    teacher: Teacher = Depends(get_current_teacher),
):
    return list_generation_jobs(teacher.id, limit)


@router.get("/{job_id}")
def get_job(job_id: str, teacher: Teacher = Depends(get_current_teacher)):
    try:
        return get_generation_job(teacher.id, job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
