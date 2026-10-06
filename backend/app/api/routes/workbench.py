import json
from datetime import datetime
import hashlib
import json
from pathlib import Path
import tempfile
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_teacher
from app.db.session import get_db
from app.models.entities import ArrangementProject, InstrumentSoundfont, Teacher
from app.schemas.workbench import ArrangeRequest, ProjectCreate
from app.services.arrangement_service import arrange, parse_midi, parse_musicxml, parse_note_text
from app.services.omr_service import OMRUnavailableError, SUPPORTED_OMR_SUFFIXES, recognize_staff_image
from app.services.object_storage import ObjectStorageError, delete_object, download_object, is_remote_ref, upload_local_file

router = APIRouter(prefix="/workbench", tags=["数字乐器与智能编曲"])


def present(row: ArrangementProject) -> dict:
    return {
        "id": row.id, "title": row.title, "source_kind": row.source_kind, "tempo": row.tempo, "style": row.style,
        "melody": json.loads(row.melody_json or "[]"), "arrangement": json.loads(row.arrangement_json or "{}"),
        "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
    }


def present_summary(row: ArrangementProject) -> dict:
    """工程侧栏只需要元数据，绝不能把所有轨道 JSON 一次传回浏览器。

    旧实现最多传 60 个完整工程，每个工程都包含音符、编曲声部和和弦；工程增多后
    点击一个项目之前就要反复解码、传输和渲染大量无关数据，造成明显卡顿。
    """
    return {
        "id": row.id,
        "title": row.title,
        "source_kind": row.source_kind,
        "tempo": row.tempo,
        "style": row.style,
        "updated_at": row.updated_at.isoformat(),
    }


def own(project_id: int, db: Session, teacher: Teacher) -> ArrangementProject:
    row = db.scalar(select(ArrangementProject).where(ArrangementProject.id == project_id, ArrangementProject.teacher_id == teacher.id))
    if not row:
        raise HTTPException(404, "编曲工程不存在或无权访问")
    return row


@router.get("/projects")
def projects(db: Session = Depends(get_db), teacher: Teacher = Depends(get_current_teacher)):
    rows = db.scalars(select(ArrangementProject).where(ArrangementProject.teacher_id == teacher.id).order_by(ArrangementProject.updated_at.desc()).limit(60)).all()
    return [present_summary(row) for row in rows]


@router.get("/projects/{project_id}")
def project(project_id: int, db: Session = Depends(get_db), teacher: Teacher = Depends(get_current_teacher)):
    return present(own(project_id, db, teacher))


@router.post("/projects", status_code=201)
def create(payload: ProjectCreate, db: Session = Depends(get_db), teacher: Teacher = Depends(get_current_teacher)):
    melody = [n.model_dump() for n in payload.melody]
    row = ArrangementProject(teacher_id=teacher.id, title=payload.title, tempo=payload.tempo, style=payload.style,
                             melody_json=json.dumps(melody, ensure_ascii=False), arrangement_json=json.dumps(arrange(melody, payload.tempo, payload.style, payload.instruments, payload.meter_numerator, payload.grid_division, payload.bars), ensure_ascii=False))
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
    row.arrangement_json = json.dumps(arrange(melody, payload.tempo, payload.style, payload.instruments, payload.meter_numerator, payload.grid_division, payload.bars), ensure_ascii=False)
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
        import_notice = None
        if suffix in {"musicxml", "xml", "mxl"}:
            melody, tempo, source = parse_musicxml(raw), 96, "musicxml"
        elif suffix in {"mid", "midi"}:
            melody, tempo, source = (*parse_midi(raw), "midi")
        elif suffix in SUPPORTED_OMR_SUFFIXES:
            musicxml, recognition = recognize_staff_image(raw, name, suffix)
            melody, tempo, source = parse_musicxml(musicxml), 96, "omr"
            import_notice = recognition["warning"]
        else:
            raise HTTPException(422, "支持 MusicXML（.musicxml/.xml/.mxl）、MIDI（.mid/.midi），或已配置 Audiveris 后的 PNG/JPG/WEBP/TIFF/PDF 五线谱")
    except OMRUnavailableError as exc:
        raise HTTPException(503, str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, f"未能读取乐谱：{exc}") from exc
    if not melody:
        raise HTTPException(422, "乐谱中没有识别到可播放音符")
    row = ArrangementProject(teacher_id=teacher.id, title=name.rsplit('.', 1)[0], source_kind=source, tempo=tempo,
                             melody_json=json.dumps(melody, ensure_ascii=False), arrangement_json=json.dumps(arrange(melody, tempo, "乡土抒情", ["piano", "guzheng", "drum"], 4, 4, 4), ensure_ascii=False))
    db.add(row); db.commit(); db.refresh(row)
    data = present(row)
    if import_notice:
        data["import_notice"] = import_notice
    return data


@router.post("/parse-notes")
def parse_notes(payload: dict):
    tempo = int(payload.get("tempo", 96))
    return {"melody": parse_note_text(str(payload.get("notes", "")), max(40, min(220, tempo)))}


@router.delete("/projects/{project_id}", status_code=204)
def delete(project_id: int, db: Session = Depends(get_db), teacher: Teacher = Depends(get_current_teacher)):
    db.delete(own(project_id, db, teacher)); db.commit()


