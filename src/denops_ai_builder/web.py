from __future__ import annotations

import base64
import hmac
import html
import json
import os
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from .analysis import analyze_task
from .runner import normalized_task, run_once

MAX_TASK_BYTES = 64 * 1024


def write_task(path: Path, content: str) -> None:
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_TASK_BYTES:
        raise ValueError("task exceeds the 64 KiB limit")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            if encoded and not encoded.endswith(b"\n"):
                handle.write(b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _authorized(header: str | None, password: str) -> bool:
    if not password or not header or not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:], validate=True).decode("utf-8")
        username, supplied_password = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError):
        return False
    return hmac.compare_digest(username, "admin") and hmac.compare_digest(
        supplied_password, password
    )


def _read_status(root: Path) -> dict[str, object]:
    path = root / "state" / "status.json"
    if not path.exists():
        return {"stage": "not-run", "reason": "readiness check has not run"}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"stage": "error", "reason": "status document is unreadable"}
    return value if isinstance(value, dict) else {"stage": "error", "reason": "invalid status"}


def handler_for(root: Path, password: str) -> type[BaseHTTPRequestHandler]:
    resolved_root = root.resolve(strict=True)

    class BuilderHandler(BaseHTTPRequestHandler):
        server_version = "DenOpsAIBuilder/0.1"

        def _security_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")

        def _require_authentication(self) -> bool:
            if _authorized(self.headers.get("Authorization"), password):
                return True
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self.send_header("WWW-Authenticate", 'Basic realm="DenOps AI"')
            self._security_headers()
            self.end_headers()
            return False

        def _redirect_home(self) -> None:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self._security_headers()
            self.end_headers()

        def _form(self) -> dict[str, list[str]]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as error:
                raise ValueError("invalid content length") from error
            if length < 0 or length > MAX_TASK_BYTES + 4096:
                raise ValueError("request is too large")
            body = self.rfile.read(length).decode("utf-8")
            return parse_qs(body, keep_blank_values=True)

        def do_GET(self) -> None:  # noqa: N802
            if not self._require_authentication():
                return
            if self.path != "/":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            status = _read_status(resolved_root)
            task = normalized_task(resolved_root / "tasks" / "current.md")
            plan_path = resolved_root / "state" / "latest-plan.md"
            plan = plan_path.read_text(encoding="utf-8") if plan_path.exists() else "No plan yet."
            status_json = html.escape(json.dumps(status, indent=2, sort_keys=True))
            task_text = html.escape(task)
            plan_text = html.escape(plan)
            page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>DenOps AI Builder</title><style>
body{{font:16px system-ui;max-width:900px;margin:3rem auto;padding:0 1rem;background:#101318;color:#e8edf2}}
h1{{color:#78dce8}} section{{background:#1a2028;padding:1rem;margin:1rem 0;border-radius:.6rem}}
textarea{{box-sizing:border-box;width:100%;min-height:14rem;background:#0c0f13;color:#fff;padding:.8rem}}
pre{{white-space:pre-wrap}} button{{padding:.65rem 1rem;margin:.5rem .5rem 0 0}}
.warn{{color:#ffd866}}
</style></head><body><h1>DenOps AI Builder</h1>
<p class="warn">Planning only. OpenAI cannot edit files or execute commands. Manual limit: one test call per UTC day, capped at 800 output tokens.</p>
<section><h2>Status</h2><pre>{status_json}</pre><form method="post" action="/run"><button>Run readiness check</button></form>
<form method="post" action="/analyze"><button>Use one OpenAI test call</button></form></section>
<section><h2>Single task</h2><form method="post" action="/task"><textarea name="task">{task_text}</textarea><br><button>Save task</button></form>
<form method="post" action="/clear"><button>Clear task</button></form></section>
<section><h2>Latest implementation plan</h2><pre>{plan_text}</pre></section>
</body></html>"""
            payload = page.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self._security_headers()
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self) -> None:  # noqa: N802
            if not self._require_authentication():
                return
            try:
                if self.path == "/task":
                    form = self._form()
                    write_task(resolved_root / "tasks" / "current.md", form.get("task", [""])[0])
                elif self.path == "/clear":
                    write_task(resolved_root / "tasks" / "current.md", "")
                elif self.path == "/run":
                    run_once(resolved_root)
                elif self.path == "/analyze":
                    analyze_task(resolved_root)
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
            except (OSError, RuntimeError, UnicodeDecodeError, ValueError) as error:
                self.send_error(HTTPStatus.BAD_REQUEST, str(error))
                return
            self._redirect_home()

        def log_message(self, format: str, *args: object) -> None:
            super().log_message(format, *args)

    return BuilderHandler


def serve(root: Path, host: str, port: int, password: str) -> None:
    if not password:
        raise ValueError("DENOPS_AI_ADMIN_PASSWORD is required")
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    server = ThreadingHTTPServer((host, port), handler_for(root, password))
    print(f"DenOps AI Builder listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
