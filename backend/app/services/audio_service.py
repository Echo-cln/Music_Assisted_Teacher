import math
import shutil
import uuid
from pathlib import Path

import numpy as np
from fastapi import UploadFile

from app.core.config import get_settings


def save_upload(file: UploadFile, folder: str) -> Path:
    target_dir = Path(get_settings().upload_dir) / folder
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
        return [0.0] * points, 0.0


def _score(value: float) -> int:
    return int(max(0, min(100, round(value))))


def _suggestions(scores: dict[str, int]) -> list[str]:
    suggestions = []
    if scores["pitch_stability"] < 70:
        suggestions.append("音高起伏较大：先用钢琴或标准音做两小节回声模唱，再进入歌词演唱。")
    if scores["rhythm_regularness"] < 70:
        suggestions.append("节拍稳定度偏弱：先拍恒拍、后读节奏，最后把节奏放回旋律。")
    if scores["dynamics"] < 65:
        suggestions.append("声音层次不够清晰：在乐句末尾保留气息，避免全程同一力度。")
    if scores["clarity"] < 65:
        suggestions.append("录音环境或咬字清晰度影响较大：靠近麦克风、降低环境噪声后再复测。")
    return suggestions or ["整体声学表现稳定：可挑选一个长音和一个节奏点，做更精细的分句打磨。"]


