"""Content-addressed artifact storage and confined workspace access."""

from __future__ import annotations

import fcntl
import hashlib
import os
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol, TypeVar

from pydantic import ValidationError

from sdd_engine.models import ArtifactRef, StrictModel

ModelT = TypeVar("ModelT", bound=StrictModel)


class ArtifactError(RuntimeError):
    """Raised when an artifact is missing, corrupt, or violates storage limits."""


class WorkspaceBusyError(ArtifactError):
    """Raised when another run holds the workspace lock."""


@dataclass(frozen=True)
class FileSnapshot:
    """A workspace file's state before a write; `content` is None for a missing file."""

    content: bytes | None
    mode: int | None
    created_directory: str | None


class ArtifactStore(Protocol):
    """Storage contract for content-addressed context and generated artifacts."""

    def put(self, content: bytes, media_type: str) -> ArtifactRef:
        """Persist bytes and return a verified content pointer."""

    def get(self, reference: ArtifactRef, max_bytes: int) -> bytes:
        """Load and verify a bounded artifact by its pointer."""

    def put_model(self, model: StrictModel) -> ArtifactRef:
        """Persist one strict model as JSON."""

    def get_text(self, reference: ArtifactRef, max_bytes: int) -> str:
        """Load and decode a bounded UTF-8 text artifact."""

    def get_model(self, reference: ArtifactRef, model_type: type[ModelT], max_bytes: int) -> ModelT:
        """Load and strictly validate a bounded JSON artifact."""


class FileArtifactStore:
    """Filesystem-backed content store with atomic writes and digest checks."""

    def __init__(self, root: Path) -> None:
        """Create the artifact store below a dedicated root directory."""
        self._root = root.expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def put(self, content: bytes, media_type: str) -> ArtifactRef:
        """Write immutable content under its SHA-256 digest."""
        digest = hashlib.sha256(content).hexdigest()
        destination = self._path_for(digest)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            descriptor, temporary_name = tempfile.mkstemp(
                prefix="artifact-", dir=destination.parent
            )
            try:
                with os.fdopen(descriptor, "wb") as artifact_file:
                    artifact_file.write(content)
                    artifact_file.flush()
                    os.fsync(artifact_file.fileno())
                try:
                    os.link(temporary_name, destination)
                except FileExistsError:
                    pass
            finally:
                Path(temporary_name).unlink(missing_ok=True)
        return ArtifactRef(digest=digest, byte_length=len(content), media_type=media_type)

    def put_model(self, model: StrictModel) -> ArtifactRef:
        """Serialize a strict model into the content store."""
        return self.put(model.model_dump_json().encode("utf-8"), "application/json")

    def get(self, reference: ArtifactRef, max_bytes: int) -> bytes:
        """Read bytes only when length and digest match the supplied reference."""
        if reference.byte_length > max_bytes:
            raise ArtifactError(f"artifact exceeds {max_bytes} byte hydration limit")
        try:
            content = self._path_for(reference.digest).read_bytes()
        except OSError as error:
            raise ArtifactError(f"could not read artifact {reference.digest}") from error
        actual_digest = hashlib.sha256(content).hexdigest()
        if len(content) != reference.byte_length or actual_digest != reference.digest:
            raise ArtifactError(f"artifact integrity check failed for {reference.digest}")
        return content

    def get_text(self, reference: ArtifactRef, max_bytes: int) -> str:
        """Decode one verified UTF-8 text artifact."""
        try:
            return self.get(reference, max_bytes).decode("utf-8")
        except UnicodeDecodeError as error:
            raise ArtifactError("artifact is not valid UTF-8 text") from error

    def get_model(self, reference: ArtifactRef, model_type: type[ModelT], max_bytes: int) -> ModelT:
        """Decode and strictly validate a JSON artifact as a Pydantic model."""
        try:
            return model_type.model_validate_json(self.get(reference, max_bytes))
        except ValidationError as error:
            raise ArtifactError(f"stored artifact does not match {model_type.__name__}") from error

    def _path_for(self, digest: str) -> Path:
        """Resolve a validated digest to its immutable storage path."""
        directory = self._root / digest[:2]
        destination = directory / digest[2:]
        if not destination.resolve().is_relative_to(self._root):
            raise ArtifactError("artifact path escaped its configured root")
        return destination


