"""Native validator aggregation and Docker runner failure classification."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from conftest import ScriptedRunner
from pydantic import ValidationError

from sdd_engine.models import CommandResult, Target
from sdd_engine.validation import (
    CommandSpec,
    DockerCommandRunner,
    NativeValidator,
    ValidationInfrastructureError,
    ValidationProfile,
    standard_commands,
)

PROFILE = ValidationProfile(
    image="toolchain:pinned",
    commands=(
        CommandSpec(name="first", argv=("first",)),
        CommandSpec(name="second", argv=("second",)),
    ),
)


def test_validator_stops_after_first_failure(tmp_path: Path) -> None:
    runner = ScriptedRunner([CommandResult(command_name="first", exit_code=2)])

    report = NativeValidator({Target.GO: PROFILE}, runner).validate(Target.GO, tmp_path)

    assert not report.passed
    assert runner.calls == ["first"]


def test_validator_passes_when_all_commands_pass(tmp_path: Path) -> None:
    runner = ScriptedRunner()

    report = NativeValidator({Target.GO: PROFILE}, runner).validate(Target.GO, tmp_path)

    assert report.passed
    assert runner.calls == ["first", "second"]


def test_validator_without_profile_is_an_infrastructure_error(tmp_path: Path) -> None:
    with pytest.raises(ValidationInfrastructureError, match="no native validation profile"):
        NativeValidator({}, ScriptedRunner()).validate(Target.GO, tmp_path)


def test_profile_output_limit_cannot_exceed_command_result_cap() -> None:
    with pytest.raises(ValidationError):
        ValidationProfile(image="i", commands=PROFILE.commands, max_output_bytes=16_001)


def fake_completed(returncode: int, stdout: bytes = b"", stderr: bytes = b"") -> Any:
    def run(argv: tuple[str, ...], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(argv, returncode, stdout, stderr)

    return run


def test_docker_runner_returns_tool_failures_as_results(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(subprocess, "run", fake_completed(1, stdout=b"x" * 40_000))

    result = DockerCommandRunner().run(PROFILE.commands[0], tmp_path, PROFILE)

    assert result.exit_code == 1
    assert len(result.stdout) == PROFILE.max_output_bytes


@pytest.mark.parametrize("returncode", [125, 126, 127])
def test_docker_runner_raises_for_docker_exit_codes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, returncode: int
) -> None:
    monkeypatch.setattr(subprocess, "run", fake_completed(returncode, stderr=b"no such image"))

    with pytest.raises(ValidationInfrastructureError, match="no such image"):
        DockerCommandRunner().run(PROFILE.commands[0], tmp_path, PROFILE)


def test_docker_runner_raises_when_docker_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def missing(argv: tuple[str, ...], **kwargs: Any) -> None:
        raise FileNotFoundError(2, "No such file or directory", "docker")

    monkeypatch.setattr(subprocess, "run", missing)

    with pytest.raises(ValidationInfrastructureError, match="could not start docker"):
        DockerCommandRunner().run(PROFILE.commands[0], tmp_path, PROFILE)


def test_docker_runner_reports_timeouts_and_removes_the_container(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, ...]] = []

    def timeout(argv: tuple[str, ...], **kwargs: Any) -> Any:
        calls.append(argv)
        if argv[1] == "run":
            raise subprocess.TimeoutExpired(argv, 1, output=b"partial")
        raise subprocess.TimeoutExpired(argv, 1)

    monkeypatch.setattr(subprocess, "run", timeout)

    result = DockerCommandRunner().run(PROFILE.commands[0], tmp_path, PROFILE)

    assert result.timed_out
    assert result.stdout == "partial"
    container_name = calls[0][calls[0].index("--name") + 1]
    assert calls[1] == ("docker", "rm", "--force", container_name)


def recording_run(calls: list[tuple[tuple[str, ...], dict[str, Any]]]) -> Any:
    def run(argv: tuple[str, ...], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    return run


def test_docker_runner_passes_only_allowlisted_client_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[tuple[str, ...], dict[str, Any]]] = []
    monkeypatch.setattr(subprocess, "run", recording_run(calls))
    monkeypatch.setenv("DOCKER_HOST", "unix:///run/user/1000/docker.sock")
    monkeypatch.setenv("HOME", "/home/user")
    monkeypatch.setenv("API_TOKEN", "secret")
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)

    DockerCommandRunner().run(PROFILE.commands[0], tmp_path, PROFILE)

    environment = calls[0][1]["env"]
    assert environment["DOCKER_HOST"] == "unix:///run/user/1000/docker.sock"
    assert environment["HOME"] == "/home/user"
    assert "API_TOKEN" not in environment
    assert "DOCKER_CONTEXT" not in environment


def test_docker_runner_sandbox_options(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple[tuple[str, ...], dict[str, Any]]] = []
    monkeypatch.setattr(subprocess, "run", recording_run(calls))

    DockerCommandRunner().run(PROFILE.commands[0], tmp_path, PROFILE)

    argv = calls[0][0]
    assert "--pull=never" in argv
    assert "--user" not in argv
    assert argv[argv.index("--tmpfs") + 1].startswith("/tmp:rw,exec,")
    assert argv[argv.index("--env") + 1] == "HOME=/tmp"
    assert argv[-2:] == ("toolchain:pinned", "first")


def test_docker_runner_sets_user_only_when_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[tuple[str, ...], dict[str, Any]]] = []
    monkeypatch.setattr(subprocess, "run", recording_run(calls))

    DockerCommandRunner(user="1000:1000").run(PROFILE.commands[0], tmp_path, PROFILE)

    argv = calls[0][0]
    assert argv[argv.index("--user") + 1] == "1000:1000"


def test_standard_typescript_commands_add_prisma_when_schema_exists(tmp_path: Path) -> None:
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "schema.prisma").write_text("", encoding="utf-8")

    names = [command.name for command in standard_commands(Target.PRISMA_TYPESCRIPT, tmp_path)]

    assert names == ["tsc-no-emit", "prisma-validate", "npm-test"]


@pytest.mark.parametrize(
    ("target", "test_command"),
    [
        (Target.PYTHON, "pytest"),
        (Target.SQLALCHEMY_ALEMBIC, "pytest"),
        (Target.RUST, "cargo-test"),
        (Target.DIESEL, "cargo-test"),
        (Target.GO, "go-test"),
        (Target.CPP, "ctest"),
        (Target.TYPESCRIPT, "npm-test"),
        (Target.REACT_JAVASCRIPT, "npm-test"),
        (Target.PRISMA_JAVASCRIPT, "npm-test"),
    ],
)
def test_standard_profiles_end_with_the_test_suite(
    target: Target, test_command: str, tmp_path: Path
) -> None:
    assert standard_commands(target, tmp_path)[-1].name == test_command


@pytest.mark.parametrize("target", [Target.MYSQL, Target.POSTGRESQL])
def test_database_targets_require_explicit_profiles(target: Target, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="disposable-database"):
        standard_commands(target, tmp_path)
