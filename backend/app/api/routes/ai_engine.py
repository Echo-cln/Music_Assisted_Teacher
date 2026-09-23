
from fastapi import APIRouter, Depends
from app.core.security import get_current_teacher
from app.models.entities import Teacher

router = APIRouter(prefix="/ai-engine", tags=["AI教学引擎"])

DEFAULT_MODELS=[
 {"provider":"OpenAI","model":"GPT-5.6-terra"},
 {"provider":"Zhipu","model":"GLM-5.3-flash"},
 {"provider":"DeepSeek","model":"DeepSeek"},
 {"provider":"Qwen","model":"Qwen"},
]

@router.get("/models")
def models(teacher: Teacher=Depends(get_current_teacher)):
    return {"models":DEFAULT_MODELS}

@router.get("/config")
def config(teacher: Teacher=Depends(get_current_teacher)):
    return {"model":"auto","strategy":"standard"}
