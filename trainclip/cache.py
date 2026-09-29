"""Per-file analysis cache for repeat clipping and file-level resume."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import sqlite3

from .core import Sample


class AnalysisCache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS analysis ("
            "path TEXT PRIMARY KEY, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL, "
            "analysis_key TEXT NOT NULL, samples_json TEXT NOT NULL)"
        )
        self.connection.commit()

    def get(self, path: Path, analysis_key: str) -> list[Sample] | None:
        stat = path.stat()
        row = self.connection.execute(
            "SELECT samples_json FROM analysis WHERE path=? AND size=? AND mtime_ns=? AND analysis_key=?",
            (str(path.resolve()), stat.st_size, stat.st_mtime_ns, analysis_key),
        ).fetchone()
        return [Sample(**item) for item in json.loads(row[0])] if row else None

    def put(self, path: Path, analysis_key: str, samples: list[Sample]) -> None:
        stat = path.stat()
        self.connection.execute(
            "INSERT OR REPLACE INTO analysis VALUES (?, ?, ?, ?, ?)",
            (str(path.resolve()), stat.st_size, stat.st_mtime_ns, analysis_key,
             json.dumps([asdict(item) for item in samples], ensure_ascii=False)),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

