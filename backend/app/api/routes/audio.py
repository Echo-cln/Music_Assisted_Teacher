from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_teacher
from app.db.session import get_db
from app.models.entities import AudioAsset, ClassroomRecord, Teacher
from app.repositories.song_repository import SongRepository
from app.services.audio_service import compare_waveforms, load_waveform, save_upload

router = APIRouter(prefix="/audio", tags=["音频"])


@router.post("/analyze")
def analyze_audio(
    song_id: int = Form(...),
    classroom_record_id: int | None = Form(default=None),
    recording: UploadFile = File(...),
    original: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    song = SongRepository(db, teacher.id).get(song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    if classroom_record_id:
        record = db.scalar(
            select(ClassroomRecord).where(
                ClassroomRecord.id == classroom_record_id,
                ClassroomRecord.teacher_id == teacher.id,
            )
        )
        if not record:
            raise HTTPException(status_code=404, detail="课堂记录不存在")
    recording_path = save_upload(recording, f"recordings/{teacher.id}")
    recording_waveform, recording_duration = load_waveform(recording_path)
    reference_path: Path | None = None
    if original:
        reference_path = save_upload(original, f"originals/{teacher.id}")
        if song.owner_teacher_id == teacher.id:
            song.original_audio_path = str(reference_path)
    elif song.original_audio_path and Path(song.original_audio_path).exists():
        reference_path = Path(song.original_audio_path)
    reference_waveform = load_waveform(reference_path)[0] if reference_path else None
    result = compare_waveforms(reference_waveform, recording_waveform)
    db.add(
        AudioAsset(
            teacher_id=teacher.id,
            song_id=song.id,
            classroom_record_id=classroom_record_id,
            asset_type="recording",
            file_path=str(recording_path),
            original_filename=recording.filename or recording_path.name,
            mime_type=recording.content_type or "application/octet-stream",
            duration_seconds=recording_duration,
            is_reference=False,
        )
    )
    if original and reference_path:
        db.add(
            AudioAsset(
                teacher_id=teacher.id,
                song_id=song.id,
                classroom_record_id=classroom_record_id,
                asset_type="original",
                file_path=str(reference_path),
                original_filename=original.filename or reference_path.name,
                mime_type=original.content_type or "application/octet-stream",
                is_reference=True,
            )
        )
    db.commit()
    return {"song_id": song.id, "song_name": song.name, "has_original": reference_path is not None, **result}
