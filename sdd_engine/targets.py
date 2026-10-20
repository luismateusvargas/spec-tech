"""The one registry of supported targets: their engineering skills and default native checks."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from sdd_engine.models import Target
from sdd_engine.validation import NPM_TEST, CommandSpec

CommandFactory = Callable[[Path], tuple[CommandSpec, ...]]


@dataclass(frozen=True)
class TargetSpec:
    """The skills hydrated for one target and the factory for its standard checks.

    `default_commands` is `None` for database targets, whose checks need an explicit
    disposable-database validation profile.
    """

    skills: tuple[str, ...]
    default_commands: CommandFactory | None


def _cargo_commands(workspace: Path) -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(name="cargo-check", argv=("cargo", "check")),
        CommandSpec(name="cargo-clippy", argv=("cargo", "clippy", "--", "-D", "warnings")),
        CommandSpec(name="cargo-test", argv=("cargo", "test")),
    )


def _python_commands(workspace: Path) -> tuple[CommandSpec, ...]:
    # `-P` keeps modules in the worktree from shadowing Ruff and mypy themselves.
    return (
        CommandSpec(name="ruff-check", argv=("python", "-P", "-m", "ruff", "check", ".")),
        CommandSpec(name="mypy-strict", argv=("python", "-P", "-m", "mypy", "--strict", ".")),
        CommandSpec(name="pytest", argv=("python", "-m", "pytest", "-q")),
    )


def _typescript_commands(workspace: Path) -> tuple[CommandSpec, ...]:
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


def _javascript_commands(workspace: Path) -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(name="eslint", argv=("node_modules/.bin/eslint", ".", "--max-warnings=0")),
        NPM_TEST,
    )


def _prisma_javascript_commands(workspace: Path) -> tuple[CommandSpec, ...]:
    schema = _find_prisma_schema(workspace) or "prisma/schema.prisma"
    return (
        CommandSpec(
            name="prisma-validate",
            argv=("node_modules/.bin/prisma", "validate", "--schema", schema),
        ),
        NPM_TEST,
    )


def _go_commands(workspace: Path) -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(name="go-vet", argv=("go", "vet", "./...")),
        CommandSpec(name="go-test", argv=("go", "test", "./...")),
    )


def _cmake_commands(workspace: Path) -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(name="cmake-build", argv=("cmake", "--build", "build", "--parallel")),
        CommandSpec(
            name="ctest",
            argv=("ctest", "--test-dir", "build", "--output-on-failure", "--no-tests=error"),
        ),
    )


TARGETS: Mapping[Target, TargetSpec] = MappingProxyType(
    {
        Target.JAVASCRIPT: TargetSpec(("javascript-dev",), _javascript_commands),
        Target.TYPESCRIPT: TargetSpec(("typescript-dev",), _typescript_commands),
        Target.PYTHON: TargetSpec(("python-dev",), _python_commands),
        Target.RUST: TargetSpec(("rust-dev",), _cargo_commands),
        Target.GO: TargetSpec(("go-dev",), _go_commands),
        Target.CPP: TargetSpec(("cpp-dev",), _cmake_commands),
        Target.CPP_CV: TargetSpec(("cpp-dev", "cpp-cv-dev"), _cmake_commands),
        Target.CPP_AAA: TargetSpec(("cpp-dev", "cpp-aaa-dev"), _cmake_commands),
        Target.MYSQL: TargetSpec(("database-dev",), None),
        Target.POSTGRESQL: TargetSpec(("database-dev",), None),
        Target.PRISMA_JAVASCRIPT: TargetSpec(
            ("database-dev", "javascript-dev"), _prisma_javascript_commands
        ),
        Target.PRISMA_TYPESCRIPT: TargetSpec(
            ("database-dev", "typescript-dev"), _typescript_commands
        ),
        Target.SQLALCHEMY_ALEMBIC: TargetSpec(("database-dev", "python-dev"), _python_commands),
        Target.DIESEL: TargetSpec(("database-dev", "rust-dev"), _cargo_commands),
        Target.REACT_JAVASCRIPT: TargetSpec(("javascript-dev", "react-dev"), _javascript_commands),
        Target.REACT_TYPESCRIPT: TargetSpec(("typescript-dev", "react-dev"), _typescript_commands),
        Target.VUE_JAVASCRIPT: TargetSpec(("javascript-dev", "vue-dev"), _javascript_commands),
        Target.VUE_TYPESCRIPT: TargetSpec(("typescript-dev", "vue-dev"), _typescript_commands),
    }
)


def standard_commands(target: Target, workspace: Path) -> tuple[CommandSpec, ...]:
    """Return the target's default native checks for a profile configured without commands.

    Every profile ends with the project's tests, so a run validates only when its tests pass.
    pytest (exit 5), npm (no `test` script), and ctest (`--no-tests=error`) also fail when
    there are no tests; `cargo test` and `go test` pass an empty suite.

    # Errors

    Raises `ValueError` for a target without standard checks, such as a database target.
    """
    factory = TARGETS[target].default_commands
    if factory is None:
        raise ValueError(
            f"{target.value} requires an explicit disposable-database validation profile"
        )
    return factory(workspace)


def _find_prisma_schema(workspace: Path) -> str | None:
    """Find a conventional Prisma schema path without accepting user input."""
    candidates = (workspace / "prisma" / "schema.prisma", workspace / "schema.prisma")
    for candidate in candidates:
        if candidate.is_file() and candidate.resolve().is_relative_to(workspace.resolve()):
            return candidate.relative_to(workspace).as_posix()
    return None
