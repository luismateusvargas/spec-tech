"""Real-container checks for `DockerCommandRunner`; skipped without a daemon or image."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from sdd_engine.models import Target
from sdd_engine.validation import (
    CommandSpec,
    DockerCommandRunner,
    NativeValidator,
    ValidationInfrastructureError,
    ValidationProfile,
    standard_commands,
)

pytestmark = pytest.mark.docker

BUSYBOX_IMAGE = "busybox:1.37"
GO_IMAGE = "golang:1.26-alpine"
MISSING_IMAGE = "sdd-engine-test/missing:never"


def _docker(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(("docker", *args), check=False, capture_output=True, timeout=30)


def require_image(image: str) -> None:
    """Skip the test unless the daemon answers and the image is already pulled."""
    try:
        if _docker("info").returncode != 0:
            pytest.skip("docker daemon is unavailable")
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("docker client is unavailable")
    if _docker("image", "inspect", image).returncode != 0:
        pytest.skip(f"{image} is not pulled")


def busybox_profile(*argv: str, timeout_seconds: int = 60) -> ValidationProfile:
    return ValidationProfile(
        image=BUSYBOX_IMAGE,
        commands=(CommandSpec(name="busybox", argv=argv),),
        timeout_seconds=timeout_seconds,
    )


def test_timeout_removes_the_container(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    require_image(BUSYBOX_IMAGE)
    names: list[str] = []
    real_run = subprocess.run

    def spy(argv: tuple[str, ...], **kwargs: Any) -> Any:
        if argv[1] == "run":
            names.append(argv[argv.index("--name") + 1])
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    profile = busybox_profile("sleep", "60", timeout_seconds=2)

    result = DockerCommandRunner().run(profile.commands[0], tmp_path, profile)

    monkeypatch.undo()
    assert result.timed_out
    assert _docker("container", "inspect", names[0]).returncode != 0


def test_staged_writes_are_owned_by_the_host_user(tmp_path: Path) -> None:
    require_image(BUSYBOX_IMAGE)
    profile = busybox_profile("touch", "written")
    runner = DockerCommandRunner()

    with runner.staged(tmp_path) as staging:
        result = runner.run(profile.commands[0], tmp_path, profile)
        owner = (staging / "written").stat().st_uid

    assert result.exit_code == 0, result.stderr
    assert owner == os.getuid()
    assert not (tmp_path / "written").exists()


def test_container_cannot_see_or_write_the_git_directory(tmp_path: Path) -> None:
    require_image(BUSYBOX_IMAGE)
    subprocess.run(("git", "init", "-q", str(tmp_path)), check=True, capture_output=True)
    database = tmp_path / ".git" / "spec-tech" / "engine.db"
    database.parent.mkdir()
    database.write_bytes(b"engine")
    (tmp_path / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    profile = busybox_profile(
        "sh",
        "-c",
        "test -f module.py && test ! -e .git && mkdir -p .git/hooks"
        " && echo hook > .git/hooks/pre-commit && echo changed > module.py",
    )

    result = DockerCommandRunner().run(profile.commands[0], tmp_path, profile)

    assert result.exit_code == 0, result.stderr
    assert not (tmp_path / ".git" / "hooks" / "pre-commit").exists()
    assert database.read_bytes() == b"engine"
    assert (tmp_path / "module.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_profile_commands_share_one_staged_workspace(tmp_path: Path) -> None:
    require_image(BUSYBOX_IMAGE)
    profile = ValidationProfile(
        image=BUSYBOX_IMAGE,
        commands=(
            CommandSpec(name="build", argv=("sh", "-c", "mkdir build && touch build/output")),
            CommandSpec(name="test", argv=("test", "-f", "build/output")),
        ),
        timeout_seconds=60,
    )

    report = NativeValidator({Target.GO: profile}, DockerCommandRunner()).validate(
        Target.GO, tmp_path
    )

    assert report.passed, [(result.command_name, result.stderr) for result in report.commands]
    assert not (tmp_path / "build").exists()


def test_go_profile_passes_on_a_small_module(tmp_path: Path) -> None:
    require_image(GO_IMAGE)
    (tmp_path / "go.mod").write_text("module example.com/m\n\ngo 1.26\n", encoding="utf-8")
    (tmp_path / "m.go").write_text(
        "package m\n\nfunc Add(a, b int) int { return a + b }\n", encoding="utf-8"
    )
    (tmp_path / "m_test.go").write_text(
        'package m\n\nimport "testing"\n\n'
        "func TestAdd(t *testing.T) {\n\tif Add(1, 2) != 3 {\n\t\tt.Fatal()\n\t}\n}\n",
        encoding="utf-8",
    )
    profile = ValidationProfile(
        image=GO_IMAGE, commands=standard_commands(Target.GO, tmp_path), timeout_seconds=300
    )

    report = NativeValidator({Target.GO: profile}, DockerCommandRunner()).validate(
        Target.GO, tmp_path
    )

    assert report.passed, [(result.command_name, result.stderr) for result in report.commands]


def test_missing_image_is_an_infrastructure_error(tmp_path: Path) -> None:
    require_image(BUSYBOX_IMAGE)
    if _docker("image", "inspect", MISSING_IMAGE).returncode == 0:
        pytest.skip(f"{MISSING_IMAGE} unexpectedly exists")
    profile = ValidationProfile(
        image=MISSING_IMAGE, commands=(CommandSpec(name="true", argv=("true",)),)
    )

    with pytest.raises(ValidationInfrastructureError, match="exit 125"):
        DockerCommandRunner().run(profile.commands[0], tmp_path, profile)
