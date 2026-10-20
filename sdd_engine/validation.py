"""Hardened Docker execution and native compiler/static-analysis profiles."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Annotated, Protocol

from pydantic import Field, model_validator

from sdd_engine.limits import MAX_COMMAND_NAME_CHARS, MAX_DIAGNOSTIC_CHARS
from sdd_engine.models import (
    CommandResult,
    JsonTuple,
    StrictModel,
    Target,
    ValidationReport,
)

# Exit codes that `docker run` reserves for its own failures: daemon or option errors, a
# command that cannot be invoked, and a command missing from the image.
DOCKER_INFRASTRUCTURE_EXIT_CODES = frozenset({125, 126, 127})

# Client settings the docker CLI needs to reach the daemon, such as a rootless daemon's socket.
# Everything else in the host environment stays out of the subprocess.
DOCKER_CLIENT_ENVIRONMENT = (
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "DOCKER_CONFIG",
    "DOCKER_CERT_PATH",
    "DOCKER_TLS_VERIFY",
    "XDG_RUNTIME_DIR",
    "HOME",
)

# Bounds `docker info`, which the runner calls once to detect a rootless daemon.
DOCKER_QUERY_TIMEOUT_SECONDS = 30.0

# Command names become `CommandResult.command_name` and appear in reports.
CommandName = Annotated[
    str,
    Field(
        min_length=1,
        max_length=MAX_COMMAND_NAME_CHARS,
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$",
    ),
]

# An image ID, or a name with an optional registry host and port, tag, and digest. The
# leading alphanumeric keeps option-shaped values such as `--privileged` out of `docker run`.
ImageRef = Annotated[
    str,
    Field(
        min_length=1,
        max_length=255,
        pattern=(
            r"^(?:sha256:[0-9a-f]{64}"
            r"|(?:[a-z0-9][a-z0-9.-]*:[0-9]+/)?[a-z0-9][a-z0-9._/-]*"
            r"(?::[a-zA-Z0-9_.-]+)?(?:@sha256:[0-9a-f]{64})?)$"
        ),
    ),
]

# A `docker run --memory` value with an explicit unit.
MemoryLimit = Annotated[str, Field(pattern=r"^[1-9][0-9]*[bkmgBKMG]$")]


class ValidationInfrastructureError(RuntimeError):
    """Raised when native checks cannot run, as opposed to running and failing."""


class CommandSpec(StrictModel):
    """One fixed argument-vector command from trusted deployment configuration."""

    name: CommandName
    argv: JsonTuple[str]

    @model_validator(mode="after")
    def require_valid_argv(self) -> CommandSpec:
        """Require a nonempty argv vector without NUL bytes."""
        if not self.argv or not self.argv[0] or any("\x00" in arg for arg in self.argv):
            raise ValueError("command argv must contain a nonempty executable without NUL bytes")
        return self


# Runs the project's own test script, whichever runner it configures. npm fails when the
# script is missing, and `npm init` writes one that always fails.
NPM_TEST = CommandSpec(name="npm-test", argv=("npm", "test"))


class ValidationProfile(StrictModel):
    """Container image and resource bounds for one target's native checks."""

    image: ImageRef
    commands: JsonTuple[CommandSpec]
    timeout_seconds: int = Field(default=600, ge=1, le=3600)
    memory_limit: MemoryLimit = "4g"
    cpu_limit: float = Field(default=2.0, gt=0, le=64)
    process_limit: int = Field(default=256, ge=16, le=8192)
    # CommandResult caps stdout and stderr at 16,000 characters.
    max_output_bytes: int = Field(default=MAX_DIAGNOSTIC_CHARS, ge=1024, le=MAX_DIAGNOSTIC_CHARS)

    @model_validator(mode="after")
    def require_commands(self) -> ValidationProfile:
        """Require at least one native check for every validation profile."""
        if not self.commands:
            raise ValueError("validation profiles must define at least one command")
        return self

    def digest(self) -> str:
        """Return the SHA-256 hex digest of the profile's JSON form."""
        return hashlib.sha256(self.model_dump_json().encode("utf-8")).hexdigest()


class CommandRunner(Protocol):
    """Executes configured commands within an isolated project workspace."""

    def staged(self, workspace: Path) -> AbstractContextManager[Path]:
        """Share one isolated copy of `workspace` across the `run` calls made in the block.

        # Errors

        Raises `ValidationInfrastructureError` when the copy cannot be made.
        """

    def run(
        self,
        command: CommandSpec,
        workspace: Path,
        profile: ValidationProfile,
    ) -> CommandResult:
        """Run one command and return a bounded structured result.

        # Errors

        Raises `ValidationInfrastructureError` when the command cannot be started.
        """


