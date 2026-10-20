"""Canonical workspace-relative paths and confined filesystem resolution."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from sdd_engine.errors import ArtifactError


def canonical_relative_path(value: str, *, allow_tool_dirs: bool = False) -> str:
    """Normalize a POSIX file path while rejecting unsafe or protected segments.

    Raises:
        ValueError: The path is unsafe or targets a validator tool directory.
    """
    if not value or "\\" in value or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise ValueError("path must be a safe relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(
            "path must identify a file"
            if not path.parts
            else "path must be a safe relative POSIX path"
        )
    parts = tuple(part.casefold() for part in path.parts)
    if ".git" in parts:
        raise ValueError("path must be a safe relative POSIX path")
    if not allow_tool_dirs and (
        "node_modules" in parts or "cmakefiles" in parts or parts[0] == "build"
    ):
        raise ValueError("path must be a safe relative POSIX path")
    return path.as_posix()


def resolve_workspace_path(
    root: Path, relative_path: str, *, allow_tool_dirs: bool = False
) -> Path:
    """Resolve a canonical relative path and reject paths escaping the workspace.

    Raises:
        ArtifactError: The path is invalid or resolves outside the workspace.
    """
    try:
        canonical = canonical_relative_path(relative_path, allow_tool_dirs=allow_tool_dirs)
    except ValueError as error:
        raise ArtifactError(str(error)) from error
    destination = root / canonical
    if not destination.resolve(strict=False).is_relative_to(root.resolve()):
        raise ArtifactError("workspace path escaped its configured root")
    return destination
