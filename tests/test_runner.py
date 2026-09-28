from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from denops_ai_builder.analysis import analyze_task, claim_daily_api_attempt
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
            ["OPENAI_API_KEY", "DENOPS_AI_OPENAI_ENABLED"],
            status.missing_configuration,
        )

    def test_task_with_both_services_is_ready(self) -> None:
        root = self.make_root("Implement one small feature.\n")
        status = run_once(
            root,
            environment={
                "DENOPS_AI_PROVIDER": "openai",
                "OPENAI_API_KEY": "test-key",
                "DENOPS_AI_OPENAI_ENABLED": "1",
            },
        )
        self.assertEqual("ready", status.stage)

    def test_analysis_writes_reviewable_plan(self) -> None:
        class FakeProvider:
            def create_plan(self, task: str, policy: str) -> str:
                self.assertions = (task, policy)
                return "1. Make one small change.\n2. Run tests."

        root = self.make_root("Implement one small feature.\n")
        (root / "policies").mkdir()
        (root / "policies" / "builder-policy.md").write_text(
            "Stay in the repository.", encoding="utf-8"
        )
        plan = analyze_task(
            root,
            environment={
                "OPENAI_API_KEY": "test-key",
                "DENOPS_AI_OPENAI_ENABLED": "1",
            },
            provider=FakeProvider(),
        )
        self.assertIn("Run tests", plan)
        self.assertEqual(
            "review-ready",
            json.loads((root / "state" / "status.json").read_text())["stage"],
        )

    def test_daily_api_attempt_limit_fails_closed(self) -> None:
        root = self.make_root()
        environment = {"DENOPS_AI_DAILY_CALL_LIMIT": "1"}
        self.assertEqual(1, claim_daily_api_attempt(root, environment))
        with self.assertRaisesRegex(RuntimeError, "daily OpenAI test-call limit"):
            claim_daily_api_attempt(root, environment)

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
