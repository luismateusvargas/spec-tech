"""Native validator aggregation, profile contracts, staging, and Docker runner behavior."""

from __future__ import annotations

import logging
import os
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest
from conftest import ScriptedRunner
from pydantic import ValidationError

from sdd_engine.models import CommandResult, Target
from sdd_engine.targets import TARGETS, standard_commands
from sdd_engine.validation import (
    CommandSpec,
    DockerCommandRunner,
    NativeValidator,
    ValidationInfrastructureError,
    ValidationProfile,
    stage_worktree,
)

ROOT = Path(__file__).resolve().parents[1]
REAL_RUN = subprocess.run
ROOTLESS_INFO = b'["name=seccomp,profile=builtin","name=rootless","name=cgroupns"]\n'
ROOTFUL_INFO = b'["name=seccomp,profile=builtin","name=cgroupns"]\n'
DIGEST = "0123456789abcdef" * 4
Call = tuple[tuple[str, ...], dict[str, Any]]

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


def test_validator_logs_each_command_without_its_output(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    runner = ScriptedRunner(
        [CommandResult(command_name="first", exit_code=2, stdout="command-output-marker")]
    )
    caplog.set_level(logging.INFO, logger="sdd_engine")

    NativeValidator({Target.GO: PROFILE}, runner).validate(Target.GO, tmp_path)

    [record] = caplog.records
    fields = vars(record)
    assert (fields["command_name"], fields["exit_code"], fields["timed_out"]) == ("first", 2, False)
    assert fields["target"] == "go"
    assert isinstance(fields["duration_ms"], int)
    assert "command-output-marker" not in str(fields)


def test_validator_logs_a_command_that_cannot_run(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    runner = ScriptedRunner([ValidationInfrastructureError("daemon unavailable")])
    caplog.set_level(logging.INFO, logger="sdd_engine")

    with pytest.raises(ValidationInfrastructureError):
        NativeValidator({Target.GO: PROFILE}, runner).validate(Target.GO, tmp_path)

    [record] = caplog.records
    assert record.levelno == logging.WARNING
    assert vars(record)["command_name"] == "first"


def test_profile_output_limit_cannot_exceed_command_result_cap() -> None:
    with pytest.raises(ValidationError):
        ValidationProfile(image="i", commands=PROFILE.commands, max_output_bytes=16_001)


@pytest.mark.parametrize(
    "image",
    [
        "i",
        "busybox:1.37",
        "golang:1.26-alpine",
        "sdd-engine-test/missing:never",
        "ghcr.io/org/team/image:1.2.3",
        "localhost:5000/team/image:dev",
        f"python:3.12.12-slim-bookworm@sha256:{DIGEST}",
        f"sha256:{DIGEST}",
    ],
)
def test_profile_accepts_image_references(image: str) -> None:
    profile = ValidationProfile(image=image, commands=PROFILE.commands)

    assert profile.image == image


@pytest.mark.parametrize(
    "overrides",
    [
        {"image": "--privileged"},
        {"image": "-v/:/host"},
        {"image": "busybox:1.37 --privileged"},
        {"image": "busybox:1.37\n"},
        {"image": "Busybox"},
        {"image": "busybox@sha256:short"},
        {"memory_limit": "lots"},
        {"memory_limit": "0g"},
        {"memory_limit": "4g,--privileged"},
    ],
)
def test_profile_rejects_option_shaped_and_malformed_fields(overrides: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        ValidationProfile.model_validate(
            {"image": "busybox:1.37", "commands": PROFILE.commands, **overrides}
        )


@pytest.mark.parametrize("name", ["", "x" * 129, "-flag", "two words", "semi;colon"])
def test_command_names_are_bounded_identifiers(name: str) -> None:
    with pytest.raises(ValidationError):
        CommandSpec(name=name, argv=("true",))


def test_command_name_limit_matches_command_results() -> None:
    name = "x" * 128

    CommandSpec(name=name, argv=("true",))
    CommandResult(command_name=name, exit_code=0)


def test_profile_digest_tracks_the_profile_content() -> None:
    same = ValidationProfile(image="toolchain:pinned", commands=PROFILE.commands)
    changed = ValidationProfile(image="toolchain:other", commands=PROFILE.commands)

    assert PROFILE.digest() == same.digest()
    assert PROFILE.digest() != changed.digest()
    assert len(PROFILE.digest()) == 64


def tree(root: Path) -> dict[str, str]:
    """Map each path under `root` to its file content or symlink target."""
    entries: dict[str, str] = {}
    for directory, names, files in os.walk(root):
        for name in (*names, *files):
            path = Path(directory) / name
            key = path.relative_to(root).as_posix()
            if path.is_symlink():
                entries[key] = f"-> {os.readlink(path)}"
            elif path.is_file():
                entries[key] = path.read_text(encoding="utf-8")
            else:
                entries[key] = "/"
    return entries


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    """Create a worktree with Git metadata, nested files, and a symlink."""
    root = tmp_path / "worktree"
    (root / ".git" / "hooks").mkdir(parents=True)
    (root / ".git" / "spec-tech").mkdir()
    (root / ".git" / "spec-tech" / "engine.db").write_text("db", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / ".gitignore").write_text("build/\n", encoding="utf-8")
    (root / "link.py").symlink_to("src/module.py")
    return root


EXPECTED_STAGE = {
    ".gitignore": "build/\n",
    "link.py": "-> src/module.py",
    "src": "/",
    "src/module.py": "VALUE = 1\n",
}


def test_stage_worktree_copies_everything_but_git(worktree: Path, tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()

    stage_worktree(worktree, staging)

    assert tree(staging) == EXPECTED_STAGE


def test_stage_worktree_skips_a_linked_worktree_pointer(tmp_path: Path) -> None:
    root = tmp_path / "linked"
    root.mkdir()
    (root / ".git").write_text("gitdir: /repo/.git/worktrees/linked\n", encoding="utf-8")
    (root / "main.go").write_text("package main\n", encoding="utf-8")
    staging = tmp_path / "staging"
    staging.mkdir()

    stage_worktree(root, staging)

    assert tree(staging) == {"main.go": "package main\n"}


def unusable_cp(error: bool) -> Any:
    """Make `cp` missing, or reject its options the way BSD and busybox cp do."""

    def run(argv: tuple[str, ...], **kwargs: Any) -> Any:
        if argv[0] != "cp":
            return REAL_RUN(argv, **kwargs)
        if error:
            raise FileNotFoundError(2, "No such file or directory", "cp")
        return subprocess.CompletedProcess(argv, 1, b"", b"cp: illegal option -- -")

    return run


@pytest.mark.parametrize("missing", [True, False])
def test_stage_worktree_falls_back_when_cp_is_unusable(
    monkeypatch: pytest.MonkeyPatch, worktree: Path, tmp_path: Path, missing: bool
) -> None:
    monkeypatch.setattr(subprocess, "run", unusable_cp(missing))
    staging = tmp_path / "staging"
    staging.mkdir()

    stage_worktree(worktree, staging)

    assert tree(staging) == EXPECTED_STAGE


def test_stage_worktree_reports_a_partial_copy(
    monkeypatch: pytest.MonkeyPatch, worktree: Path, tmp_path: Path
) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()

    def partial(argv: tuple[str, ...], **kwargs: Any) -> Any:
        (staging / ".gitignore").write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 1, b"", b"cp: cannot open 'secret'")

    monkeypatch.setattr(subprocess, "run", partial)

    with pytest.raises(ValidationInfrastructureError, match="cannot open 'secret'"):
        stage_worktree(worktree, staging)


def fake_docker(
    calls: list[Call] | None = None,
    returncode: int = 0,
    stdout: bytes = b"",
    stderr: bytes = b"",
    info: bytes = ROOTLESS_INFO,
) -> Any:
    """Answer docker calls with fixed results and run every other command for real."""

    def run(argv: tuple[str, ...], **kwargs: Any) -> Any:
        if argv[0] != "docker":
            return REAL_RUN(argv, **kwargs)
        if calls is not None:
            calls.append((argv, kwargs))
        if argv[1] == "info":
            return subprocess.CompletedProcess(argv, 0, info, b"")
        return subprocess.CompletedProcess(argv, returncode, stdout, stderr)

    return run


def docker_runs(calls: list[Call]) -> list[tuple[str, ...]]:
    return [argv for argv, _ in calls if argv[1] == "run"]


def mount_source(argv: tuple[str, ...]) -> Path:
    mount = argv[argv.index("--mount") + 1]
    fields = dict(field.split("=", 1) for field in mount.split(","))
    assert fields["type"] == "bind"
    assert fields["dst"] == "/workspace"
    return Path(fields["src"])


def test_docker_runner_returns_tool_failures_as_results(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(subprocess, "run", fake_docker(returncode=1, stdout=b"x" * 40_000))

    result = DockerCommandRunner().run(PROFILE.commands[0], tmp_path, PROFILE)

    assert result.exit_code == 1
    assert len(result.stdout) == PROFILE.max_output_bytes


@pytest.mark.parametrize("returncode", [125, 126, 127])
def test_docker_runner_raises_for_docker_exit_codes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, returncode: int
) -> None:
    monkeypatch.setattr(
        subprocess, "run", fake_docker(returncode=returncode, stderr=b"no such image")
    )

    with pytest.raises(ValidationInfrastructureError, match="no such image"):
        DockerCommandRunner().run(PROFILE.commands[0], tmp_path, PROFILE)


@pytest.mark.parametrize("user", [None, "1000:1000"])
def test_docker_runner_raises_when_docker_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, user: str | None
) -> None:
    def missing(argv: tuple[str, ...], **kwargs: Any) -> Any:
        if argv[0] != "docker":
            return REAL_RUN(argv, **kwargs)
        raise FileNotFoundError(2, "No such file or directory", "docker")

    monkeypatch.setattr(subprocess, "run", missing)

    with pytest.raises(ValidationInfrastructureError, match="could not start docker"):
        DockerCommandRunner(user=user).run(PROFILE.commands[0], tmp_path, PROFILE)


def test_docker_runner_raises_when_the_daemon_cannot_be_queried(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def daemon_down(argv: tuple[str, ...], **kwargs: Any) -> Any:
        return subprocess.CompletedProcess(argv, 1, b"", b"Cannot connect to the Docker daemon")

    monkeypatch.setattr(subprocess, "run", daemon_down)

    with pytest.raises(ValidationInfrastructureError, match="Cannot connect"):
        DockerCommandRunner().run(PROFILE.commands[0], tmp_path, PROFILE)


def test_docker_runner_reports_timeouts_and_removes_the_container(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, ...]] = []

    def timeout(argv: tuple[str, ...], **kwargs: Any) -> Any:
        if argv[1] == "info":
            return subprocess.CompletedProcess(argv, 0, ROOTLESS_INFO, b"")
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


def test_docker_runner_passes_only_allowlisted_client_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[Call] = []
    monkeypatch.setattr(subprocess, "run", fake_docker(calls))
    monkeypatch.setenv("DOCKER_HOST", "unix:///run/user/1000/docker.sock")
    monkeypatch.setenv("HOME", "/home/user")
    monkeypatch.setenv("API_TOKEN", "secret")
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)

    DockerCommandRunner().run(PROFILE.commands[0], tmp_path, PROFILE)

    assert [argv[1] for argv, _ in calls] == ["info", "run"]
    for _, kwargs in calls:
        environment = kwargs["env"]
        assert environment["DOCKER_HOST"] == "unix:///run/user/1000/docker.sock"
        assert environment["HOME"] == "/home/user"
        assert "API_TOKEN" not in environment
        assert "DOCKER_CONTEXT" not in environment


def test_docker_runner_sandbox_options(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[Call] = []
    monkeypatch.setattr(subprocess, "run", fake_docker(calls))

    DockerCommandRunner().run(PROFILE.commands[0], tmp_path, PROFILE)

    (argv,) = docker_runs(calls)
    assert "--pull=never" in argv
    assert "--user" not in argv
    assert argv[argv.index("--tmpfs") + 1].startswith("/tmp:rw,exec,")
    assert argv[argv.index("--env") + 1] == "HOME=/tmp"
    assert argv[-3:] == ("--", "toolchain:pinned", "first")


def test_docker_runner_mounts_a_disposable_copy_without_git(
    monkeypatch: pytest.MonkeyPatch, worktree: Path
) -> None:
    calls: list[Call] = []
    staged: dict[str, str] = {}
    run_docker = fake_docker(calls)

    def inspect(argv: tuple[str, ...], **kwargs: Any) -> Any:
        if argv[:2] == ("docker", "run"):
            staged.update(tree(mount_source(argv)))
        return run_docker(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", inspect)

    DockerCommandRunner().run(PROFILE.commands[0], worktree, PROFILE)

    (argv,) = docker_runs(calls)
    source = mount_source(argv)
    assert source.name.startswith("sdd-validate-")
    assert not source.is_relative_to(worktree)
    assert not source.exists()
    assert staged == EXPECTED_STAGE


def test_validator_shares_one_staged_copy_across_its_commands(
    monkeypatch: pytest.MonkeyPatch, worktree: Path
) -> None:
    calls: list[Call] = []
    monkeypatch.setattr(subprocess, "run", fake_docker(calls))
    validator = NativeValidator({Target.GO: PROFILE}, DockerCommandRunner())

    validator.validate(Target.GO, worktree)
    validator.validate(Target.GO, worktree)

    sources = [mount_source(argv) for argv in docker_runs(calls)]
    assert len(sources) == 4
    assert sources[0] == sources[1]
    assert sources[2] == sources[3]
    assert sources[0] != sources[2]


def test_docker_runner_sets_the_configured_user_without_detection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[Call] = []
    monkeypatch.setattr(subprocess, "run", fake_docker(calls))

    DockerCommandRunner(user="1000:1000").run(PROFILE.commands[0], tmp_path, PROFILE)

    (argv,) = docker_runs(calls)
    assert argv[argv.index("--user") + 1] == "1000:1000"
    assert [argv[1] for argv, _ in calls] == ["run"]


def test_docker_runner_uses_the_host_user_for_a_rootful_daemon(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[Call] = []
    monkeypatch.setattr(subprocess, "run", fake_docker(calls, info=ROOTFUL_INFO))
    runner = DockerCommandRunner()

    runner.run(PROFILE.commands[0], tmp_path, PROFILE)
    runner.run(PROFILE.commands[1], tmp_path, PROFILE)

    expected = f"{os.getuid()}:{os.getgid()}"
    assert [argv[argv.index("--user") + 1] for argv in docker_runs(calls)] == [expected] * 2
    assert [argv[1] for argv, _ in calls] == ["info", "run", "run"]


def test_standard_typescript_commands_add_prisma_when_schema_exists(tmp_path: Path) -> None:
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "schema.prisma").write_text("", encoding="utf-8")

    names = [command.name for command in standard_commands(Target.PRISMA_TYPESCRIPT, tmp_path)]

    assert names == ["tsc-no-emit", "prisma-validate", "npm-test"]


def test_standard_python_commands_keep_the_workspace_off_tool_imports(tmp_path: Path) -> None:
    argvs = {command.name: command.argv for command in standard_commands(Target.PYTHON, tmp_path)}

    assert argvs["ruff-check"] == ("python", "-P", "-m", "ruff", "check", ".")
    assert argvs["mypy-strict"] == ("python", "-P", "-m", "mypy", "--strict", ".")


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


def test_target_registry_covers_every_target_with_packaged_skills() -> None:
    skills = {skill for spec in TARGETS.values() for skill in spec.skills}
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    packaged = {Path(entry).name for entry in pyproject["tool"]["setuptools"]["data-files"]}

    assert set(TARGETS) == set(Target)
    assert [
        skill for skill in sorted(skills) if not (ROOT / "skills" / skill / "SKILL.md").is_file()
    ] == []
    assert packaged == skills


def test_engine_protocol_names_every_target() -> None:
    protocol = ROOT / "skills" / "sdd-shared" / "templates" / "engine-protocol.md"
    text = protocol.read_text(encoding="utf-8")

    assert [target.value for target in Target if f"`{target.value}`" not in text] == []
