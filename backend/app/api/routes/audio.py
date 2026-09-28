from pathlib import Path

import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_teacher
from app.db.session import SessionLocal, get_db
from app.models.entities import AudioAnalysis, AudioAnalysisJob, AudioAsset, ClassroomRecord, LessonPlan, Song, Teacher
from app.repositories.song_repository import SongRepository
from app.services.audio_service import analyze_singing, assess_note_accuracy, compare_intonation, compare_waveforms, load_waveform, save_upload

router = APIRouter(prefix="/audio", tags=["音频"])
logger = logging.getLogger(__name__)
# 音频解码和音高估计是 CPU 密集型任务。限制为两个工作线程，避免多次上传拖慢全部 API。
audio_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="audio-analysis")


def _check_request(db: Session, teacher: Teacher, song_id: int, lesson_plan_id: int | None, classroom_record_id: int | None, analysis_mode: str, has_original: bool):
    song = SongRepository(db, teacher.id).get(song_id)
    if not song:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    if analysis_mode not in {"classroom", "solo"}:
        raise HTTPException(status_code=422, detail="不支持的分析方式")
    if analysis_mode == "solo" and not has_original:
        raise HTTPException(status_code=422, detail="单人练唱逐音评测需要上传参考音频")
    if lesson_plan_id:
        plan = db.scalar(select(LessonPlan).where(LessonPlan.id == lesson_plan_id, LessonPlan.teacher_id == teacher.id))
        if not plan:
            raise HTTPException(status_code=404, detail="对应教案不存在")
        record = db.scalar(select(ClassroomRecord).where(ClassroomRecord.lesson_plan_id == plan.id, ClassroomRecord.teacher_id == teacher.id))
        classroom_record_id = record.id if record else None
    if classroom_record_id:
        record = db.scalar(select(ClassroomRecord).where(ClassroomRecord.id == classroom_record_id, ClassroomRecord.teacher_id == teacher.id))
        if not record:
            raise HTTPException(status_code=404, detail="课堂记录不存在")
    return song, classroom_record_id


def _build_analysis(db: Session, teacher_id: int, song: Song, lesson_plan_id: int | None, classroom_record_id: int | None,
                    analysis_mode: str, recording_path: Path, recording_name: str, recording_type: str,
                    reference_path: Path | None, reference_name: str | None, reference_type: str | None,
                    report=None):
    if report:
        report(20, "正在读取录音并校验格式")
    recording_waveform, recording_duration = load_waveform(recording_path)
    if report:
        report(42, "正在提取音高轨迹、起音与节拍")
    singing_analysis = analyze_singing(recording_path)
    if report:
        report(68, "正在计算分段声学指标")
    if reference_path and song.owner_teacher_id == teacher_id:
        song.original_audio_path = str(reference_path)
    reference_waveform = load_waveform(reference_path)[0] if reference_path else None
    waveform_result = compare_waveforms(reference_waveform, recording_waveform)
    intonation = compare_intonation(recording_path, reference_path)
    if report:
        report(82, "正在生成逐音结果与教学建议" if analysis_mode == "solo" else "正在生成课堂建议")
    note_assessment = assess_note_accuracy(recording_path, reference_path) if analysis_mode == "solo" else None
    recording_asset = AudioAsset(teacher_id=teacher_id, song_id=song.id, classroom_record_id=classroom_record_id,
        asset_type="recording", file_path=str(recording_path), original_filename=recording_name,
        mime_type=recording_type, duration_seconds=recording_duration, is_reference=False)
    db.add(recording_asset)
    db.flush()
    reference_asset = None
    if reference_path:
        reference_asset = AudioAsset(teacher_id=teacher_id, song_id=song.id, classroom_record_id=classroom_record_id,
            asset_type="original", file_path=str(reference_path), original_filename=reference_name or reference_path.name,
            mime_type=reference_type or "audio/mpeg", is_reference=True)
        db.add(reference_asset)
        db.flush()
    result = {
        "song_id": song.id, "song_name": song.name, "analysis_mode": analysis_mode,
        "analysis_mode_label": "单人练唱逐音评测" if analysis_mode == "solo" else "课堂整体分析",
        "has_original": reference_path is not None,
        "analysis_scope": "课堂录音可评估整体音高稳定、节拍和声音表现；只有参考音频与主声部清晰时才给出音准对齐提示。",
        "analysis_method": [
            "以 librosa.pyin 提取有声帧基频，计算音高稳定度与分段音高轨迹。",
            "检测起音、拍点与相邻拍间隔，估计节拍稳定性和推测速度。",
            "以短时能量与频谱特征估计力度层次、清晰度和录音可用性。",
            "若提供参考音频，则将两条主音高轨迹归一化到同一时间轴，扣除整体音高偏移后计算局部偏差与疑似跑调比例。",
        ],
        **singing_analysis, **waveform_result, "intonation_comparison": intonation,
        "note_assessment": note_assessment,
    }
    analysis = AudioAnalysis(teacher_id=teacher_id, song_id=song.id, lesson_plan_id=lesson_plan_id,
        classroom_record_id=classroom_record_id, recording_asset_id=recording_asset.id,
        reference_asset_id=reference_asset.id if reference_asset else None, result_json=json.dumps(result, ensure_ascii=False))
    db.add(analysis)
    db.flush()
    return analysis, recording_asset, reference_asset