class DockerCommandRunner:
    """Runs native checks in disposable, network-isolated Docker containers."""

    def __init__(self, user: str | None = None, cleanup_timeout_seconds: float = 30.0) -> None:
        """Configure the container user and the bound on removing a timed-out container.

        # Arguments

        `user` is passed to `docker run --user`. Left unset, the runner asks the daemon once
        whether it is rootless. Rootless container root already maps to the host user, so
        only a rootful daemon gets the host UID and GID.
        """
        self._user = user
        self._user_resolved = user is not None
        self._cleanup_timeout_seconds = cleanup_timeout_seconds
        self._staging: dict[Path, Path] = {}

    @contextmanager
    def staged(self, workspace: Path) -> Iterator[Path]:
        """Mount one copy of `workspace`, without `.git`, for the `run` calls in the block.

        Commands of one validation pass share the copy, so build output from one step stays
        visible to the next. Container writes never reach the worktree or its Git directory.

        # Errors

        Raises `ValidationInfrastructureError` when the copy cannot be made.
        """
        root = workspace.resolve(strict=True)
        if root in self._staging:
            yield self._staging[root]
            return
        try:
            # Files written by a container user that the host cannot map back, such as an
            # image `USER` under rootless Docker, may be undeletable. A leftover copy must
            # not turn a finished validation into an error.
            directory = tempfile.TemporaryDirectory(
                prefix="sdd-validate-", ignore_cleanup_errors=True
            )
        except OSError as error:
            raise ValidationInfrastructureError(
                f"could not create a staging directory: {error}"
            ) from error
        with directory as name:
            staging = Path(name)
            # The path is interpolated into `--mount`, whose fields are comma-separated.
            if any(character in name for character in ',"'):
                raise ValidationInfrastructureError(
                    f"staging directory {name!r} cannot be passed to docker --mount"
                )
            stage_worktree(root, staging)
            self._staging[root] = staging
            try:
                yield staging
            finally:
                del self._staging[root]

    def run(
        self,
        command: CommandSpec,
        workspace: Path,
        profile: ValidationProfile,
    ) -> CommandResult:
        """Execute one argv command against the staged copy of `workspace`.

        Outside a `staged` block the command gets a fresh copy of its own.
        """
        staging = self._staging.get(workspace.resolve(strict=True))
        if staging is None:
            with self.staged(workspace) as staging:
                return self._run_staged(command, staging, profile)
        return self._run_staged(command, staging, profile)

    def _run_staged(
        self,
        command: CommandSpec,
        staging: Path,
        profile: ValidationProfile,
    ) -> CommandResult:
        """Execute one argv command with reduced container privileges and limits."""
        container_name = f"sdd-{uuid.uuid4().hex}"
        environment = _docker_client_environment()
        user_options = self._user_options(environment)
        docker_argv = (
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--pull=never",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            *user_options,
            "--pids-limit",
            str(profile.process_limit),
            "--memory",
            profile.memory_limit,
            "--cpus",
            str(profile.cpu_limit),
            # Toolchains such as Go build and run test binaries under their cache in HOME.
            "--tmpfs",
            "/tmp:rw,exec,nosuid,nodev,size=1g",
            "--env",
            "HOME=/tmp",
            "--mount",
            f"type=bind,src={staging},dst=/workspace",
            "--workdir",
            "/workspace",
            # Nothing after this separator is parsed as a `docker run` option.
            "--",
            profile.image,
            *command.argv,
        )
        try:
            completed = subprocess.run(
                docker_argv,
                cwd=staging,
                check=False,
                capture_output=True,
                timeout=profile.timeout_seconds,
                shell=False,
                env=environment,
            )
        except subprocess.TimeoutExpired as error:
            # Killing the client leaves the container running, so remove it by name.
            self._remove_container(container_name, environment)
            return CommandResult(
                command_name=command.name,
                exit_code=124,
                stdout=_decode_output(error.stdout, profile.max_output_bytes),
                stderr=_decode_output(error.stderr, profile.max_output_bytes),
                timed_out=True,
            )
        except OSError as error:
            raise ValidationInfrastructureError(
                f"could not start docker for {command.name}: {error}"
            ) from error
        if completed.returncode in DOCKER_INFRASTRUCTURE_EXIT_CODES:
            stderr = _decode_output(completed.stderr, profile.max_output_bytes)
            raise ValidationInfrastructureError(
                f"docker could not run {command.name} "
                f"(exit {completed.returncode}): {stderr[-2000:]}"
            )
        return CommandResult(
            command_name=command.name,
            exit_code=completed.returncode,
            stdout=_decode_output(completed.stdout, profile.max_output_bytes),
            stderr=_decode_output(completed.stderr, profile.max_output_bytes),
        )

    def _user_options(self, environment: dict[str, str]) -> tuple[str, ...]:
        """Return `--user` for a configured user or a rootful daemon, detected once."""
        if not self._user_resolved:
            if not _daemon_is_rootless(environment):
                self._user = f"{os.getuid()}:{os.getgid()}"
            self._user_resolved = True
        return () if self._user is None else ("--user", self._user)

    def _remove_container(self, name: str, environment: dict[str, str]) -> None:
        """Force-remove a container on a best-effort basis; the timeout result stands."""
        try:
            subprocess.run(
                ("docker", "rm", "--force", name),
                check=False,
                capture_output=True,
                timeout=self._cleanup_timeout_seconds,
                shell=False,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


class NativeValidator:
    """Runs all configured native checks and aggregates their result."""

    def __init__(
        self,
        profiles: dict[Target, ValidationProfile],
        runner: CommandRunner,
        profile_versions: dict[Target, tuple[int, str]] | None = None,
    ) -> None:
        """Bind trusted validation profiles to a sandboxed command runner."""
        self._profiles = profiles
        self._runner = runner
        self._profile_versions = profile_versions or {}

    def validate(self, target: Target, workspace: Path) -> ValidationReport:
        """Run the selected profile sequentially and stop after the first failure."""
        try:
            profile = self._profiles[target]
        except KeyError as error:
            raise ValidationInfrastructureError(
                f"no native validation profile configured for {target.value}"
            ) from error

        results: list[CommandResult] = []
        with self._runner.staged(workspace):
            for command in profile.commands:
                result = self._runner.run(command, workspace, profile)
                results.append(result)
                if result.exit_code != 0 or result.timed_out:
                    break
        passed = all(result.exit_code == 0 and not result.timed_out for result in results)
        summary = (
            "All native validation commands passed."
            if passed
            else "A native validation command failed."
        )
        version = self._profile_versions.get(target)
        return ValidationReport(
            target=target,
            passed=passed,
            commands=tuple(results),
            summary=summary,
            profile_revision=None if version is None else version[0],
            profile_digest=None if version is None else version[1],
        )


def standard_commands(target: Target, workspace: Path) -> tuple[CommandSpec, ...]:
    """Return common project-native checks; database-specific commands remain configured.

    Every profile ends with the project's tests, so a run validates only when its tests pass.
    pytest (exit 5), npm (no `test` script), and ctest (`--no-tests=error`) also fail when
    there are no tests; `cargo test` and `go test` pass an empty suite. Ruff and mypy run
    with `python -P`, so modules in the workspace cannot shadow the tools themselves.
    """
    if target in {Target.RUST, Target.DIESEL}:
        return (
            CommandSpec(name="cargo-check", argv=("cargo", "check")),
            CommandSpec(name="cargo-clippy", argv=("cargo", "clippy", "--", "-D", "warnings")),
            CommandSpec(name="cargo-test", argv=("cargo", "test")),
        )
    if target in {
        Target.PYTHON,
        Target.SQLALCHEMY_ALEMBIC,
    }:
        return (
            CommandSpec(name="ruff-check", argv=("python", "-P", "-m", "ruff", "check", ".")),
            CommandSpec(name="mypy-strict", argv=("python", "-P", "-m", "mypy", "--strict", ".")),
            CommandSpec(name="pytest", argv=("python", "-m", "pytest", "-q")),
        )
    if target in {
        Target.TYPESCRIPT,
        Target.REACT_TYPESCRIPT,
        Target.VUE_TYPESCRIPT,
        Target.PRISMA_TYPESCRIPT,
    }:
        commands = [CommandSpec(name="tsc-no-emit", argv=("node_modules/.bin/tsc", "--noEmit"))]
        prisma_schema = _find_prisma_schema(workspace)
        if prisma_schema is not None:
            commands.append(
                CommandSpec(
                    name="prisma-validate",
                    argv=("node_modules/.bin/prisma", "validate", "--schema", prisma_schema),
                )
            )
        commands.append(NPM_TEST)
        return tuple(commands)
    if target in {Target.JAVASCRIPT, Target.REACT_JAVASCRIPT, Target.VUE_JAVASCRIPT}:
        return (
            CommandSpec(name="eslint", argv=("node_modules/.bin/eslint", ".", "--max-warnings=0")),
            NPM_TEST,
        )
    if target is Target.GO:
        return (
            CommandSpec(name="go-vet", argv=("go", "vet", "./...")),
            CommandSpec(name="go-test", argv=("go", "test", "./...")),
        )
    if target in {Target.CPP, Target.CPP_CV, Target.CPP_AAA}:
        return (
            CommandSpec(name="cmake-build", argv=("cmake", "--build", "build", "--parallel")),
            CommandSpec(
                name="ctest",
                argv=("ctest", "--test-dir", "build", "--output-on-failure", "--no-tests=error"),
            ),
        )
    if target is Target.PRISMA_JAVASCRIPT:
        return (
            CommandSpec(
                name="prisma-validate",
                argv=(
                    "node_modules/.bin/prisma",
                    "validate",
                    "--schema",
                    _find_prisma_schema(workspace) or "prisma/schema.prisma",
                ),
            ),
            NPM_TEST,
        )
    if target in {Target.MYSQL, Target.POSTGRESQL}:
        raise ValueError(
            f"{target.value} requires an explicit disposable-database validation profile"
        )
    raise ValueError(f"no standard native commands are defined for {target.value}")


def stage_worktree(workspace_root: Path, staging_root: Path) -> None:
    """Copy a worktree into an existing empty directory, leaving out its `.git` entry.

    The entry is a directory in a main worktree and a pointer file in a linked one, so the
    copy carries no Git metadata, hooks, or engine database. Symlinks are copied as links.

    # Errors

    Raises `ValidationInfrastructureError` when the worktree cannot be read or copied.
    """
    try:
        sources = sorted(
            entry for entry in workspace_root.iterdir() if entry.name.casefold() != ".git"
        )
    except OSError as error:
        raise ValidationInfrastructureError(f"could not read the worktree: {error}") from error
    if not sources:
        return
    try:
        copied = subprocess.run(
            ("cp", "-a", "--reflink=auto", "--", *map(str, sources), str(staging_root)),
            check=False,
            capture_output=True,
            shell=False,
        )
    except OSError:
        copied = None
    if copied is not None:
        if copied.returncode == 0:
            return
        # BSD and busybox cp reject `--reflink` before copying anything. A cp that copied
        # part of the tree failed for a reason the fallback would hit as well.
        if any(staging_root.iterdir()):
            stderr = _decode_output(copied.stderr, 2000).strip()
            raise ValidationInfrastructureError(f"could not stage the worktree: {stderr}")
    try:
        for source in sources:
            destination = staging_root / source.name
            if source.is_dir() and not source.is_symlink():
                shutil.copytree(source, destination, symlinks=True)
            else:
                shutil.copy2(source, destination, follow_symlinks=False)
    except OSError as error:
        raise ValidationInfrastructureError(f"could not stage the worktree: {error}") from error


def _find_prisma_schema(workspace: Path) -> str | None:
    """Find a conventional Prisma schema path without accepting user input."""
    candidates = (workspace / "prisma" / "schema.prisma", workspace / "schema.prisma")
    for candidate in candidates:
        if candidate.is_file() and candidate.resolve().is_relative_to(workspace.resolve()):
            return candidate.relative_to(workspace).as_posix()
    return None


def _docker_client_environment() -> dict[str, str]:
    """Return a fixed PATH plus the allowlisted docker client settings from the host."""
    environment = {"PATH": "/usr/local/bin:/usr/bin:/bin"}
    for name in DOCKER_CLIENT_ENVIRONMENT:
        value = os.environ.get(name)
        if value is not None:
            environment[name] = value
    return environment


def _daemon_is_rootless(environment: dict[str, str]) -> bool:
    """Report whether the daemon lists the `rootless` security option.

    # Errors

    Raises `ValidationInfrastructureError` when the daemon cannot be queried.
    """
    try:
        completed = subprocess.run(
            ("docker", "info", "--format", "{{json .SecurityOptions}}"),
            check=False,
            capture_output=True,
            timeout=DOCKER_QUERY_TIMEOUT_SECONDS,
            shell=False,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValidationInfrastructureError(
            f"could not start docker to query the daemon: {error}"
        ) from error
    if completed.returncode != 0:
        stderr = _decode_output(completed.stderr, 2000)
        raise ValidationInfrastructureError(
            f"docker could not query the daemon (exit {completed.returncode}): {stderr}"
        )
    try:
        options = json.loads(completed.stdout)
    except ValueError as error:
        raise ValidationInfrastructureError("docker info returned unreadable output") from error
    # Each option is comma-separated fields, such as `name=seccomp,profile=builtin`.
    return isinstance(options, list) and any(
        isinstance(option, str) and "name=rootless" in option.split(",") for option in options
    )


def _decode_output(value: bytes | str | None, max_bytes: int) -> str:
    """Decode only the final bounded portion of subprocess output."""
    if value is None:
        return ""
    content = value.encode("utf-8", errors="replace") if isinstance(value, str) else value
    suffix = content[-max_bytes:]
    return suffix.decode("utf-8", errors="replace")
