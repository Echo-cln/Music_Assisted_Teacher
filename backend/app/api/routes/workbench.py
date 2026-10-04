import json
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_teacher
from app.db.session import get_db
from app.models.entities import ArrangementProject, Teacher
from app.schemas.workbench import ArrangeRequest, ProjectCreate
from app.services.arrangement_service import arrange, parse_midi, parse_musicxml, parse_note_text

router = APIRouter(prefix="/workbench", tags=["数字乐器与智能编曲"])


def present(row: ArrangementProject) -> dict:
    return {
        "id": row.id, "title": row.title, "source_kind": row.source_kind, "tempo": row.tempo, "style": row.style,
        "melody": json.loads(row.melody_json or "[]"), "arrangement": json.loads(row.arrangement_json or "{}"),
        "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
    }


def own(project_id: int, db: Session, teacher: Teacher) -> ArrangementProject:
    row = db.scalar(select(ArrangementProject).where(ArrangementProject.id == project_id, ArrangementProject.teacher_id == teacher.id))
    if not row:
        raise HTTPException(404, "编曲工程不存在或无权访问")
    return row


@router.get("/projects")
def projects(db: Session = Depends(get_db), teacher: Teacher = Depends(get_current_teacher)):
    rows = db.scalars(select(ArrangementProject).where(ArrangementProject.teacher_id == teacher.id).order_by(ArrangementProject.updated_at.desc()).limit(60)).all()
    return [present(row) for row in rows]


@router.get("/projects/{project_id}")
def project(project_id: int, db: Session = Depends(get_db), teacher: Teacher = Depends(get_current_teacher)):
    return present(own(project_id, db, teacher))


@router.post("/projects", status_code=201)
def create(payload: ProjectCreate, db: Session = Depends(get_db), teacher: Teacher = Depends(get_current_teacher)):
    melody = [n.model_dump() for n in payload.melody]
    row = ArrangementProject(teacher_id=teacher.id, title=payload.title, tempo=payload.tempo, style=payload.style,
                             melody_json=json.dumps(melody, ensure_ascii=False), arrangement_json=json.dumps(arrange(melody, payload.tempo, payload.style, payload.instruments), ensure_ascii=False))
    db.add(row); db.commit(); db.refresh(row)
    return present(row)


@router.post("/projects/{project_id}/arrange")
def make_arrangement(project_id: int, payload: ArrangeRequest, db: Session = Depends(get_db), teacher: Teacher = Depends(get_current_teacher)):
    row = own(project_id, db, teacher)
    melody = [n.model_dump() for n in payload.melody] or json.loads(row.melody_json or "[]")
    if not melody:
        raise HTTPException(422, "请先输入旋律，或导入 MusicXML / MIDI 乐谱")
    row.tempo, row.style = payload.tempo, payload.style
    row.melody_json = json.dumps(melody, ensure_ascii=False)
    row.arrangement_json = json.dumps(arrange(melody, payload.tempo, payload.style, payload.instruments), ensure_ascii=False)
    row.updated_at = datetime.utcnow()
    db.commit(); db.refresh(row)
    return present(row)


@router.post("/import", status_code=201)
async def import_score(file: UploadFile = File(...), db: Session = Depends(get_db), teacher: Teacher = Depends(get_current_teacher)):
    name = file.filename or "导入乐谱"
    suffix = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    raw = await file.read()
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(413, "乐谱文件不能超过 8MB")
    try:
        if suffix in {"musicxml", "xml"}:
            melody, tempo, source = parse_musicxml(raw), 96, "musicxml"
        elif suffix in {"mid", "midi"}:
            melody, tempo, source = (*parse_midi(raw), "midi")
        else:
            raise HTTPException(422, "目前可直接导入 MusicXML（.musicxml/.xml）或 MIDI（.mid/.midi）")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, f"未能读取乐谱：{exc}") from exc
    if not melody:
        raise HTTPException(422, "乐谱中没有识别到可播放音符")
    row = ArrangementProject(teacher_id=teacher.id, title=name.rsplit('.', 1)[0], source_kind=source, tempo=tempo,
                             melody_json=json.dumps(melody, ensure_ascii=False), arrangement_json=json.dumps(arrange(melody, tempo, "乡土抒情", ["piano", "guzheng", "drum"]), ensure_ascii=False))
    db.add(row); db.commit(); db.refresh(row)
    return present(row)


@router.post("/parse-notes")
def parse_notes(payload: dict):
    tempo = int(payload.get("tempo", 96))
    return {"melody": parse_note_text(str(payload.get("notes", "")), max(40, min(220, tempo)))}


@router.delete("/projects/{project_id}", status_code=204)
def delete(project_id: int, db: Session = Depends(get_db), teacher: Teacher = Depends(get_current_teacher)):
    db.delete(own(project_id, db, teacher)); db.commit()

