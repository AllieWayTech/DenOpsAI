from __future__ import annotations

import os
import tempfile
import json
import fcntl
from datetime import UTC, datetime
from pathlib import Path

from .provider import PlanningProvider, provider_from_environment
from .runner import normalized_task, run_once
from .state import BuilderStatus, write_status


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", text=True
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content.rstrip() + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def claim_daily_api_attempt(
    root: Path, environment: dict[str, str] | None = None
) -> int:
    values = os.environ if environment is None else environment
    try:
        limit = int(values.get("DENOPS_AI_DAILY_CALL_LIMIT", "1"))
    except ValueError as error:
        raise RuntimeError("DENOPS_AI_DAILY_CALL_LIMIT must be an integer") from error
    if not 1 <= limit <= 5:
        raise RuntimeError("DENOPS_AI_DAILY_CALL_LIMIT must be between 1 and 5")

    state_dir = root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    date = datetime.now(UTC).date().isoformat()
    usage_path = state_dir / f"openai-usage-{date}.json"
    lock_path = state_dir / "openai-usage.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        attempts = 0
        if usage_path.exists():
            try:
                usage = json.loads(usage_path.read_text(encoding="utf-8"))
                attempts = int(usage.get("attempts", 0))
            except (OSError, ValueError, json.JSONDecodeError, AttributeError) as error:
                raise RuntimeError("OpenAI usage counter is invalid") from error
        if attempts >= limit:
            raise RuntimeError(f"daily OpenAI test-call limit reached ({limit})")
        attempts += 1
        _write_text_atomic(
            usage_path,
            json.dumps({"date": date, "attempts": attempts, "limit": limit}, sort_keys=True),
        )
        return attempts


def analyze_task(
    root: Path,
    environment: dict[str, str] | None = None,
    provider: PlanningProvider | None = None,
) -> str:
    root = root.resolve(strict=True)
    readiness = run_once(root, environment=environment)
    if readiness.stage != "ready":
        raise RuntimeError(readiness.reason)

    task = normalized_task(root / "tasks" / "current.md")
    if len(task.encode("utf-8")) > 64 * 1024:
        raise RuntimeError("task exceeds the 64 KiB limit")
    policy = (root / "policies" / "builder-policy.md").read_text(encoding="utf-8")
    if provider is None:
        claim_daily_api_attempt(root, environment)
    active_provider = provider or provider_from_environment(environment)
    plan = active_provider.create_plan(task, policy)
    _write_text_atomic(root / "state" / "latest-plan.md", plan)
    write_status(
        root / "state" / "status.json",
        BuilderStatus(
            stage="review-ready",
            reason="OpenAI produced an implementation plan for human review",
            task_present=True,
        ),
    )
    return plan