def analyze_singing(path: Path) -> dict:
    """课堂录音的可解释分析；不把合唱录音伪装成个人逐字评分。"""
    try:
        import librosa

        signal, sample_rate = librosa.load(path, sr=22050, mono=True)
        duration = len(signal) / sample_rate
        if duration < 1:
            raise ValueError("录音时长不足 1 秒")

        f0, voiced, _ = librosa.pyin(
            signal, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7"), sr=sample_rate, hop_length=512
        )
        valid_f0 = f0[~np.isnan(f0)]
        voiced_ratio = len(valid_f0) / max(1, len(f0))
        if len(valid_f0) > 2:
            cents = 1200 * np.log2(valid_f0 / np.median(valid_f0))
            pitch_spread = float(np.median(np.abs(cents - np.median(cents))))
            pitch_stability = _score(94 - pitch_spread / 5 - max(0, 0.35 - voiced_ratio) * 80)
        else:
            pitch_stability = 0

        onset = librosa.onset.onset_strength(y=signal, sr=sample_rate)
        tempo, beats = librosa.beat.beat_track(onset_envelope=onset, sr=sample_rate)
        beat_times = librosa.frames_to_time(beats, sr=sample_rate)
        if len(beat_times) >= 3:
            intervals = np.diff(beat_times)
            regularity = 100 - float(np.std(intervals) / max(np.mean(intervals), 0.01) * 100)
            rhythm = _score(regularity)
        else:
            rhythm = 55

        rms = librosa.feature.rms(y=signal)[0]
        dynamic_range = float(np.percentile(rms, 90) - np.percentile(rms, 10))
        dynamics = _score(45 + dynamic_range * 260)
        spectral = librosa.feature.spectral_centroid(y=signal, sr=sample_rate)[0]
        clarity = _score(45 + min(45, float(np.median(spectral)) / 55) - max(0, 0.16 - float(np.mean(rms))) * 100)
        scores = {"pitch_stability": pitch_stability, "rhythm_regularness": rhythm, "dynamics": dynamics, "clarity": clarity}

        section_count = min(6, max(3, int(duration // 7) + 1))
        sections = []
        frame_times = librosa.frames_to_time(np.arange(len(f0)), sr=sample_rate, hop_length=512)
        for index in range(section_count):
            start, end = index * duration / section_count, (index + 1) * duration / section_count
            mask = (frame_times >= start) & (frame_times < end)
            local_f0 = f0[mask]
            local_valid = local_f0[~np.isnan(local_f0)]
            local_voiced = len(local_valid) / max(1, len(local_f0))
            local_spread = 0.0
            if len(local_valid) > 2:
                local_cents = 1200 * np.log2(local_valid / np.median(local_valid))
                local_spread = float(np.median(np.abs(local_cents - np.median(local_cents))))
            local_score = _score(94 - local_spread / 5 - max(0, .35 - local_voiced) * 80) if len(local_valid) > 2 else 0
            if local_score >= 75:
                note = "音高轨迹较稳定，可保持当前速度继续分句演唱。"
            elif local_score >= 50:
                note = "音高有起伏，建议用标准音做两小节回声模唱后再接歌词。"
            else:
                note = "有效有声音高不足或起伏较大；建议降低伴奏、靠近麦克风并录制单独声部。"
            sections.append({
                "start_seconds": round(start, 1), "end_seconds": round(end, 1),
                "time": f"{int(start // 60):02d}:{int(start % 60):02d}—{int(end // 60):02d}:{int(end % 60):02d}",
                "focus": "音高稳定" if index in (0, section_count - 1) else "音高、节拍与气息",
                "pitch_stability": local_score, "voiced_ratio": round(local_voiced, 2), "note": note,
            })
        return {
            "analysis_available": True, "duration_seconds": round(duration, 1),
            "tempo_bpm": int(round(float(np.asarray(tempo).item()))), "scores": scores,
            "pitch_track": _compact_pitch_track(f0, frame_times), "segment_feedback": sections,
            "suggestions": _suggestions(scores),
        }
    except Exception as exc:
        return {"analysis_available": False, "duration_seconds": 0.0, "tempo_bpm": None, "scores": {}, "segment_feedback": [], "suggestions": [f"无法完成声学分析：{str(exc)[:120]}。请上传清晰的 WAV、MP3 或 M4A 录音。"]}


def _compact_pitch_track(f0: np.ndarray, times: np.ndarray, points: int = 90) -> list[dict]:
    """供前端展示的降采样音高轨迹（Hz），不把原始逐帧数据塞进数据库。"""
    if not len(f0):
        return []
    indices = np.linspace(0, len(f0) - 1, min(points, len(f0))).astype(int)
    return [{"t": round(float(times[i]), 2), "hz": round(float(f0[i]), 1) if not np.isnan(f0[i]) else None} for i in indices]


def compare_intonation(recording_path: Path, reference_path: Path | None) -> dict:
    """参考音频存在时，按归一化时间轴比较主音高轨迹，输出可解释的偏差而非波形相关性。"""
    if not reference_path:
        return {"available": False, "message": "未上传参考音频：系统只能评估课堂录音的音高稳定性，不能判定是否跑调。"}
    try:
        import librosa

        def track(path: Path) -> np.ndarray:
            signal, sr = librosa.load(path, sr=22050, mono=True)
            values, _, _ = librosa.pyin(signal, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7"), sr=sr, hop_length=512)
            return values

        recording, reference = track(recording_path), track(reference_path)
        target = min(120, len(recording), len(reference))
        if target < 12:
            raise ValueError("有效音高帧不足")
        grid = np.linspace(0, 1, target)
        def normalize(values: np.ndarray) -> np.ndarray:
            valid = ~np.isnan(values)
            if valid.sum() < 8:
                raise ValueError("有效音高帧不足")
            return np.interp(grid, np.linspace(0, 1, len(values))[valid], values[valid])
        r, ref = normalize(recording), normalize(reference)
        cents = 1200 * np.log2(r / ref)
        # 参考音频与课堂录音常有整体音高偏移；先扣除整体偏移，再判断局部音准。
        global_offset = float(np.median(cents))
        residual = cents - global_offset
        median_abs = float(np.median(np.abs(residual)))
        off_ratio = float(np.mean(np.abs(residual) > 50))
        score = _score(100 - median_abs * .7 - off_ratio * 35)
        status = "较准" if score >= 80 else "局部需校准" if score >= 60 else "跑调风险较高"
        segments = []
        for i, values in enumerate(np.array_split(residual, 4)):
            error = float(np.median(np.abs(values)))
            segments.append({"part": f"第 {i + 1} 段", "median_deviation_cents": round(error, 1), "off_pitch_ratio": round(float(np.mean(np.abs(values) > 50)) * 100), "status": "稳定" if error < 30 else "注意音准" if error < 55 else "需回声模唱"})
        return {"available": True, "intonation_score": score, "status": status, "median_deviation_cents": round(median_abs, 1), "off_pitch_ratio": round(off_ratio * 100), "global_offset_cents": round(global_offset, 1), "segments": segments, "message": "已按归一化时间轴比较主音高轨迹；结果适合单人或主声部清晰的录音，合唱与嘈杂环境只作教学参考。"}
    except Exception as exc:
        return {"available": False, "message": f"参考音高对齐未完成：{str(exc)[:100]}。仍保留课堂录音的稳定性分析。"}


def assess_note_accuracy(recording_path: Path, reference_path: Path | None) -> dict:
    """专业单人练唱模式：从参考与演唱音频提取音高轨迹并计算逐音偏差。

    这里刻意不依赖 Basic Pitch/TensorFlow。它们会让轻量 Web 服务带上数百 MB
    的模型运行时，而且 TensorFlow 2.14 没有 Python 3.12 wheel。课堂教学所需的
    单旋律逐音对齐用 pYIN 已足够，也与整体音高分析使用同一套可解释算法。
    """
    if not reference_path:
        return {"available": False, "message": "单人练唱逐音评测必须上传参考音频。"}
    try:
        import librosa

        reference_signal, reference_sr = librosa.load(reference_path, sr=22050, mono=True)
        signal, sr = librosa.load(recording_path, sr=22050, mono=True)
        reference_duration, duration = len(reference_signal) / reference_sr, len(signal) / sr
        reference_f0, _, _ = librosa.pyin(
            reference_signal,
            fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C7"),
            sr=reference_sr,
            hop_length=512,
        )
        f0, _, _ = librosa.pyin(signal, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7"), sr=sr, hop_length=512)
        reference_times = librosa.frames_to_time(np.arange(len(reference_f0)), sr=reference_sr, hop_length=512)
        times = librosa.frames_to_time(np.arange(len(f0)), sr=sr, hop_length=512)

        # 把参考音频的连续基频压缩为稳定音符段。相邻帧落在同一 MIDI 音高时
        # 合并，极短的过渡/噪声段不参与评分。
        reference_midi = np.full(len(reference_f0), np.nan)
        voiced = ~np.isnan(reference_f0)
        reference_midi[voiced] = np.rint(librosa.hz_to_midi(reference_f0[voiced]))
        note_events: list[tuple[float, float, int]] = []
        start_index: int | None = None
        current_midi: int | None = None
        for index, raw_midi in enumerate(reference_midi):
            midi = int(raw_midi) if not np.isnan(raw_midi) else None
            changed = midi != current_midi
            if changed and start_index is not None and current_midi is not None:
                start = float(reference_times[start_index])
                end = float(reference_times[index - 1] + 512 / reference_sr)
                if end - start >= 0.12:
                    note_events.append((start, end, current_midi))
            if changed:
                start_index = index if midi is not None else None
                current_midi = midi
        if start_index is not None and current_midi is not None:
            start = float(reference_times[start_index])
            end = float(reference_duration)
            if end - start >= 0.12:
                note_events.append((start, end, current_midi))

        events = []
        for start, end, midi in note_events:
            # 以相对时间对齐，避免两次录音时长不同导致逐音窗口偏移。
            target_start, target_end = start / max(reference_duration, .01) * duration, end / max(reference_duration, .01) * duration
            window = f0[(times >= target_start) & (times <= target_end)]
            valid = window[~np.isnan(window)]
            if len(valid) < 2:
                continue
            actual_hz, expected_hz = float(np.median(valid)), float(librosa.midi_to_hz(midi))
            cents = float(1200 * np.log2(actual_hz / expected_hz))
            label = "较准" if abs(cents) <= 35 else "偏高" if cents > 0 else "偏低"
            events.append({
                "index": len(events) + 1, "start_seconds": round(target_start, 2), "end_seconds": round(target_end, 2),
                "expected_midi": midi, "expected_note": librosa.midi_to_note(midi), "actual_hz": round(actual_hz, 1),
                "deviation_cents": round(cents, 1), "status": label,
            })
        if len(events) < 3:
            raise ValueError("可对齐的音符不足，请使用更清晰的单人演唱和参考旋律")
        deviations = np.asarray([item["deviation_cents"] for item in events])
        accurate = float(np.mean(np.abs(deviations) <= 50))
        score = _score(100 - np.median(np.abs(deviations)) * .65 - (1 - accurate) * 20)
        return {
            "available": True, "method": "pyin_reference_notes_plus_pyin_cents", "score": score,
            "matched_notes": len(events), "accurate_note_ratio": round(accurate * 100),
            "median_deviation_cents": round(float(np.median(np.abs(deviations))), 1),
            "events": events[:48],
            "message": "逐音评测以参考旋律转写出的音符为目标，并按相对时间定位课堂录音的实际音高；适合单人清唱或主声部清晰的录音。",
        }
    except Exception as exc:
        return {"available": False, "message": f"逐音评测未完成：{str(exc)[:140]}。可改用课堂整体分析，或使用清晰的单人练唱录音。"}


def compare_waveforms(reference: list[float] | None, recording: list[float]) -> dict:
    if not reference:
        return {"has_reference_comparison": False, "reference_waveform": None, "recording_waveform": recording, "reference_similarity": None}
    a, b = np.asarray(reference), np.asarray(recording)
    length = min(len(a), len(b))
    correlation = float(np.corrcoef(a[:length], b[:length])[0, 1]) if length > 3 else 0.0
    return {"has_reference_comparison": True, "reference_waveform": reference, "recording_waveform": recording, "reference_similarity": _score(50 + correlation * 45)}
