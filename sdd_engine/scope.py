"""Git tree snapshots, scope findings, and conservative worktree restoration."""

from __future__ import annotations

import errno
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path

from sdd_engine.errors import GitOperationError, RollbackError, SpecContractError
from sdd_engine.limits import MAX_CONTEXT_BYTES
from sdd_engine.paths import canonical_relative_path, resolve_workspace_path

_SUPPRESSION = re.compile(
    r"(?:noqa\b|type:\s*ignore\b|eslint-disable\b|@ts-ignore\b|pragma:\s*no cover\b|"
    r"#\[allow\(|NOLINT\b)"
)
_SKIP = re.compile(
    r"(?:pytest\.mark\.skip|\bskip\s*\(|\bignore\s*\(|\btest\.skip\s*\(|"
    r"#\[ignore\b|\bt\.Skip(?:Now|f)?\s*\(|\bGTEST_SKIP\s*\()"
)
_TEST_PATH = re.compile(
    r"(?:^|/)(?:tests?|__tests__)/|(?:^|/)test_[^/]+|(?:_test|\.(?:test|spec))\.[^/]+$"
)
_CHECK_CONFIG = re.compile(
    r"(?:^|/)(?:\.gitignore|pyproject\.toml|pytest\.ini|mypy\.ini|ruff\.toml|eslint\.config\.[^/]+|"
    r"\.eslintrc[^/]*|tsconfig[^/]*\.json|Cargo\.toml|go\.mod|CMakeLists\.txt|package\.json)$"
)


def _git(workspace: Path, *arguments: str, env: dict[str, str] | None = None) -> bytes:
    try:
        result = subprocess.run(
            ("git", *arguments), cwd=workspace, env=env, capture_output=True, check=False
        )
    except OSError as error:
        raise GitOperationError(f"could not run git {' '.join(arguments[:2])}") from error
    if result.returncode != 0:
        raise GitOperationError(
            f"git {' '.join(arguments[:2])} failed: {result.stderr.decode(errors='replace')[:500]}"
        )
    return result.stdout


def head(workspace: Path) -> str:
    """Return the worktree's current commit identifier."""
    return _git(workspace, "rev-parse", "HEAD").decode().strip()


def worktree_tree(workspace: Path, preserve: tuple[str, ...] = ()) -> str:
    """Create a Git tree of tracked and untracked worktree files using a private index."""
    with tempfile.TemporaryDirectory(prefix="sdd-index-") as directory:
        environment = os.environ.copy()
        environment["GIT_INDEX_FILE"] = str(Path(directory) / "index")
        _git(workspace, "read-tree", "HEAD", env=environment)
        _git(workspace, "add", "-A", env=environment)
        # An edited .gitignore must not make a previously visible untracked file
        # disappear from the finishing tree.
        existing = [
            path
            for path in preserve
            if (workspace / path).exists() or (workspace / path).is_symlink()
        ]
        if existing:
            pathspec = Path(directory) / "preserve-paths"
            pathspec.write_bytes(b"\0".join(os.fsencode(path) for path in existing) + b"\0")
            _git(
                workspace,
                "add",
                "-f",
                f"--pathspec-from-file={pathspec}",
                "--pathspec-file-nul",
                env=environment,
            )
        return _git(workspace, "write-tree", env=environment).decode().strip()


def committed_blob(workspace: Path, relative_path: str) -> tuple[str, str]:
    """Return the blob ID and UTF-8 text of a regular file committed at `HEAD`.

    The worktree and index copies must match `HEAD`, so the run implements the reviewed text.

    # Errors

    Raises `SpecContractError` when the path is unsafe, absent from `HEAD`, not a regular
    file, modified, too large, or not UTF-8, and `GitOperationError` when Git fails.
    """
    try:
        path = canonical_relative_path(relative_path)
    except ValueError as error:
        raise SpecContractError(f"spec_path {relative_path!r}: {error}") from error
    # `--literal-pathspecs` keeps a path such as `:(glob)*` from acting as pathspec magic.
    entry = _git(workspace, "--literal-pathspecs", "ls-tree", "-z", "HEAD", "--", path)
    if not entry:
        raise SpecContractError(f"spec_path {path!r} is not committed at HEAD")
    mode, kind, blob = entry.split(b"\t", 1)[0].decode().split(" ")
    if kind != "blob" or mode not in {"100644", "100755"}:
        raise SpecContractError(f"spec_path {path!r} is not a regular file at HEAD")
    if _git(workspace, "--literal-pathspecs", "status", "--porcelain", "-z", "--", path):
        raise SpecContractError(f"spec_path {path!r} has uncommitted changes")
    size = int(_git(workspace, "cat-file", "-s", blob).decode().strip())
    if size > MAX_CONTEXT_BYTES:
        raise SpecContractError(f"spec_path {path!r} exceeds {MAX_CONTEXT_BYTES} bytes")
    try:
        text = _git(workspace, "cat-file", "blob", blob).decode("utf-8")
    except UnicodeDecodeError as error:
        raise SpecContractError(f"spec_path {path!r} is not UTF-8") from error
    return blob, text


