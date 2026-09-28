from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .runner import run_once
from .web import serve


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Run one DenOps AI builder check")
    result.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="DenOpsAI repository root (default: current directory)",
    )
    result.add_argument(
        "--serve", action="store_true", help="start the administrative web interface"
    )
    result.add_argument("--host", default="127.0.0.1", help="web listen address")
    result.add_argument("--port", default=8080, type=int, help="web listen port")
    return result


def main() -> int:
    arguments = parser().parse_args()
    if arguments.serve:
        password = os.environ.get("DENOPS_AI_ADMIN_PASSWORD", "")
        try:
            serve(arguments.root, arguments.host, arguments.port, password)
        except (OSError, RuntimeError, ValueError) as error:
            print(json.dumps({"stage": "error", "reason": str(error)}, sort_keys=True))
            return 2
        return 0
    try:
        status = run_once(arguments.root)
    except (OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"stage": "error", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(status.to_dict(), sort_keys=True))
    return 0 if status.stage in {"idle", "ready"} else 1
