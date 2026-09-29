"""Pure event and clip planning logic; independent from the AI and FFmpeg."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Sample:
    time: float
    confidence: float
    area_percent: float = 0.0


@dataclass(frozen=True)
class Interval:
    start: float
    end: float


def train_events(
    samples: list[Sample],
    *,
    sample_fps: float,
    confidence: float,
    min_area_percent: float,
    consecutive: int,
    merge_gap: float,
    duration: float,
) -> list[Interval]:
    """Find confirmed runs, then join runs separated by at most merge_gap seconds."""
    if sample_fps <= 0 or consecutive < 1 or merge_gap < 0 or duration < 0:
        raise ValueError("Invalid event settings")
    period = 1.0 / sample_fps
    runs: list[Interval] = []
    run_start: float | None = None
    run_end = 0.0
    run_count = 0

    def finish_run() -> None:
        nonlocal run_start, run_end, run_count
        if run_start is not None and run_count >= consecutive:
            runs.append(Interval(run_start, min(duration, run_end + period)))
        run_start = None
        run_count = 0

    previous_time: float | None = None
    for sample in samples:
        if sample.time < 0 or (previous_time is not None and sample.time <= previous_time):
            raise ValueError("Sample times must be nonnegative and increasing")
        present = (
            sample.confidence > 0
            and sample.confidence >= confidence
            and sample.area_percent >= min_area_percent
        )
        # A missing decoded sample must not count as a consecutive detection.
        if previous_time is not None and sample.time - previous_time > period * 1.5:
            finish_run()
        if present:
            if run_start is None:
                run_start = sample.time
            run_count += 1
            run_end = sample.time
        else:
            finish_run()
        previous_time = sample.time
    finish_run()

    merged: list[Interval] = []
    for run in runs:
        if merged and run.start - merged[-1].end <= merge_gap + 1e-9:
            merged[-1] = Interval(merged[-1].start, max(merged[-1].end, run.end))
        else:
            merged.append(run)
    return merged


def clip_ranges(
    events: list[Interval], *, before: float, after: float, duration: float
) -> list[Interval]:
    """Pad and clamp events, merging overlapping output ranges."""
    if before < 0 or after < 0 or duration < 0:
        raise ValueError("Invalid clip settings")
    clips: list[Interval] = []
    for event in sorted(events, key=lambda item: item.start):
        start = max(0.0, event.start - before)
        end = min(duration, event.end + after)
        if end <= start:
            continue
        if clips and start <= clips[-1].end:
            clips[-1] = Interval(clips[-1].start, max(clips[-1].end, end))
        else:
            clips.append(Interval(start, end))
    return clips


def clock_time(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 3600:02d}:{(total // 60) % 60:02d}:{total % 60:02d}"

