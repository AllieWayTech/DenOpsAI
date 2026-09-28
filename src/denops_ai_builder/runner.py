from __future__ import annotations

import fcntl
import os
import re
from pathlib import Path

from .state import BuilderStatus, write_status

OPENAI_KEY_SETTING = "OPENAI_API_KEY"
MODEL_SETTING = "DENOPS_AI_MODEL_URL"
SAFEGUARD_SETTING = "DENOPS_AI_SAFEGUARD_URL"


def normalized_task(task_path: Path) -> str:
    if not task_path.exists():
        return ""
    content = task_path.read_text(encoding="utf-8")
    without_comments = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    return without_comments.strip()


def configuration_gaps(environment: dict[str, str] | None = None) -> list[str]:
    values = os.environ if environment is None else environment
    provider = values.get("DENOPS_AI_PROVIDER", "openai")
    if provider == "openai":
        missing = [] if values.get(OPENAI_KEY_SETTING) else [OPENAI_KEY_SETTING]
        if values.get("DENOPS_AI_OPENAI_ENABLED") != "1":
            missing.append("DENOPS_AI_OPENAI_ENABLED")
        return missing
    if provider == "gpt-oss":
        return [name for name in (MODEL_SETTING, SAFEGUARD_SETTING) if not values.get(name)]
    return ["DENOPS_AI_PROVIDER"]


def run_once(root: Path, environment: dict[str, str] | None = None) -> BuilderStatus:
    root = root.resolve(strict=True)
    task_path = root / "tasks" / "current.md"
    status_path = root / "state" / "status.json"
    lock_path = root / "state" / "builder.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("another builder process holds the lock") from error

        task = normalized_task(task_path)
        if not task:
            status = BuilderStatus(
                stage="idle", reason="no task queued", task_present=False
            )
        else:
            missing = configuration_gaps(environment)
            if missing:
                status = BuilderStatus(
                    stage="blocked",
                    reason="required model services are not configured",
                    task_present=True,
                    missing_configuration=missing,
                )
            else:
                status = BuilderStatus(
                    stage="ready",
                    reason="task and model service configuration are present",
                    task_present=True,
                )

        write_status(status_path, status)
        return status
