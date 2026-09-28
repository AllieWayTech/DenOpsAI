from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from denops_ai_builder.runner import run_once
from denops_ai_builder.state import BuilderStatus, write_status
from denops_ai_builder.web import _authorized, write_task


class RunnerTests(unittest.TestCase):
    def make_root(self, task: str = "") -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "tasks").mkdir()
        (root / "state").mkdir()
        (root / "tasks" / "current.md").write_text(task, encoding="utf-8")
        return root

    def test_empty_or_comment_only_task_is_idle(self) -> None:
        root = self.make_root("<!-- no task -->\n")
        status = run_once(root, environment={})
        self.assertEqual("idle", status.stage)
        self.assertFalse(status.task_present)

    def test_task_without_model_services_fails_closed(self) -> None:
        root = self.make_root("Implement one small feature.\n")
        status = run_once(root, environment={})
        self.assertEqual("blocked", status.stage)
        self.assertEqual(
            ["DENOPS_AI_MODEL_URL", "DENOPS_AI_SAFEGUARD_URL"],
            status.missing_configuration,
        )

    def test_task_with_both_services_is_ready(self) -> None:
        root = self.make_root("Implement one small feature.\n")
        status = run_once(
            root,
            environment={
                "DENOPS_AI_MODEL_URL": "http://model.internal/v1",
                "DENOPS_AI_SAFEGUARD_URL": "http://safeguard.internal/v1",
            },
        )
        self.assertEqual("ready", status.stage)

    def test_status_document_is_valid_json(self) -> None:
        root = self.make_root()
        expected = BuilderStatus("idle", "test", False)
        status_path = root / "state" / "status.json"
        write_status(status_path, expected)
        actual = json.loads(status_path.read_text(encoding="utf-8"))
        self.assertEqual("idle", actual["stage"])
        self.assertEqual(1, actual["schema_version"])

    def test_web_task_write_is_atomic_and_normalized(self) -> None:
        root = self.make_root()
        task_path = root / "tasks" / "current.md"
        write_task(task_path, "One task")
        self.assertEqual("One task\n", task_path.read_text(encoding="utf-8"))

    def test_basic_authentication_requires_admin_and_exact_password(self) -> None:
        import base64

        valid = "Basic " + base64.b64encode(b"admin:correct").decode("ascii")
        wrong_user = "Basic " + base64.b64encode(b"owner:correct").decode("ascii")
        self.assertTrue(_authorized(valid, "correct"))
        self.assertFalse(_authorized(wrong_user, "correct"))
        self.assertFalse(_authorized(valid, "wrong"))


if __name__ == "__main__":
    unittest.main()