def _update_job(job_id: str, progress: int, stage: str):
    db = SessionLocal()
    try:
        job = db.get(AudioAnalysisJob, job_id)
        if job:
            job.progress, job.stage, job.status = progress, stage, "running"
            db.commit()
    finally:
        db.close()


def _run_job(job_id: str):
    db = SessionLocal()
    try:
        job = db.get(AudioAnalysisJob, job_id)
        if not job:
            return
        logger.info("audio_job_started job_id=%s teacher_id=%s", job.id, job.teacher_id)
        payload = json.loads(job.request_json)
        song = db.get(Song, payload["song_id"])
        if not song:
            raise ValueError("歌曲不存在或已删除")
        def report(progress, stage):
            db.refresh(job)
            if job.status == "cancelled":
                raise RuntimeError("任务已取消")
            job.progress, job.stage, job.status = progress, stage, "running"
            db.commit()
        report(8, "后台任务已开始，正在读取音频")
        analysis, recording, reference = _build_analysis(db, job.teacher_id, song, payload.get("lesson_plan_id"),
            payload.get("classroom_record_id"), payload["analysis_mode"], Path(payload["recording_path"]),
            payload["recording_name"], payload["recording_type"], Path(payload["reference_path"]) if payload.get("reference_path") else None,
            payload.get("reference_name"), payload.get("reference_type"), report)
        db.refresh(job)
        if job.status == "cancelled":
            db.rollback()
            return
        job.analysis_id, job.status, job.progress, job.stage = analysis.id, "completed", 100, "分析完成，结果已保存"
        db.commit()
        logger.info("audio_job_completed job_id=%s analysis_id=%s", job.id, analysis.id)
    except Exception as exc:
        logger.exception("audio_job_failed job_id=%s error=%s", job_id, exc)
        db.rollback()
        job = db.get(AudioAnalysisJob, job_id)
        if job and job.status != "cancelled":
            job.status, job.stage, job.error_message = "failed", "音频分析失败", str(exc)[:500]
            db.commit()
    finally:
        db.close()


def _serialize_job(job: AudioAnalysisJob, db: Session) -> dict:
    data = {"id": job.id, "status": job.status, "stage": job.stage, "progress": job.progress,
            "analysis_id": job.analysis_id, "error_message": job.error_message or "", "created_at": job.created_at.isoformat(timespec="seconds")}
    if job.analysis_id:
        item = db.get(AudioAnalysis, job.analysis_id)
        if item:
            song, recording = db.get(Song, item.song_id), db.get(AudioAsset, item.recording_asset_id)
            reference = db.get(AudioAsset, item.reference_asset_id) if item.reference_asset_id else None
            if song and recording:
                data["analysis"] = _serialize_analysis(item, song, recording, reference)
    return data


@router.post("/analyze")
def analyze_audio(
    song_id: int = Form(...),
    lesson_plan_id: int | None = Form(default=None),
    classroom_record_id: int | None = Form(default=None),
    analysis_mode: str = Form(default="classroom"),
    recording: UploadFile = File(...),
    original: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(get_current_teacher),
):
    song, classroom_record_id = _check_request(db, teacher, song_id, lesson_plan_id, classroom_record_id, analysis_mode, bool(original))
    recording_path = save_upload(recording, f"recordings/{teacher.id}")
    reference_path: Path | None = None
    if original:
        reference_path = save_upload(original, f"originals/{teacher.id}")
    elif song.original_audio_path and Path(song.original_audio_path).exists():
        reference_path = Path(song.original_audio_path)
    analysis, recording_asset, reference_asset = _build_analysis(db, teacher.id, song, lesson_plan_id, classroom_record_id,
        analysis_mode, recording_path, recording.filename or recording_path.name, recording.content_type or "application/octet-stream",
        reference_path, (original.filename if original else reference_path.name) if reference_path else None,
        (original.content_type if original else "audio/mpeg") if reference_path else None)
    db.commit()
    return _serialize_analysis(analysis, song, recording_asset, reference_asset)