def tree_paths(workspace: Path, tree: str) -> tuple[str, ...]:
    """List file paths recorded in a Git tree."""
    raw = _git(workspace, "ls-tree", "-r", "--name-only", "-z", tree)
    return tuple(os.fsdecode(item) for item in raw.split(b"\0") if item)


def changed_paths(workspace: Path, before: str, after: str) -> list[str]:
    """List every changed path without Git rename heuristics."""
    raw = _git(workspace, "diff", "--name-only", "--no-renames", "-z", before, after)
    return [os.fsdecode(item) for item in raw.split(b"\0") if item]


def scope_report(
    workspace: Path, before: str, after: str, submitted: set[str], targets: set[str]
) -> dict[str, object]:
    """Label changed paths and surface edits that require reviewer attention."""
    findings: list[dict[str, object]] = []
    for path in changed_paths(workspace, before, after):
        declared = path in submitted and path in targets
        flags: list[str] = []
        if _TEST_PATH.search(path):
            if not _git(workspace, "ls-tree", "-z", after, "--", path):
                flags.append("test_deleted")
            elif not declared:
                flags.append("test_changed_outside_plan")
        if _CHECK_CONFIG.search(path):
            flags.append("check_config_changed")
        diff = _git(workspace, "diff", "--no-ext-diff", "--unified=0", before, after, "--", path)
        added = "\n".join(
            line[1:]
            for line in diff.decode(errors="replace").splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        if _SUPPRESSION.search(added):
            flags.append("suppression_added")
        if _SKIP.search(added):
            flags.append("skip_added")
        findings.append(
            {"path": path, "label": "declared" if declared else "undeclared", "flags": flags}
        )
    return {"start_tree": before, "finish_tree": after, "changes": findings}


def _safe_path(workspace: Path, relative: str) -> Path:
    return resolve_workspace_path(workspace, relative, allow_tool_dirs=True)


def restore_tree(workspace: Path, before: str, after: str, original_head: str) -> None:
    """Restore every changed worktree path, refusing a run whose HEAD moved."""
    if head(workspace) != original_head:
        raise RollbackError("HEAD moved during the run; automatic rollback refused")
    paths = changed_paths(workspace, before, after)
    for relative in paths:
        try:
            destination = _safe_path(workspace, relative)
            metadata = _git(workspace, "ls-tree", "-z", before, "--", relative)
            if not metadata:
                if destination.is_dir() and not destination.is_symlink():
                    raise RollbackError(f"cannot remove changed directory {relative!r}")
                destination.unlink(missing_ok=True)
                parent = destination.parent
                root_resolved = workspace.resolve()
                while parent != root_resolved and parent.is_relative_to(root_resolved):
                    try:
                        parent.rmdir()
                    except OSError as error:
                        if error.errno not in (errno.ENOTEMPTY, errno.EEXIST):
                            raise
                        break
                    parent = parent.parent
                continue
            header = metadata.split(b"\t", 1)[0].decode()
            mode_text, kind, object_id = header.split(" ")
            if kind != "blob":
                raise RollbackError(f"cannot restore non-file Git entry {relative!r}")
            content = _git(workspace, "cat-file", "blob", object_id)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.is_symlink():
                destination.unlink()
            if mode_text == "120000":
                destination.unlink(missing_ok=True)
                destination.symlink_to(os.fsdecode(content))
            else:
                descriptor, temporary = tempfile.mkstemp(
                    prefix="sdd-restore-", dir=destination.parent
                )
                try:
                    with os.fdopen(descriptor, "wb") as output:
                        output.write(content)
                        output.flush()
                        os.fsync(output.fileno())
                    os.chmod(temporary, stat.S_IMODE(int(mode_text, 8)))
                    os.replace(temporary, destination)
                finally:
                    Path(temporary).unlink(missing_ok=True)
        except OSError as error:
            raise RollbackError(f"failed to restore {relative!r}: {error}", cause=error) from error
