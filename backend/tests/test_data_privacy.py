from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import UploadFile

from app.services import audio_service
from app.services.lesson_service import _external_model_payload


def _upload(filename: str, body: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(body))


def test_audio_upload_accepts_supported_file_and_uses_generated_storage_name(tmp_path, monkeypatch):
    monkeypatch.setattr(audio_service, "get_settings", lambda: SimpleNamespace(
        upload_dir=str(tmp_path), audio_max_upload_bytes=16,
    ))
    result = audio_service.save_upload(_upload("student-name.wav", b"RIFF"), "recordings/1")

    assert result.parent == tmp_path / "recordings" / "1"
    assert result.name != "student-name.wav"
    assert result.suffix == ".wav"
    assert result.read_bytes() == b"RIFF"


def test_audio_upload_rejects_unsupported_extension():
    with pytest.raises(audio_service.UnsupportedAudioUpload):
        audio_service.validate_upload(_upload("score.png", b"image"))


def test_audio_upload_rejects_empty_and_oversized_files(tmp_path, monkeypatch):
    monkeypatch.setattr(audio_service, "get_settings", lambda: SimpleNamespace(
        upload_dir=str(tmp_path), audio_max_upload_bytes=3,
    ))
    with pytest.raises(audio_service.AudioUploadError, match="为空"):
        audio_service.validate_upload(_upload("empty.wav", b""))
    with pytest.raises(audio_service.AudioUploadTooLarge):
        audio_service.save_upload(_upload("large.wav", b"1234"), "recordings/1")
    assert not list(tmp_path.rglob("*.wav"))


def test_external_lesson_model_payload_omits_class_name_and_teacher_notes():
    source = {
        "title": "音乐课",
        "generation_context": {"class_profile": {
            "name": "三年级一班", "teacher_notes": "某学生姓名与观察",
            "grade": 3, "common_problems": "某学生姓名：小明，不敢开口",
            "pitch_level": "音准基础一般",
        }},
    }
    payload = _external_model_payload(source)

    assert payload["generation_context"]["class_profile"] == {
        "grade": 3, "pitch_level": "音准基础一般",
    }
    assert source["generation_context"]["class_profile"]["teacher_notes"]
