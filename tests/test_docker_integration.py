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


def test_workspace_writes_are_owned_by_the_host_user(tmp_path: Path) -> None:
    require_image(BUSYBOX_IMAGE)
    profile = busybox_profile("touch", "written")

    result = DockerCommandRunner().run(profile.commands[0], tmp_path, profile)

    assert result.exit_code == 0, result.stderr
    assert (tmp_path / "written").stat().st_uid == os.getuid()


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
