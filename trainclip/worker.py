"""Background batch processing. A failed source never stops the remaining queue."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import threading
import time

from PySide6.QtCore import QThread, Signal

from .cache import AnalysisCache
from .core import clip_ranges, clock_time, train_events
from .detector import TrainDetector
from .video import Cancelled, export_clip, frames, probe


@dataclass(frozen=True)
class Options:
    source: Path
    output: Path
    recursive: bool = True
    force_analysis: bool = False
    before: float = 10
    after: float = 10
    minimum_duration: float = 20
    analysis_fps: float = 2
    confidence: float = 0.5
    consecutive: int = 2
    merge_gap: float = 10
    min_area_percent: float = 0
    model: str = "COCO_V1"
    device: str = "auto"
    exact: bool = True


class BatchWorker(QThread):
    found = Signal(str, str)
    state = Signal(str, str, str, str)
    overall = Signal(int, int)
    current = Signal(str, int, str)
    message = Signal(str)
    finished_summary = Signal(int, int, bool)

    def __init__(self, options: Options):
        super().__init__()
        self.options = options
        self.stop_event = threading.Event()

    def cancel(self) -> None:
        self.stop_event.set()

    def _cancelled(self) -> bool:
        return self.stop_event.is_set()

    def _sources(self) -> list[Path]:
        options = self.options
        iterator = options.source.rglob("*") if options.recursive else options.source.iterdir()
        output = options.output.resolve()
        return sorted(
            (path for path in iterator if path.is_file() and path.suffix.casefold() == ".mp4"
             and not path.resolve().is_relative_to(output)),
            key=lambda path: str(path).casefold(),
        )

    def _log(self, log_file, kind: str, **fields) -> None:
        payload = {"time": datetime.now().astimezone().isoformat(timespec="seconds"),
                   "kind": kind, **fields}
        log_file.write(json.dumps(payload, ensure_ascii=False) + "\n")
        log_file.flush()

    def run(self) -> None:
        options = self.options
        processed = 0
        errors = 0
        cancelled = False
        started = time.monotonic()
        try:
            sources = self._sources()
            self.overall.emit(0, len(sources))
            if not sources:
                self.message.emit("MP4 ファイルが見つかりませんでした。")
                self.finished_summary.emit(0, 0, False)
                return
            for path in sources:
                self.found.emit(str(path), str(path.relative_to(options.source)))
            options.output.mkdir(parents=True, exist_ok=True)
            log_dir = options.output / "logs"
            log_dir.mkdir(exist_ok=True)
            log_path = log_dir / f"{datetime.now():%Y-%m-%d}.jsonl"
            with log_path.open("a", encoding="utf-8") as log_file:
                cache = AnalysisCache(options.output / ".trainclip.sqlite")
                detector: TrainDetector | None = None
                try:
                    self._log(log_file, "batch_start", source=str(options.source),
                              output=str(options.output), count=len(sources))
                    for path in sources:
                        if self._cancelled():
                            cancelled = True
                            break
                        label = str(path.relative_to(options.source))
                        file_started = time.monotonic()
                        self.state.emit(str(path), "-", "-", "解析中")
                        self.message.emit(f"解析中: {label}")
                        try:
                            info = probe(path)
                            initial_stat = path.stat()
                            duration = info["duration"]
                            duration_label = clock_time(duration)
                            if duration < options.minimum_duration:
                                self.state.emit(str(path), duration_label, "0", "スキップ")
                                self._log(log_file, "skip", file=str(path), reason="short",
                                          duration=duration)
                                continue
                            def make_analysis_key() -> str:
                                model_path = Path(options.model)
                                model_stamp = (model_path.stat().st_size, model_path.stat().st_mtime_ns) if model_path.is_file() else None
                                return json.dumps({"model": options.model,
                                                   "model_stamp": model_stamp,
                                                   "fps": options.analysis_fps,
                                                   "device": options.device,
                                                   "min_area_percent": options.min_area_percent},
                                                  sort_keys=True)

                            analysis_key = make_analysis_key()
                            samples = None if options.force_analysis else cache.get(path, analysis_key)
                            if samples is None:
                                if detector is None:
                                    self.message.emit("AI モデルを読み込み中です。初回は取得に時間がかかります。")
                                    detector = TrainDetector(options.model, options.device,
                                                             options.min_area_percent)
                                    analysis_key = make_analysis_key()
                                samples = []
                                for position, frame in frames(path, fps=options.analysis_fps,
                                                              cancelled=self._cancelled):
                                    samples.append(detector.detect(position, frame))
                                    percent = min(100, int(100 * position / duration))
                                    self.current.emit(label, percent,
                                                      f"{clock_time(position)} / {duration_label}")
                                if self._cancelled():
                                    raise Cancelled()
                                if not samples:
                                    raise RuntimeError("解析できるフレームがありません")
                                current_stat = path.stat()
                                if (current_stat.st_size, current_stat.st_mtime_ns) != (initial_stat.st_size, initial_stat.st_mtime_ns):
                                    raise RuntimeError("解析中に元動画が変更されました")
                                self.current.emit(label, 100, duration_label)
                                cache.put(path, analysis_key, samples)
                                self.message.emit(f"AI 解析完了: {label} ({len(samples)} フレーム)")
                            else:
                                self.current.emit(label, 100, "保存済みの解析結果を使用")
                                self.message.emit(f"解析結果を再利用: {label}")
                            current_stat = path.stat()
                            if (current_stat.st_size, current_stat.st_mtime_ns) != (initial_stat.st_size, initial_stat.st_mtime_ns):
                                raise RuntimeError("処理中に元動画が変更されました")
                            events = train_events(
                                samples, sample_fps=options.analysis_fps,
                                confidence=options.confidence,
                                min_area_percent=options.min_area_percent,
                                consecutive=options.consecutive, merge_gap=options.merge_gap,
                                duration=duration,
                            )
                            clips = clip_ranges(events, before=options.before,
                                                after=options.after, duration=duration)
                            if not clips:
                                self.state.emit(str(path), duration_label, "0", "列車なし")
                            else:
                                self.state.emit(str(path), duration_label, str(len(events)), "切り出し中")
                                relative = path.relative_to(options.source)
                                for index, clip in enumerate(clips, 1):
                                    destination = options.output / relative.parent / f"{path.stem}_{index:03d}.mp4"
                                    export_clip(path, destination, clip, exact=options.exact,
                                                cancelled=self._cancelled)
                                    self.message.emit(f"保存: {destination}")
                                self.state.emit(str(path), duration_label, str(len(events)), "完了")
                            self._log(log_file, "file_done", file=str(path), metadata=info,
                                      model=options.model, confidence=options.confidence,
                                      analysis_fps=options.analysis_fps, sample_count=len(samples),
                                      events=[event.__dict__ for event in events],
                                      clips=[clip.__dict__ for clip in clips],
                                      output_mode="exact" if options.exact else "fast",
                                      elapsed_seconds=round(time.monotonic() - file_started, 3))
                        except Cancelled:
                            cancelled = True
                            self.state.emit(str(path), "-", "-", "中断")
                            self._log(log_file, "cancelled", file=str(path))
                            break
                        except Exception as exc:
                            errors += 1
                            self.state.emit(str(path), "-", "-", "エラー")
                            self.message.emit(f"エラー: {label}: {exc}")
                            self._log(log_file, "error", file=str(path), error=str(exc),
                                      elapsed_seconds=round(time.monotonic() - file_started, 3))
                        finally:
                            if not cancelled:
                                processed += 1
                                self.overall.emit(processed, len(sources))
                    self._log(log_file, "batch_end", processed=processed, errors=errors,
                              cancelled=cancelled,
                              elapsed_seconds=round(time.monotonic() - started, 3))
                finally:
                    cache.close()
        except Exception as exc:
            errors += 1
            self.message.emit(f"処理を開始できません: {exc}")
        self.finished_summary.emit(processed, errors, cancelled)