SOUNDFONT_MAX_BYTES = 128 * 1024 * 1024
SOUNDFONT_INSTRUMENTS = {"piano", "violin", "guzheng", "erhu", "guitar", "drum"}


def present_soundfont(row: InstrumentSoundfont) -> dict:
    return {
        "id": row.id,
        "display_name": row.display_name,
        "original_filename": row.original_filename,
        "file_size": row.file_size,
        "sha256": row.sha256,
        "instruments": json.loads(row.instruments_json or "[]"),
        "preset_name": row.preset_name,
        "created_at": row.created_at.isoformat(),
    }


def own_soundfont(asset_id: int, db: Session, teacher: Teacher) -> InstrumentSoundfont:
    row = db.scalar(select(InstrumentSoundfont).where(
        InstrumentSoundfont.id == asset_id,
        InstrumentSoundfont.teacher_id == teacher.id,
    ))
    if row is None:
        raise HTTPException(404, "云端音色包不存在或无权访问")
    return row


@router.get("/soundfonts")
def list_soundfonts(db: Session = Depends(get_db), teacher: Teacher = Depends(get_current_teacher)):
    rows = db.scalars(
        select(InstrumentSoundfont)
        .where(InstrumentSoundfont.teacher_id == teacher.id)
        .order_by(InstrumentSoundfont.updated_at.desc())
    ).all()
    return [present_soundfont(row) for row in rows]


@router.post("/soundfonts", status_code=201)
async def upload_soundfont(
    file: UploadFile = File(...),
    display_name: str = Form(""),
    instruments: str = Form("[]"),
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    filename = (file.filename or "soundfont.sf2").replace("\\", "/").rsplit("/", 1)[-1]
    if not filename.lower().endswith(".sf2"):
        raise HTTPException(415, "只接受 .sf2 音色包")
    try:
        assigned = json.loads(instruments)
    except (TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(422, "乐器绑定格式无效") from exc
    if not isinstance(assigned, list):
        raise HTTPException(422, "乐器绑定必须是列表")
    assigned = sorted({str(value) for value in assigned if str(value) in SOUNDFONT_INSTRUMENTS})
    if not assigned:
        raise HTTPException(422, "请至少绑定一种乐器")
    label = (display_name or filename[:-4]).strip()[:100]
    if not label:
        raise HTTPException(422, "请填写音色包名称")

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix="soundfont-", suffix=".sf2", delete=False) as temp:
            temp_path = Path(temp.name)
            size = 0
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > SOUNDFONT_MAX_BYTES:
                    raise HTTPException(413, "SF2 音色包不能超过 128 MB；Supabase Bucket 也需允许该文件大小")
                temp.write(chunk)
        if size < 16:
            raise HTTPException(422, "SF2 文件太小或为空")
        with temp_path.open("rb") as source:
            header = source.read(12)
        if header[:4] != b"RIFF" or header[8:12] != b"sfbk":
            raise HTTPException(422, "文件不是标准 SoundFont2（RIFF/sfbk）；请确认下载的不是 ZIP 或网页错误页")
        digest_hash = hashlib.sha256()
        with temp_path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest_hash.update(chunk)
        digest = digest_hash.hexdigest()
        existing = db.scalar(select(InstrumentSoundfont).where(
            InstrumentSoundfont.teacher_id == teacher.id,
            InstrumentSoundfont.sha256 == digest,
        ))
        if existing:
            existing.display_name = label
            existing.original_filename = filename
            existing.instruments_json = json.dumps(assigned, ensure_ascii=False)
            existing.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            return present_soundfont(existing)

        object_key = f"teachers/{teacher.id}/soundfonts/{digest}.sf2"
        object_ref = upload_local_file(temp_path, object_key, content_type="application/octet-stream")
        row = InstrumentSoundfont(
            teacher_id=teacher.id,
            display_name=label,
            original_filename=filename,
            file_path=object_ref,
            file_size=size,
            sha256=digest,
            instruments_json=json.dumps(assigned, ensure_ascii=False),
        )
        db.add(row)
        try:
            db.commit()
            db.refresh(row)
        except Exception:
            db.rollback()
            try:
                delete_object(object_ref)
            except ObjectStorageError:
                pass
            raise
        return present_soundfont(row)
    except ObjectStorageError as exc:
        raise HTTPException(502, str(exc)) from exc
    finally:
        await file.close()
        if temp_path:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


@router.get("/soundfonts/{asset_id}/file")
def download_soundfont(asset_id: int, db: Session = Depends(get_db), teacher: Teacher = Depends(get_current_teacher)):
    row = own_soundfont(asset_id, db, teacher)
    try:
        data = download_object(row.file_path)
    except ObjectStorageError as exc:
        raise HTTPException(502, str(exc)) from exc
    safe_name = quote(row.original_filename.encode("utf-8"))
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}", "Cache-Control": "private, no-store"},
    )


@router.delete("/soundfonts/{asset_id}", status_code=204)
def delete_soundfont(asset_id: int, db: Session = Depends(get_db), teacher: Teacher = Depends(get_current_teacher)):
    row = own_soundfont(asset_id, db, teacher)
    try:
        if is_remote_ref(row.file_path):
            delete_object(row.file_path)
        db.delete(row)
        db.commit()
    except ObjectStorageError as exc:
        db.rollback()
        raise HTTPException(502, str(exc)) from exc