@router.post("/jobs", status_code=202)
def create_audio_job(song_id: int = Form(...), lesson_plan_id: int | None = Form(default=None), classroom_record_id: int | None = Form(default=None),
                     analysis_mode: str = Form(default="classroom"), recording: UploadFile = File(...), original: UploadFile | None = File(default=None),
                     db: Session = Depends(get_db), teacher: Teacher = Depends(get_current_teacher)):
    song, classroom_record_id = _check_request(db, teacher, song_id, lesson_plan_id, classroom_record_id, analysis_mode, bool(original))
    recording_path = save_upload(recording, f"recordings/{teacher.id}")
    reference_path = save_upload(original, f"originals/{teacher.id}") if original else (Path(song.original_audio_path) if song.original_audio_path and Path(song.original_audio_path).exists() else None)
    job = AudioAnalysisJob(id=str(uuid.uuid4()), teacher_id=teacher.id, status="pending", stage="音频已保存，等待后台分析", progress=3,
        request_json=json.dumps({"song_id": song.id, "lesson_plan_id": lesson_plan_id, "classroom_record_id": classroom_record_id,
          "analysis_mode": analysis_mode, "recording_path": str(recording_path), "recording_name": recording.filename or recording_path.name,
          "recording_type": recording.content_type or "application/octet-stream", "reference_path": str(reference_path) if reference_path else None,
          "reference_name": (original.filename if original else reference_path.name) if reference_path else None,
          "reference_type": (original.content_type if original else "audio/mpeg") if reference_path else None}, ensure_ascii=False))
    db.add(job); db.commit()
    audio_executor.submit(_run_job, job.id)
    return _serialize_job(job, db)


@router.delete("/jobs/{job_id}", status_code=204)
def cancel_audio_job(job_id: str, db: Session = Depends(get_db), teacher: Teacher = Depends(get_current_teacher)):
    job = db.scalar(select(AudioAnalysisJob).where(AudioAnalysisJob.id == job_id, AudioAnalysisJob.teacher_id == teacher.id))
    if not job:
        raise HTTPException(status_code=404, detail="音频分析任务不存在")
    if job.status not in {"pending", "running"}:
        raise HTTPException(status_code=409, detail="该音频任务已经结束，无法取消")
    job.status, job.stage, job.error_message = "cancelled", "已取消，不会保存分析结果", ""
    db.commit()
    return None


@router.get("/jobs/{job_id}")
def get_audio_job(job_id: str, db: Session = Depends(get_db), teacher: Teacher = Depends(get_current_teacher)):
    job = db.scalar(select(AudioAnalysisJob).where(AudioAnalysisJob.id == job_id, AudioAnalysisJob.teacher_id == teacher.id))
    if not job:
        raise HTTPException(status_code=404, detail="音频分析任务不存在")
    return _serialize_job(job, db)


def _serialize_analysis(item: AudioAnalysis, song: Song, recording: AudioAsset, reference: AudioAsset | None) -> dict:
    result = json.loads(item.result_json or "{}")
    return {
        **result, "id": item.id, "created_at": item.created_at.isoformat(timespec="seconds"),
        "lesson_plan_id": item.lesson_plan_id,
        "recording_url": f"/api/audio/assets/{recording.id}/stream",
        "reference_url": f"/api/audio/assets/{reference.id}/stream" if reference else None,
        "recording_filename": recording.original_filename,
        "reference_filename": reference.original_filename if reference else None,
        "song_name": song.name,
    }


@router.get("/analyses")
def list_analyses(db: Session = Depends(get_db), teacher: Teacher = Depends(get_current_teacher)):
    rows = db.scalars(select(AudioAnalysis).where(AudioAnalysis.teacher_id == teacher.id).order_by(AudioAnalysis.created_at.desc())).all()
    output = []
    for item in rows:
        song = db.get(Song, item.song_id)
        recording = db.get(AudioAsset, item.recording_asset_id)
        reference = db.get(AudioAsset, item.reference_asset_id) if item.reference_asset_id else None
        if song and recording:
            output.append(_serialize_analysis(item, song, recording, reference))
    return output


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: int, db: Session = Depends(get_db), teacher: Teacher = Depends(get_current_teacher)):
    item = db.scalar(select(AudioAnalysis).where(AudioAnalysis.id == analysis_id, AudioAnalysis.teacher_id == teacher.id))
    if not item:
        raise HTTPException(status_code=404, detail="音频分析记录不存在")
    song, recording = db.get(Song, item.song_id), db.get(AudioAsset, item.recording_asset_id)
    reference = db.get(AudioAsset, item.reference_asset_id) if item.reference_asset_id else None
    if not song or not recording:
        raise HTTPException(status_code=404, detail="音频文件或歌曲已不存在")
    return _serialize_analysis(item, song, recording, reference)


@router.get("/assets/{asset_id}/stream")
def stream_asset(asset_id: int, db: Session = Depends(get_db), teacher: Teacher = Depends(get_current_teacher)):
    asset = db.scalar(select(AudioAsset).where(AudioAsset.id == asset_id, AudioAsset.teacher_id == teacher.id))
    if not asset or not Path(asset.file_path).exists():
        raise HTTPException(status_code=404, detail="音频文件不存在")
    return FileResponse(asset.file_path, media_type=asset.mime_type, filename=asset.original_filename)
