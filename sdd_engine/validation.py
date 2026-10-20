"""Hardened Docker execution and native compiler/static-analysis profiles."""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path
from typing import Protocol

from pydantic import Field, model_validator

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


class ValidationInfrastructureError(RuntimeError):
    """Raised when native checks cannot run, as opposed to running and failing."""


class CommandSpec(StrictModel):
    """One fixed argument-vector command from trusted deployment configuration."""

    name: str
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

    image: str
    commands: JsonTuple[CommandSpec]
    timeout_seconds: int = Field(default=600, ge=1, le=3600)
    memory_limit: str = "4g"
    cpu_limit: float = Field(default=2.0, gt=0, le=64)
    process_limit: int = Field(default=256, ge=16, le=8192)
    # CommandResult caps stdout and stderr at 16,000 characters.
    max_output_bytes: int = Field(default=16_000, ge=1024, le=16_000)

    @model_validator(mode="after")
    def require_commands(self) -> ValidationProfile:
        """Require at least one native check for every validation profile."""
        if not self.commands:
            raise ValueError("validation profiles must define at least one command")
        return self


class CommandRunner(Protocol):
    """Executes configured commands within an isolated project workspace."""

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

        `user` is passed to `docker run --user` and is for rootful daemons only. Leave it
        unset under rootless Docker, where container root already maps to the host user.
        """
        self._user = user
        self._cleanup_timeout_seconds = cleanup_timeout_seconds

    def run(
        self,
        command: CommandSpec,
        workspace: Path,
        profile: ValidationProfile,
    ) -> CommandResult:
        """Execute one argv command with reduced container privileges and limits."""
        workspace_root = workspace.resolve(strict=True)
        container_name = f"sdd-{uuid.uuid4().hex}"
        user_options = ("--user", self._user) if self._user is not None else ()
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
            f"type=bind,src={workspace_root},dst=/workspace",
            "--workdir",
            "/workspace",
            profile.image,
            *command.argv,
        )
        environment = _docker_client_environment()
        try:
            completed = subprocess.run(
                docker_argv,
                cwd=workspace_root,
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

    def __init__(self, profiles: dict[Target, ValidationProfile], runner: CommandRunner) -> None:
        """Bind trusted validation profiles to a sandboxed command runner."""
        self._profiles = profiles
        self._runner = runner

    def validate(self, target: Target, workspace: Path) -> ValidationReport:
        """Run the selected profile sequentially and stop after the first failure."""
        try:
            profile = self._profiles[target]
        except KeyError as error:
            raise ValidationInfrastructureError(
                f"no native validation profile configured for {target.value}"
            ) from error

        results: list[CommandResult] = []
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
        return ValidationReport(
            target=target, passed=passed, commands=tuple(results), summary=summary
        )


def standard_commands(target: Target, workspace: Path) -> tuple[CommandSpec, ...]:
    """Return common project-native checks; database-specific commands remain configured.

    Every profile ends with the project's tests, so a run validates only when its tests pass.
    pytest (exit 5), npm (no `test` script), and ctest (`--no-tests=error`) also fail when
    there are no tests; `cargo test` and `go test` pass an empty suite.
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
            CommandSpec(name="ruff-check", argv=("python", "-m", "ruff", "check", ".")),
            CommandSpec(name="mypy-strict", argv=("python", "-m", "mypy", "--strict", ".")),
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


def _decode_output(value: bytes | str | None, max_bytes: int) -> str:
    """Decode only the final bounded portion of subprocess output."""
    if value is None:
        return ""
    content = value.encode("utf-8", errors="replace") if isinstance(value, str) else value
    suffix = content[-max_bytes:]
    return suffix.decode("utf-8", errors="replace")
