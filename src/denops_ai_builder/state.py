from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BuilderStatus:
    stage: str
    reason: str
    task_present: bool
    missing_configuration: list[str] = field(default_factory=list)
    updated_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def write_status(path: Path, status: BuilderStatus) -> None:
    """Atomically replace the public status document."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(status.to_dict(), indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", text=True
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)

