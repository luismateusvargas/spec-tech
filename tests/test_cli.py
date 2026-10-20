"""JSON CLI command routing between the implementer and administrator interfaces."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from sdd_engine.cli import main
from sdd_engine.validation import CommandSpec, ValidationProfile

PROFILE = ValidationProfile(
    image="busybox:1.37", commands=(CommandSpec(name="check", argv=("true",)),)
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a Git worktree that can hold the engine database."""
    subprocess.run(("git", "init", "-q", str(tmp_path)), check=True, capture_output=True)
    return tmp_path


def run_cli(monkeypatch: pytest.MonkeyPatch, payload: dict[str, object], *argv: str) -> None:
    monkeypatch.setattr(sys, "argv", ["sdd_engine.cli", *argv])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    main()


def profile_request(workspace: Path) -> dict[str, object]:
    return {
        "workspace": str(workspace),
        "target": "python",
        "profile": PROFILE.model_dump(mode="json"),
    }


def test_configure_profile_requires_admin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], workspace: Path
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        run_cli(monkeypatch, profile_request(workspace), "configure_profile")

    assert exit_info.value.code == 2
    assert "configure_profile requires --admin" in capsys.readouterr().err


def test_admin_configures_and_reads_a_profile(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], workspace: Path
) -> None:
    run_cli(monkeypatch, profile_request(workspace), "--admin", "configure_profile")
    configured = json.loads(capsys.readouterr().out)
    run_cli(
        monkeypatch, {"workspace": str(workspace), "target": "python"}, "--admin", "get_profile"
    )
    stored = json.loads(capsys.readouterr().out)

    assert configured == {"target": "python", "revision": 1}
    assert stored == PROFILE.model_dump(mode="json")


def test_admin_cannot_run_task_commands(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], workspace: Path
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        run_cli(monkeypatch, {"workspace": str(workspace)}, "--admin", "begin_task")

    assert exit_info.value.code == 2
    assert "begin_task is not an administrator command" in capsys.readouterr().err