class WorkspaceRegistry:
    """Maps opaque workspace identifiers to isolated local worktree roots.

    The calling agent creates and merges worktrees; the registry only confines file access
    to them and serializes runs on the same worktree.
    """

    def __init__(self, workspaces: dict[str, Path], lock_directory: Path | None = None) -> None:
        """Resolve and retain only configured workspace roots.

        # Arguments

        `lock_directory` holds one lock file per workspace root. It defaults to a per-user
        directory under the system temporary directory, outside every worktree.
        """
        self._workspaces = {
            key: value.expanduser().resolve(strict=True) for key, value in workspaces.items()
        }
        if any(not root.is_dir() for root in self._workspaces.values()):
            raise ValueError("every workspace root must be an existing directory")
        self._lock_directory = (
            lock_directory
            if lock_directory is not None
            else Path(tempfile.gettempdir()) / f"sdd-engine-locks-{os.getuid()}"
        )

    def get(self, workspace_id: str) -> Path:
        """Return a configured worktree without accepting paths from graph state."""
        try:
            return self._workspaces[workspace_id]
        except KeyError as error:
            raise ArtifactError(f"workspace {workspace_id!r} is not configured") from error

    @contextmanager
    def lock(self, workspace_id: str) -> Iterator[None]:
        """Hold an exclusive lock on the workspace root for the duration of one run.

        Identifiers that map to the same root share a lock. The lock is released when the
        process exits, so a crashed run cannot leave the workspace locked.

        # Errors

        Raises `WorkspaceBusyError` when another run holds the lock, and `ArtifactError` when
        the workspace is not configured or the lock file cannot be opened.
        """
        root = self.get(workspace_id)
        digest = hashlib.sha256(os.fsencode(root)).hexdigest()
        try:
            self._lock_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor = os.open(
                self._lock_directory / f"{digest}.lock", os.O_RDWR | os.O_CREAT, 0o600
            )
        except OSError as error:
            raise ArtifactError(
                f"could not open the lock for workspace {workspace_id!r}"
            ) from error
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise WorkspaceBusyError(
                    f"workspace {workspace_id!r} is in use by another run"
                ) from error
            yield
        finally:
            os.close(descriptor)

    def read_text(self, workspace_id: str, relative_path: str, max_bytes: int) -> str | None:
        """Read one in-worktree file for immediate node-local hydration."""
        path = self._resolve_file(workspace_id, relative_path)
        if not path.exists():
            return None
        try:
            content = path.read_bytes()
        except OSError as error:
            raise ArtifactError(f"could not read workspace file {relative_path!r}") from error
        if len(content) > max_bytes:
            raise ArtifactError(f"workspace file {relative_path!r} exceeds hydration limit")
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ArtifactError(f"workspace file {relative_path!r} is not UTF-8") from error

    def write_text(self, workspace_id: str, relative_path: str, content: str) -> None:
        """Atomically write a generated file inside its isolated worktree."""
        self._write_bytes(self._resolve_file(workspace_id, relative_path), content.encode("utf-8"))

    def snapshot(self, workspace_id: str, relative_path: str, max_bytes: int) -> FileSnapshot:
        """Capture a file's content, mode, and first missing ancestor before it is written."""
        path = self._resolve_file(workspace_id, relative_path)
        if path.exists():
            content = path.read_bytes()
            if len(content) > max_bytes:
                raise ArtifactError(f"workspace file {relative_path!r} exceeds snapshot limit")
            return FileSnapshot(content, stat.S_IMODE(path.stat().st_mode), None)
        parts = PurePosixPath(relative_path).parts
        root = self.get(workspace_id)
        for depth in range(1, len(parts)):
            if not root.joinpath(*parts[:depth]).exists():
                return FileSnapshot(None, None, PurePosixPath(*parts[:depth]).as_posix())
        return FileSnapshot(None, None, None)

    def restore(
        self,
        workspace_id: str,
        relative_path: str,
        content: bytes | None,
        mode: int | None,
        created_directory: str | None,
    ) -> None:
        """Put a file back as `snapshot` found it.

        A file that did not exist is deleted, along with the directories its write created,
        as long as they are empty again.
        """
        path = self._resolve_file(workspace_id, relative_path)
        if content is not None:
            self._write_bytes(path, content, mode)
            return
        path.unlink(missing_ok=True)
        if created_directory is None:
            return
        stop = self._resolve_file(workspace_id, created_directory)
        directory = path.parent
        while directory.is_relative_to(stop):
            try:
                directory.rmdir()
            except OSError:
                return
            directory = directory.parent

    def _write_bytes(self, destination: Path, content: bytes, mode: int | None = None) -> None:
        """Atomically replace a file, keeping its mode unless one is given."""
        if mode is None:
            mode = stat.S_IMODE(destination.stat().st_mode) if destination.exists() else 0o644
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix="generated-", dir=destination.parent)
        try:
            with os.fdopen(descriptor, "wb") as output_file:
                output_file.write(content)
                output_file.flush()
                os.fchmod(output_file.fileno(), mode)
                os.fsync(output_file.fileno())
            os.replace(temporary_name, destination)
        finally:
            Path(temporary_name).unlink(missing_ok=True)

    def _resolve_file(self, workspace_id: str, relative_path: str) -> Path:
        """Resolve a safe relative path and reject symlink escapes."""
        root = self.get(workspace_id)
        posix_path = PurePosixPath(relative_path)
        if (
            posix_path.is_absolute()
            or ".." in posix_path.parts
            or ".git" in posix_path.parts
            or "\\" in relative_path
        ):
            raise ArtifactError("workspace file paths must be relative and cannot traverse parents")
        path = root.joinpath(*posix_path.parts)
        if not path.resolve(strict=False).is_relative_to(root):
            raise ArtifactError("workspace path escaped its configured root")
        return path
