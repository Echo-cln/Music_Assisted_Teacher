"""Audiveris 图片/PDF 五线谱识别适配层。

Audiveris 是本地安装的开源 OMR 程序。它不会被伪装成浏览器内置能力：未安装、
超时、没有导出 MusicXML 都会返回可定位的错误，方便教师真正处理识谱失败。
"""
from __future__ import annotations

import shlex
import subprocess
import tempfile
from pathlib import Path

from app.core.config import get_settings

SUPPORTED_OMR_SUFFIXES = {"png", "jpg", "jpeg", "webp", "tif", "tiff", "pdf"}


class OMRUnavailableError(RuntimeError):
    """Audiveris 没有安装或没有配置时的明确错误。"""


def _command_parts(command: str) -> list[str]:
    parts = shlex.split(command, posix=False)
    if not parts:
        raise OMRUnavailableError(
            "尚未配置 AUDIVERIS_COMMAND，无法识别图片/PDF 五线谱。"
            "请安装官方 Audiveris 后，在 backend/.env 填写其可执行文件完整路径，"
            "例如 AUDIVERIS_COMMAND=C:\\Program Files\\Audiveris\\bin\\Audiveris.bat。"
        )
    return parts


def _export_file(output_dir: Path) -> Path | None:
    # 只接收 Audiveris 导出的 MusicXML，不把中间 .omr/.xml 配置误当作乐谱。
    candidates = [
        path for path in output_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".musicxml", ".mxl"}
    ]
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def recognize_staff_image(raw: bytes, filename: str, suffix: str) -> tuple[bytes, dict]:
    """将一张图片或 PDF 送至本机 Audiveris，返回导出的 MusicXML 字节和说明。"""
    if suffix.lower() not in SUPPORTED_OMR_SUFFIXES:
        raise ValueError("仅支持 PNG/JPG/WEBP/TIFF/PDF 五线谱图片")
    settings = get_settings()
    executable = _command_parts(settings.audiveris_command)
    with tempfile.TemporaryDirectory(prefix="xiangyin-omr-") as directory:
        root = Path(directory)
        source = root / f"score.{suffix.lower()}"
        output = root / "export"
        source.write_bytes(raw)
        output.mkdir()
        # Audiveris 的官方批处理导出参数。传列表而不是 shell 字符串，避免文件名注入。
        command = [*executable, "-batch", "-export", "-output", str(output), str(source)]
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=max(30, settings.omr_timeout_seconds), check=False
            )
        except FileNotFoundError as exc:
            raise OMRUnavailableError(f"找不到 Audiveris：{executable[0]}。请检查 AUDIVERIS_COMMAND 的路径。") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Audiveris 在 {settings.omr_timeout_seconds} 秒内没有完成识别；请裁剪为单页、清晰的五线谱后重试。") from exc
        exported = _export_file(output)
        if result.returncode != 0 or not exported:
            detail = (result.stderr or result.stdout or "未导出 MusicXML").strip().replace("\n", " ")[:500]
            raise RuntimeError(f"Audiveris 识谱失败（退出码 {result.returncode}）：{detail}")
        return exported.read_bytes(), {
            "engine": "Audiveris",
            "source_filename": filename,
            "warning": "识谱结果已导入钢琴卷帘；请逐小节核对音高、节奏、连音与调号后再用于课堂。",
        }
