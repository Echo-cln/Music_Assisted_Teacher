"""音频分析服务。

不能可靠判断，就明确说明不能判断，绝不把混音伴奏的错误转写伪装成学生
“跑调 0 分”。逐音评测只接受可用的单人参考人声；混音原唱优先尝试独立环境中的
Audio Separator / BS-RoFormer，未安装时使用现有 Demucs 路径。
"""

from __future__ import annotations

import math
import logging
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from fastapi import UploadFile

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class PitchTrack:
    values: np.ndarray
    times: np.ndarray
    confidence: np.ndarray
    voiced_ratio: float
    backend: str


def save_upload(file: UploadFile, folder: str) -> Path:
    target_dir = Path(get_settings().upload_dir) / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "audio.wav").suffix.lower()
    target = target_dir / f"{uuid.uuid4().hex}{suffix}"
    with target.open("wb") as output:
        shutil.copyfileobj(file.file, output)
    return target


def _load_mono_audio(path: Path, sample_rate: int = 22050) -> tuple[np.ndarray, int]:
    """以 FFmpeg 统一解码，避免 PySoundFile/audioread 的格式回退。"""
    import imageio_ffmpeg

    command = [
        imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-v", "error", "-i", str(path),
        "-f", "f32le", "-ac", "1", "-ar", str(sample_rate), "-",
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()[:220]
        raise ValueError(f"无法解码音频：{detail or 'FFmpeg 未返回可读音频流'}")
    signal = np.frombuffer(result.stdout, dtype=np.float32)
    if not len(signal):
        raise ValueError("音频不含可读取的声音数据")
    return signal, sample_rate


def load_waveform(path: Path, points: int = 180) -> tuple[list[float], float]:
    try:
        signal, sample_rate = _load_mono_audio(path)
        duration = float(len(signal) / sample_rate)
        blocks = np.array_split(np.abs(signal), points)
        waveform = [round(float(np.mean(block)), 5) if len(block) else 0.0 for block in blocks]
        maximum = max(waveform) or 1.0
        return [round(value / maximum, 4) for value in waveform], duration
    except Exception:
        return [0.0] * points, 0.0


def _score(value: float | None) -> int:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0
    return int(max(0, min(100, round(numeric)))) if math.isfinite(numeric) else 0


def _pitch_track(path: Path) -> PitchTrack:
    """提取单声部 F0 与置信度。

    稳定基线为 pYIN；后续可换接 torchcrepe，但无论哪一后端都会经过同一
    置信度门控和 DTW 对齐。
    """
    import librosa

    signal, sr = _load_mono_audio(path)
    values, voiced, probability = librosa.pyin(
        signal, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7"),
        sr=sr, hop_length=512,
    )
    values = np.asarray(values, dtype=float)
    confidence = np.asarray(probability if probability is not None else voiced, dtype=float)
    confidence = np.nan_to_num(confidence, nan=0.0)
    times = librosa.frames_to_time(np.arange(len(values)), sr=sr, hop_length=512)
    valid = np.isfinite(values) & (confidence >= 0.25)
    values[~valid] = np.nan
    return PitchTrack(values, np.asarray(times, dtype=float), confidence, float(valid.mean()) if len(valid) else 0.0, "librosa_pyin")


def _midi(values: np.ndarray) -> np.ndarray:
    output = np.full(len(values), np.nan, dtype=float)
    valid = np.isfinite(values) & (values > 0)
    output[valid] = 69 + 12 * np.log2(values[valid] / 440.0)
    return output


def _voiced_sequence(track: PitchTrack, minimum_confidence: float = 0.25) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """只保留可信有声帧，返回 MIDI、原始帧索引和置信度。

    不对静音/失声区间插值。插值会把停顿连接成虚构音高轨迹，进而让 DTW
    把演唱错位、长停顿误认为连续旋律。
    """
    values = np.asarray(track.values, dtype=float)
    confidence = np.asarray(track.confidence, dtype=float)
    length = min(len(values), len(confidence))
    values, confidence = values[:length], confidence[:length]
    valid = np.isfinite(values) & (values > 0) & np.isfinite(confidence) & (confidence >= minimum_confidence)
    frame_indices = np.flatnonzero(valid)
    if len(frame_indices) < 2:
        raise ValueError("可用的人声音高帧不足")
    return _midi(values[valid]), frame_indices, confidence[valid]


def _pitch_quality(track: PitchTrack) -> dict:
    confidence = np.asarray(track.confidence, dtype=float)
    values = np.asarray(track.values, dtype=float)
    length = min(len(values), len(confidence))
    if not length:
        return {"voiced_ratio": 0.0, "usable_frames": 0, "median_confidence": 0.0}
    confidence, values = confidence[:length], values[:length]
    valid = np.isfinite(values) & (values > 0) & np.isfinite(confidence) & (confidence >= 0.25)
    selected = confidence[valid]
    return {
        "voiced_ratio": round(float(valid.mean()), 3),
        "usable_frames": int(valid.sum()),
        "median_confidence": round(float(np.median(selected)), 3) if len(selected) else 0.0,
    }


def _audio_separator_executable() -> list[str] | None:
    """Return the optional audio-separator CLI without importing its heavy ML stack."""
    settings = get_settings()
    configured = str(getattr(settings, "audio_separator_command", "") or "").strip()
    if configured:
        candidate = Path(configured.strip('"'))
        if candidate.is_file():
            return [str(candidate)]
        found = shutil.which(configured)
        return [found] if found else None
    root = Path(__file__).resolve().parents[3]
    candidate = root / ".audio-separator-venv" / ("Scripts/audio-separator.exe" if sys.platform == "win32" else "bin/audio-separator")
    return [str(candidate)] if candidate.is_file() else None


def _decode_process_output(value: bytes | str | None) -> str:
    """Decode captured CLI output safely on Windows and Unix regardless of console code page."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def _separator_failure_message(detail: str, wav_count: int) -> str:
    text = detail.casefold()
    if any(token in text for token in ("out of memory", "outofmemory", "cuda out of memory", "not enough memory")):
        return "BS-RoFormer 分离占用内存过高而失败。请先用较短的参考片段重试，或使用清晰单人参考人声。"
    if any(token in text for token in ("connection", "http error", "urlopen", "download", "timed out", "ssl")):
        return "BS-RoFormer 模型下载或网络访问失败。请确认本机可访问模型下载站点后重试；权重缓存成功后后续无需重复下载。"
    if wav_count == 0:
        return "分离程序没有生成 WAV 音轨。模型或依赖错误已记录在后端 audio_separator_failed 日志。"
    return "分离程序生成了 WAV 文件，但没有可识别的人声音轨。请检查模型是否支持 Vocals 输出；具体错误已记录在后端 audio_separator_failed 日志。"


def _separate_with_audio_separator(path: Path, output_root: Path) -> tuple[Path | None, str]:
    command = _audio_separator_executable()
    if not command:
        return None, "audio-separator 未安装"
    output_root.mkdir(parents=True, exist_ok=True)
    model = str(getattr(get_settings(), "audio_separator_model", "") or "model_bs_roformer_ep_317_sdr_12.9755.ckpt").strip()
    args = [
        *command, str(path), "--model_filename", model, "--single_stem", "Vocals",
        "--output_format", "WAV", "--output_dir", str(output_root),
    ]
    logger.info("audio_separator_started model=%s input=%s", model, path.name)
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900, check=False)
    raw_detail = _decode_process_output(result.stderr) + ("\n" if result.stderr and result.stdout else "") + _decode_process_output(result.stdout)
    detail = " ".join(raw_detail.split())
    wav_files = sorted(
        (item for item in output_root.rglob("*") if item.is_file() and item.suffix.lower() == ".wav" and item.stat().st_size > 4096),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    vocal_candidates = [item for item in wav_files if any(token in item.name.casefold() for token in ("vocal", "voice"))]
    # --single_stem Vocals requests only the vocal output. Some supported models
    # use non-English/custom filenames, so accept the sole WAV in this unique job dir.
    candidates = vocal_candidates or (wav_files if len(wav_files) == 1 else [])
    if result.returncode == 0 and candidates:
        logger.info("audio_separator_completed model=%s output=%s", model, candidates[0].name)
        return candidates[0], detail[-1200:]
    logger.warning("audio_separator_failed returncode=%s model=%s wav_count=%s detail=%s", result.returncode, model, len(wav_files), detail[-1600:])
    return None, detail[-1200:] or f"audio-separator exited with code {result.returncode}"


def _prepare_reference(path: Path | None, reference_kind: str) -> dict:
    """将参考音频变为可用于主旋律比较的人声；混音不允许直接拿来打分。"""
    if not path:
        return {"available": False, "code": "reference_missing", "message": "未提供参考旋律：只能做课堂整体声学分析，不能判定是否唱准。"}
    if reference_kind == "vocal":
        return {"available": True, "path": path, "source": "clean_vocal", "message": "使用上传的清晰单人参考人声进行对齐。"}
    if reference_kind not in {"mixed", "auto"}:
        return {"available": False, "code": "reference_unsupported", "message": "参考类型无效。请选“清晰人声”或“原唱/伴奏混音”。"}
    separator_command = _audio_separator_executable()
    if separator_command:
        try:
            output_root = Path(tempfile.gettempdir()) / "xiangyin-audio-separator" / uuid.uuid4().hex
            stem, detail = _separate_with_audio_separator(path, output_root)
            if stem:
                model = str(getattr(get_settings(), "audio_separator_model", "BS-RoFormer"))
                return {"available": True, "path": stem, "source": "audio_separator_vocals", "engine": "audio_separator", "message": f"已使用 Audio Separator 分离参考人声（{model}），再用于主旋律对齐。"}
            wav_count = sum(1 for item in output_root.rglob("*") if item.is_file() and item.suffix.lower() == ".wav")
            logger.warning("reference_vocal_separation_unavailable engine=audio-separator detail=%s", detail[-1200:])
            return {"available": False, "source": "audio_separator_failed", "engine": "audio_separator", "code": "vocal_separation_failed", "message": _separator_failure_message(detail, wav_count)}
        except subprocess.TimeoutExpired:
            return {"available": False, "code": "vocal_separation_timeout", "message": "Audio Separator 人声分离超过 15 分钟仍未完成，本次不输出逐音分数。请使用较短的参考片段或清晰单人参考人声。"}
        except Exception as exc:
            logger.exception("audio_separator_reference_failed error=%s", exc)
            return {"available": False, "source": "audio_separator_failed", "engine": "audio_separator", "code": "vocal_separation_failed", "message": f"BS-RoFormer 分离命令执行失败：{str(exc)[:180]}。本次不输出逐音分数；可先上传清晰单人参考人声。"}
    try:
        output_root = Path(tempfile.gettempdir()) / "xiangyin-demucs" / uuid.uuid4().hex
        command = [sys.executable, "-m", "demucs.separate", "--two-stems=vocals", "-n", "htdemucs", "-o", str(output_root), str(path)]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=600, check=False)
        stem = output_root / "htdemucs" / path.stem / "vocals.wav"
        if result.returncode == 0 and stem.exists() and stem.stat().st_size > 4096:
            return {"available": True, "path": stem, "source": "demucs_vocals", "message": "已从混音参考中分离人声，再用于主旋律对齐。"}
        raw_detail = (result.stderr or "") + ("\n" if result.stderr and result.stdout else "") + (result.stdout or "")
        detail = " ".join(raw_detail.split())
        if "No module named demucs" in detail:
            return {"available": False, "source": "demucs_failed", "engine": "demucs", "code": "vocal_separator_not_installed", "message": "本机未检测到 Audio Separator，也未安装 Demucs，因此无法分离混音参考。请在项目根目录运行 setup_audio_separator.bat（首次下载模型需要联网），重启后端再分析；也可上传清晰单人参考人声。"}
        # tqdm 的模型下载进度可能有数千字符，并非教师可读的诊断；保留在
        # 后端日志用于排查，API 只返回稳定、可执行的短错误，不污染结果卡。
        logger.warning("demucs_separation_failed returncode=%s detail=%s", result.returncode, detail[-1200:])
        download_failure = any(token in detail.lower() for token in ("download", "http", "connection", "https", "100%|", "0%|", "urlopen"))
        message = (
            "混音人声分离失败：Demucs 模型下载或加载未完成。首次运行需要联网下载分离模型；请确认网络可访问，或改上传清晰单人参考人声后重试。"
            if download_failure else
            "混音人声分离未生成有效的人声轨。本次不输出逐音分数；请改上传清晰单人参考人声，或查看后端日志中的 Demucs 错误后重试。"
        )
        return {"available": False, "source": "demucs_failed", "engine": "demucs", "code": "vocal_separation_failed", "message": message}
    except (ModuleNotFoundError, FileNotFoundError):
        return {"available": False, "source": "demucs_failed", "engine": "demucs", "code": "vocal_separator_not_installed", "message": "本机未检测到 Audio Separator，也未安装 Demucs。请在项目根目录运行 setup_audio_separator.bat，重启后端并重新分析；也可上传清晰单人参考人声。"}
    except subprocess.TimeoutExpired:
        return {"available": False, "code": "vocal_separation_timeout", "message": "人声分离超过 10 分钟仍未完成，本次未生成逐音分数。请使用更短的片段或清晰人声参考。"}


def _align_tracks(recording_path: Path, reference: dict) -> dict:
    """只用可信有声帧进行 DTW；较短旋律可在较长录音中做子序列匹配。"""
    if not reference.get("available"):
        return {"available": False, "reason": reference.get("code"), "message": reference.get("message")}
    try:
        import librosa

        recording = _pitch_track(recording_path)
        expected = _pitch_track(Path(reference["path"]))
        recording_quality, reference_quality = _pitch_quality(recording), _pitch_quality(expected)
        diagnostics = {
            "recording_voiced_ratio": recording_quality["voiced_ratio"],
            "reference_voiced_ratio": reference_quality["voiced_ratio"],
            "recording_usable_frames": recording_quality["usable_frames"],
            "reference_usable_frames": reference_quality["usable_frames"],
            "recording_median_confidence": recording_quality["median_confidence"],
            "reference_median_confidence": reference_quality["median_confidence"],
            "recording_pitch_backend": recording.backend,
            "reference_pitch_backend": expected.backend,
        }
        if recording_quality["voiced_ratio"] < 0.16:
            return {"available": False, "reason": "recording_low_quality", "diagnostics": diagnostics, "message": f"练唱录音可用人声音高仅 {recording_quality['voiced_ratio']:.0%}，请降低伴奏并靠近麦克风重录。"}
        if reference_quality["voiced_ratio"] < 0.18:
            return {"available": False, "reason": "reference_low_quality", "diagnostics": diagnostics, "message": f"参考人声可用音高仅 {reference_quality['voiced_ratio']:.0%}，不能作为主旋律目标。请确认上传的是清晰人声；混音文件应选择“原唱/伴奏混音”。"}

        actual_midi, recording_frames, recording_confidence = _voiced_sequence(recording)
        expected_midi, reference_frames, reference_confidence = _voiced_sequence(expected)
        # 去除整体音高位置后对齐旋律轮廓，评分阶段仍使用原始音高。
        a_feature = actual_midi - np.median(actual_midi)
        e_feature = expected_midi - np.median(expected_midi)
        length_ratio = min(len(actual_midi), len(expected_midi)) / max(len(actual_midi), len(expected_midi))
        if length_ratio >= 0.85:
            _, warp = librosa.sequence.dtw(
                X=a_feature[np.newaxis, :], Y=e_feature[np.newaxis, :],
                metric="euclidean", global_constraints=True, band_rad=0.2,
            )
            pairs = np.asarray(warp[::-1], dtype=int)
            alignment_mode = "full"
        elif len(actual_midi) < len(expected_midi):
            # 学生只唱一段时，在完整参考曲中寻找这一段，不把前奏/尾奏硬拉进对齐。
            _, warp = librosa.sequence.dtw(
                X=a_feature[np.newaxis, :], Y=e_feature[np.newaxis, :],
                metric="euclidean", subseq=True,
            )
            pairs = np.asarray(warp[::-1], dtype=int)
            alignment_mode = "recording_subsequence"
        else:
            # 反向查询，保持短的参考乐句完整匹配到学生录音中的位置。
            _, warp = librosa.sequence.dtw(
                X=e_feature[np.newaxis, :], Y=a_feature[np.newaxis, :],
                metric="euclidean", subseq=True,
            )
            reverse_pairs = np.asarray(warp[::-1], dtype=int)
            pairs = reverse_pairs[:, ::-1]
            alignment_mode = "reference_subsequence"

        if len(pairs) < 32:
            return {"available": False, "reason": "alignment_too_short", "diagnostics": diagnostics, "message": "两段音频可对齐的可信人声不足约 0.7 秒，本次不给逐音分数。请上传更长、清晰的同一乐句。"}
        # DTW 输出索引属于压缩后的有声序列；映射回原始帧，保留正确时间戳和置信度。
        frame_pairs = np.column_stack((recording_frames[pairs[:, 0]], reference_frames[pairs[:, 1]])).astype(int)
        actual_hz = recording.values[frame_pairs[:, 0]]
        expected_hz = expected.values[frame_pairs[:, 1]]
        confidence = np.minimum(recording_confidence[pairs[:, 0]], reference_confidence[pairs[:, 1]])
        valid = np.isfinite(actual_hz) & np.isfinite(expected_hz) & (confidence >= 0.25)
        if valid.sum() < 32:
            diagnostics["trusted_aligned_frames"] = int(valid.sum())
            return {"available": False, "reason": "alignment_low_confidence", "diagnostics": diagnostics, "message": "对齐后可信人声音高不足，本次不给逐音分数。请降低伴奏、减少环境噪声后重录。"}
        frame_pairs, actual_hz, expected_hz = frame_pairs[valid], actual_hz[valid], expected_hz[valid]
        raw_cents = 1200 * np.log2(actual_hz / expected_hz)
        octave_shift = round(float(np.median(raw_cents)) / 1200) * 1200
        cents = raw_cents - octave_shift
        median_abs = float(np.median(np.abs(cents)))
        diagnostics.update({
            "trusted_aligned_frames": int(valid.sum()),
            "trusted_pair_ratio": round(float(valid.mean()), 3),
            "alignment_mode": alignment_mode,
        })
        if median_abs > 600:
            return {"available": False, "reason": "reference_mismatch", "message": "对齐后中位音高差仍超过 600 cents，说明参考人声与练唱旋律不匹配，或分离结果被伴奏污染；本次不输出误导性的 0 分。", "diagnostics": {**diagnostics, "median_deviation_cents": round(median_abs, 1), "reference_source": reference.get("source")}}
        return {"available": True, "recording": recording, "reference_track": expected, "pairs": frame_pairs, "actual_hz": actual_hz, "expected_hz": expected_hz, "cents": cents, "octave_shift": octave_shift, "reference_source": reference.get("source"), "diagnostics": diagnostics, "message": reference.get("message")}
    except Exception as exc:
        logger.exception("solo_pitch_alignment_failed error=%s", exc)
        return {"available": False, "reason": "alignment_failed", "message": f"主旋律对齐未完成：{str(exc)[:180]}。本次不输出逐音分数。"}

def _score_details(cents: np.ndarray) -> tuple[int, float, float]:
    absolute = np.abs(cents)
    median_abs = float(np.median(absolute))
    accurate = float(np.mean(absolute <= 50))
    return _score(100 - median_abs * 0.72 - (1 - accurate) * 18), median_abs, accurate


def _classroom_findings(sections: list[dict], scores: dict[str, int]) -> list[dict]:
    """从实际最弱片段生成可定位的课堂动作，避免四个总分换成固定模板。"""
    findings: list[dict] = []
    usable = [section for section in sections if section.get("voiced_ratio", 0) >= .22]
    weak_voice = min(sections, key=lambda item: item.get("voiced_ratio", 0), default=None)
    if weak_voice and weak_voice.get("voiced_ratio", 0) < .35:
        findings.append({
            "priority": "先处理", "time": weak_voice["time"], "metric": "人声可用性",
            "evidence": f"可用人声 {weak_voice['voiced_ratio']:.0%}",
            "action": f"先在 {weak_voice['time']} 这一段让主唱靠近麦克风、伴奏降到较低音量后重录 20 秒；当前录音不适合把音高稳定度解释为学生唱准程度。",
        })
    if usable:
        unstable = min(usable, key=lambda item: item.get("pitch_stability", 100))
        if unstable.get("pitch_stability", 100) < 72:
            findings.append({
                "priority": "重点练", "time": unstable["time"], "metric": "音高稳定性",
                "evidence": f"稳定度 {unstable['pitch_stability']} 分；{unstable.get('evidence', '')}",
                "action": f"截取 {unstable['time']} 的一句，先给起始音，再做“教师唱两拍—学生回唱两拍—保留长音”的三轮练习；此项描述稳定性，不是跑调判定。",
            })
        rhythmic = [item for item in usable if item.get("rhythm_score") is not None]
        if rhythmic:
            weakest = min(rhythmic, key=lambda item: item["rhythm_score"])
            if weakest["rhythm_score"] < 76:
                findings.append({
                    "priority": "随后练", "time": weakest["time"], "metric": "起音节拍",
                    "evidence": f"起音节拍稳定 {weakest['rhythm_score']} 分",
                    "action": f"在 {weakest['time']} 先只拍恒拍并读节奏，再加旋律；下一次回听只检查每个小组是否同时进入首拍。",
                })
    if scores.get("dynamics", 100) < 65:
        findings.append({
            "priority": "表达练习", "time": "全段", "metric": "力度层次",
            "evidence": f"力度层次 {scores['dynamics']} 分",
            "action": "挑一句句尾做一次渐弱与统一换气，然后录一遍前后对照；评价时记录能否听出句尾变化。",
        })
    if not findings:
        strongest = max(sections, key=lambda item: item.get("pitch_stability", 0), default=None)
        findings.append({
            "priority": "保持并迁移", "time": strongest.get("time", "全段") if strongest else "全段", "metric": "可复用片段",
            "evidence": strongest.get("evidence", "录音证据稳定") if strongest else "录音证据稳定",
            "action": "保留这一段的进入方式和音量平衡，再把同样的排练顺序迁移到最难的一句。",
        })
    # 同一课堂最多呈现三个优先动作，按录音证据排序，避免模板式建议堆叠。
    return findings[:3]


def _suggestions(findings: list[dict]) -> list[str]:
    return [f"{item['time']}｜{item['action']}" for item in findings]

def _segment_metrics(track: PitchTrack, signal: np.ndarray, sr: int, start: float, end: float) -> dict:
    import librosa

    mask = (track.times >= start) & (track.times < end)
    values, confidence = track.values[mask], track.confidence[mask]
    valid = np.isfinite(values) & (confidence >= 0.25)
    voiced_ratio = float(valid.mean()) if len(valid) else 0.0
    local_cents = np.array([])
    if valid.sum() > 2:
        current = values[valid]
        local_cents = 1200 * np.log2(current / np.median(current))
    spread = float(np.median(np.abs(local_cents - np.median(local_cents)))) if len(local_cents) else None
    pitch_score = _score(94 - (spread or 180) / 5 - max(0, .35 - voiced_ratio) * 80) if len(local_cents) else 0
    chunk = signal[int(start * sr):min(len(signal), int(end * sr))]
    if len(chunk) < 512:
        return {"pitch_stability": pitch_score, "voiced_ratio": voiced_ratio, "pitch_spread_cents": spread, "rhythm_score": None, "dynamics_score": None}
    onset = librosa.onset.onset_strength(y=chunk, sr=sr)
    onset_times = librosa.frames_to_time(librosa.onset.onset_detect(onset_envelope=onset, sr=sr), sr=sr)
    intervals = np.diff(onset_times)
    rhythm_score = _score(100 - float(np.std(intervals) / max(np.mean(intervals), .01) * 100)) if len(intervals) >= 2 else None
    rms = librosa.feature.rms(y=chunk)[0]
    dynamic_range = float(np.percentile(rms, 90) - np.percentile(rms, 10))
    return {"pitch_stability": pitch_score, "voiced_ratio": voiced_ratio, "pitch_spread_cents": spread, "rhythm_score": rhythm_score, "dynamics_score": _score(45 + dynamic_range * 260)}


def _segment_feedback(metrics: dict, start: float, end: float) -> dict:
    evidence = [f"可用人声 {metrics['voiced_ratio']:.0%}"]
    if metrics.get("pitch_spread_cents") is not None:
        evidence.append(f"音高离散 {metrics['pitch_spread_cents']:.0f} cents")
    if metrics.get("rhythm_score") is not None:
        evidence.append(f"起音节拍稳定 {metrics['rhythm_score']} 分")
    span = f"{int(start // 60):02d}:{int(start % 60):02d}—{int(end // 60):02d}:{int(end % 60):02d}"
    if metrics["voiced_ratio"] < .22:
        focus, note = "录音可用性", f"{span} 的可信人声只有 {metrics['voiced_ratio']:.0%}，伴奏或环境声覆盖较多。先降伴奏、靠近麦克风录 20 秒；这一段不做音准判断。"
    elif metrics["pitch_stability"] < 55:
        focus, note = "音高稳定性", f"该段音高离散 {metrics.get('pitch_spread_cents') or 0:.0f} cents，主要问题是长音或换气后的轨迹波动。先给起始音，再做两拍回声模唱后接歌词。"
    elif metrics.get("rhythm_score") is not None and metrics["rhythm_score"] < 65:
        focus, note = "起音与节拍", f"该段起音节拍稳定度为 {metrics['rhythm_score']} 分，进入点不够一致。先只拍恒拍并读节奏，再用慢速伴奏完成这一句。"
    elif metrics.get("dynamics_score", 100) < 58:
        focus, note = "力度层次", f"该段能量变化较小（力度层次 {metrics['dynamics_score']} 分）。指定句尾渐弱与统一换气，再录一次前后对照。"
    else:
        focus, note = "可迁移片段", f"该段人声与起音证据较稳定。保留当前进入方式，把相同的速度和音量平衡迁移到下一句。"
    return {"start_seconds": round(start, 1), "end_seconds": round(end, 1), "time": f"{int(start // 60):02d}:{int(start % 60):02d}—{int(end // 60):02d}:{int(end % 60):02d}", "focus": focus, "pitch_stability": metrics["pitch_stability"], "voiced_ratio": round(metrics["voiced_ratio"], 2), "evidence": " · ".join(evidence), "note": note}


def analyze_singing(path: Path) -> dict:
    """课堂整体分析：每一条建议携带录音中的真实音高、节拍或可用人声证据。"""
    try:
        import librosa

        signal, sr = _load_mono_audio(path)
        duration = len(signal) / sr
        if duration < 1:
            raise ValueError("录音时长不足 1 秒")
        track = _pitch_track(path)
        valid = track.values[np.isfinite(track.values)]
        cents = 1200 * np.log2(valid / np.median(valid)) if len(valid) > 2 else np.array([])
        spread = float(np.median(np.abs(cents - np.median(cents)))) if len(cents) else None
        pitch_stability = _score(94 - (spread or 180) / 5 - max(0, .35 - track.voiced_ratio) * 80) if len(cents) else 0
        onset = librosa.onset.onset_strength(y=signal, sr=sr)
        tempo, beats = librosa.beat.beat_track(onset_envelope=onset, sr=sr)
        intervals = np.diff(librosa.frames_to_time(beats, sr=sr))
        rhythm = _score(100 - float(np.std(intervals) / max(np.mean(intervals), .01) * 100)) if len(intervals) >= 3 else 55
        rms = librosa.feature.rms(y=signal)[0]
        dynamic_range = float(np.percentile(rms, 90) - np.percentile(rms, 10))
        dynamics = _score(45 + dynamic_range * 260)
        spectral = librosa.feature.spectral_centroid(y=signal, sr=sr)[0]
        clarity = _score(45 + min(45, float(np.median(spectral)) / 55) - max(0, 0.16 - float(np.mean(rms))) * 100)
        scores = {"pitch_stability": pitch_stability, "rhythm_regularness": rhythm, "dynamics": dynamics, "clarity": clarity}
        section_count = min(6, max(3, int(duration // 7) + 1))
        sections = [_segment_feedback(_segment_metrics(track, signal, sr, i * duration / section_count, (i + 1) * duration / section_count), i * duration / section_count, (i + 1) * duration / section_count) for i in range(section_count)]
        raw_tempo = float(np.asarray(tempo).item())
        findings = _classroom_findings(sections, scores)
        classroom_evidence = {
            "quality": {"voiced_ratio": round(track.voiced_ratio, 2), "pitch_spread_cents": round(spread, 1) if spread is not None else None, "pitch_backend": track.backend},
            "summary": f"全段可用人声 {track.voiced_ratio:.0%}；音高离散 {round(spread) if spread is not None else '—'} cents；节拍稳定 {rhythm} 分。",
            "limitations": ["课堂整体分析基于整段录音，显示的是声音轨迹与起音证据；没有参考主旋律时，不判断学生是否唱准。"] if track.voiced_ratio < .72 else ["没有参考主旋律时，音高稳定度不等同于跑调结论。"],
        }
        return {"analysis_available": True, "duration_seconds": round(duration, 1), "tempo_bpm": int(round(raw_tempo)) if np.isfinite(raw_tempo) and raw_tempo > 0 else None, "scores": scores, "pitch_track": _compact_pitch_track(track.values, track.times), "segment_feedback": sections, "classroom_evidence": classroom_evidence, "findings": findings, "suggestions": _suggestions(findings)}
    except Exception as exc:
        return {"analysis_available": False, "duration_seconds": 0.0, "tempo_bpm": None, "scores": {}, "segment_feedback": [], "classroom_evidence": {}, "suggestions": [f"无法完成声学分析：{str(exc)[:160]}。请上传清晰的 WAV、MP3 或 M4A 录音。"]}


def _compact_pitch_track(f0: np.ndarray, times: np.ndarray, points: int = 90) -> list[dict]:
    if not len(f0):
        return []
    indices = np.linspace(0, len(f0) - 1, min(points, len(f0))).astype(int)
    return [{"t": round(float(times[i]), 2), "hz": round(float(f0[i]), 1) if np.isfinite(f0[i]) else None} for i in indices]


def compare_intonation(recording_path: Path, reference: dict) -> dict:
    aligned = _align_tracks(recording_path, reference)
    if not aligned.get("available"):
        return {"available": False, "reason": aligned.get("reason"), "message": aligned.get("message"), "diagnostics": aligned.get("diagnostics", {})}
    cents = aligned["cents"]
    score, median_abs, accurate = _score_details(cents)
    segments = []
    for i, values in enumerate(np.array_split(cents, 4)):
        error = float(np.median(np.abs(values)))
        segments.append({"part": f"第 {i + 1} 段", "median_deviation_cents": round(error, 1), "off_pitch_ratio": round(float(np.mean(np.abs(values) > 50)) * 100), "status": "稳定" if error < 30 else "可校准" if error < 55 else "建议回声模唱"})
    return {"available": True, "intonation_score": score, "status": "较准" if score >= 80 else "局部需校准" if score >= 60 else "音准需重点练习", "median_deviation_cents": round(median_abs, 1), "off_pitch_ratio": round((1 - accurate) * 100), "global_offset_cents": 0, "octave_adjustment_cents": aligned["octave_shift"], "reference_source": aligned["reference_source"], "segments": segments, "message": f"{aligned['message']} 已用动态时间规整对齐两次演唱；仅消除 {aligned['octave_shift']:+.0f} cents 的整八度声部差异，半音偏差仍会计入结果。", "_aligned": aligned}


def _smooth_midi(values: np.ndarray, window: int = 5) -> np.ndarray:
    rounded = np.rint(_midi(values))
    result = rounded.copy()
    for index in range(len(rounded)):
        nearby = rounded[max(0, index - window // 2): index + window // 2 + 1]
        nearby = nearby[np.isfinite(nearby)]
        if len(nearby):
            result[index] = round(float(np.median(nearby)))
    return result


def assess_note_accuracy(recording_path: Path, reference: dict, aligned: dict | None = None) -> dict:
    """基于 DTW 后的人声轨迹分段，不再转写混音伴奏中的所有乐器。"""
    if not reference.get("available"):
        return {"available": False, "reason": reference.get("code"), "message": reference.get("message")}
    aligned = aligned or _align_tracks(recording_path, reference)
    if not aligned.get("available"):
        return {"available": False, "reason": aligned.get("reason"), "message": aligned.get("message")}
    try:
        import librosa

        ref_track, pairs = aligned["reference_track"], aligned["pairs"]
        expected_hz, actual_hz, cents = aligned["expected_hz"], aligned["actual_hz"], aligned["cents"]
        expected_midi = _smooth_midi(expected_hz)
        events, start = [], 0
        def append_event(begin: int, finish: int):
            if finish - begin < 5:
                return
            group = expected_midi[begin:finish]
            group = group[np.isfinite(group)]
            if not len(group):
                return
            midi = int(round(float(np.median(group))))
            start_ref, end_ref = pairs[begin, 1], pairs[finish - 1, 1]
            start_time, end_time = float(ref_track.times[min(start_ref, end_ref)]), float(ref_track.times[max(start_ref, end_ref)])
            if end_time - start_time < .14:
                return
            deviation = float(np.median(cents[begin:finish]))
            events.append({"index": len(events) + 1, "start_seconds": round(start_time, 2), "end_seconds": round(end_time, 2), "expected_midi": midi, "expected_note": librosa.midi_to_note(midi), "actual_hz": round(float(np.median(actual_hz[begin:finish])), 1), "deviation_cents": round(deviation, 1), "status": "较准" if abs(deviation) <= 35 else "偏高" if deviation > 0 else "偏低"})
        for index in range(1, len(expected_midi) + 1):
            if index == len(expected_midi) or expected_midi[index] != expected_midi[start]:
                append_event(start, index)
                start = index
        if len(events) < 3:
            return {"available": False, "reason": "note_segmentation_failed", "message": "人声旋律未形成足够稳定的音符片段；请上传更清晰、无伴奏或伴奏较低的单人参考与练唱。"}
        values = np.asarray([item["deviation_cents"] for item in events])
        score, median_abs, accurate = _score_details(values)
        return {"available": True, "method": "vocal_f0_dtw_note_segments", "score": score, "matched_notes": len(events), "accurate_note_ratio": round(accurate * 100), "median_deviation_cents": round(median_abs, 1), "events": events[:48], "message": "目标音来自已对齐的参考人声主旋律；没有把伴奏和低音声部当作学生应唱的音。"}
    except Exception as exc:
        return {"available": False, "reason": "note_assessment_failed", "message": f"逐音评测未完成：{str(exc)[:160]}。课堂整体分析仍已保存。"}


def compare_waveforms(reference: list[float] | None, recording: list[float]) -> dict:
    if not reference:
        return {"has_reference_comparison": False, "reference_waveform": None, "recording_waveform": recording, "reference_similarity": None}
    a, b = np.asarray(reference, dtype=float), np.asarray(recording, dtype=float)
    length = min(len(a), len(b))
    if length <= 3 or np.std(a[:length]) < 1e-8 or np.std(b[:length]) < 1e-8:
        return {"has_reference_comparison": True, "reference_waveform": reference, "recording_waveform": recording, "reference_similarity": None, "comparison_note": "其中一段音频的能量变化过小，已跳过波形相似度；这不是音准结论。"}
    correlation = float(np.corrcoef(a[:length], b[:length])[0, 1])
    if not np.isfinite(correlation):
        return {"has_reference_comparison": True, "reference_waveform": reference, "recording_waveform": recording, "reference_similarity": None, "comparison_note": "两段音频无法形成有效波形相关性，已跳过此展示指标。"}
    return {"has_reference_comparison": True, "reference_waveform": reference, "recording_waveform": recording, "reference_similarity": _score(50 + correlation * 45)}
