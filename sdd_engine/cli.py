"""Small JSON CLI over the same task and configuration service as MCP."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sdd_engine import service


def main() -> None:
    """Dispatch a JSON request from a file or standard input."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "begin_task",
            "submit",
            "finish_task",
            "get_run_report",
            "configure_profile",
            "get_profile",
        ),
    )
    parser.add_argument("--input", type=Path, help="JSON request file; defaults to standard input")
    arguments = parser.parse_args()
    source = arguments.input.read_text(encoding="utf-8") if arguments.input else sys.stdin.read()
    payload = json.loads(source)
    if not isinstance(payload, dict):
        parser.error("input must be a JSON object")
    operation = getattr(service, arguments.command)
    print(json.dumps(operation(**payload), indent=2))


if __name__ == "__main__":
    main()
