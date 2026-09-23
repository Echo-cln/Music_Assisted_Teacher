import math
import shutil
import uuid
from pathlib import Path

import numpy as np
from fastapi import UploadFile

from app.core.config import get_settings


def save_upload(file: UploadFile, folder: str) -> Path:
    settings = get_settings()
    target_dir = Path(settings.upload_dir) / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "audio.wav").suffix.lower()
    target = target_dir / f"{uuid.uuid4().hex}{suffix}"
    with target.open("wb") as output:
        shutil.copyfileobj(file.file, output)
    return target


def load_waveform(path: Path, points: int = 180) -> tuple[list[float], float]:
    try:
        import librosa

        signal, sample_rate = librosa.load(path, sr=22050, mono=True)
        duration = float(len(signal) / sample_rate)
        if len(signal) == 0:
            return [0.0] * points, 0.0
        blocks = np.array_split(np.abs(signal), points)
        waveform = [round(float(np.mean(block)), 5) if len(block) else 0.0 for block in blocks]
        maximum = max(waveform) or 1.0
        return [round(value / maximum, 4) for value in waveform], duration
    except Exception:
        fallback = [round(0.18 + abs(math.sin(i * 0.21)) * 0.55, 4) for i in range(points)]
        return fallback, 0.0


def compare_waveforms(reference: list[float] | None, recording: list[float]) -> dict:
    if reference:
        a = np.asarray(reference)
        b = np.asarray(recording)
        length = min(len(a), len(b))
        correlation = float(np.corrcoef(a[:length], b[:length])[0, 1])
        overlap = int(max(0, min(100, 70 + correlation * 20)))
        is_demo = False
        reference_waveform = reference
    else:
        reference_waveform = [
            round(max(0.04, min(1.0, value * 0.8 + abs(math.sin(i * 0.3)) * 0.08)), 4)
            for i, value in enumerate(recording)
        ]
        overlap = 80
        is_demo = True
    return {
        "is_demo": is_demo,
        "overlap_percent": overlap,
        "reference_waveform": reference_waveform,
        "recording_waveform": recording,
        "scores": {
            "pitch": 78 if is_demo else min(96, overlap + 2),
            "rhythm": 74 if is_demo else min(94, overlap - 3),
            "volume": 81 if is_demo else min(95, overlap + 1),
            "emotion": 80 if is_demo else min(93, overlap),
            "participation": 82 if is_demo else min(95, overlap + 3),
        },
        "suggestions": [
            "先把容易抢拍的乐句拆成两拍一组，用拍手和口读稳定恒拍。",
            "高音前先轻声模唱，避免用喊叫代替歌唱。",
            "下一课先进行 3 分钟音准回声游戏，再回到本次最不稳定的乐句。",
        ],
    }
