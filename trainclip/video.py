"""FFprobe metadata, FFmpeg frame sampling and atomic clip export."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
from collections.abc import Callable, Iterator

from .core import Interval


class Cancelled(Exception):
    pass


def _run(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError(f"必要な実行ファイルが見つかりません: {args[0]}") from exc
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()[-1200:]
        raise RuntimeError(detail or f"{args[0]} failed ({result.returncode})")
    return result


def probe(path: Path) -> dict:
    result = _run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate",
        "-of", "json", str(path),
    ])
    data = json.loads(result.stdout)
    stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if not stream:
        raise RuntimeError("映像ストリームがありません")
    duration = float(data.get("format", {}).get("duration", 0))
    if duration <= 0:
        raise RuntimeError("動画の長さを取得できません")
    fraction = stream.get("avg_frame_rate", "0/1").split("/")
    fps = float(fraction[0]) / float(fraction[1]) if len(fraction) == 2 and float(fraction[1]) else 0.0
    return {
        "duration": duration,
        "width": int(stream.get("width", 0)),
        "height": int(stream.get("height", 0)),
        "fps": fps,
        "codec": stream.get("codec_name", "?"),
    }


def frames(
    path: Path, *, fps: float, cancelled: Callable[[], bool]
) -> Iterator[tuple[float, object]]:
    """Yield sampled BGR arrays. The fps filter uses a regular output time grid."""
    import numpy as np

    width, height = 640, 360
    frame_size = width * height * 3
    args = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(path),
        "-an", "-sn", "-vf",
        f"fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
        "-pix_fmt", "bgr24", "-f", "rawvideo", "pipe:1",
    ]
    with tempfile.TemporaryFile() as error_file:
        try:
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=error_file)
        except FileNotFoundError as exc:
            raise RuntimeError("FFmpeg が見つかりません") from exc
        index = 0
        try:
            assert process.stdout is not None
            while True:
                if cancelled():
                    raise Cancelled()
                raw = process.stdout.read(frame_size)
                if not raw:
                    break
                if len(raw) != frame_size:
                    raise RuntimeError("途中でフレームが途切れました")
                yield index / fps, np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3)
                index += 1
            if process.wait() != 0:
                error_file.seek(0)
                error = error_file.read().decode("utf-8", errors="replace").strip()
                raise RuntimeError(error[-1200:] or "FFmpeg の解析に失敗しました")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            if process.stdout:
                process.stdout.close()


def export_clip(
    source: Path, destination: Path, clip: Interval, *, exact: bool,
    cancelled: Callable[[], bool],
) -> None:
    if clip.end <= clip.start:
        raise ValueError("空の切り出し範囲です")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.stem + ".part.mp4")
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    if exact:
        args += ["-i", str(source), "-ss", f"{clip.start:.3f}", "-t", f"{clip.end - clip.start:.3f}",
                 "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium",
                 "-crf", "18", "-c:a", "aac", "-movflags", "+faststart"]
    else:
        args += ["-ss", f"{clip.start:.3f}", "-i", str(source), "-t", f"{clip.end - clip.start:.3f}",
                 "-map", "0:v:0", "-map", "0:a?", "-c", "copy", "-avoid_negative_ts", "make_zero"]
    args.append(str(temporary))
    try:
        process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise RuntimeError("FFmpeg が見つかりません") from exc
    try:
        while True:
            if cancelled():
                process.kill()
                process.communicate()
                raise Cancelled()
            try:
                _, error_bytes = process.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                continue
        error = error_bytes.decode("utf-8", errors="replace").strip()
        if process.returncode:
            raise RuntimeError(error[-1200:] or "FFmpeg の切り出しに失敗しました")
        os.replace(temporary, destination)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
        if process.stderr:
            process.stderr.close()
        temporary.unlink(missing_ok=True)

