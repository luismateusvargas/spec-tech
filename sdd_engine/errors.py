"""Domain errors exposed by engine storage, workspace, and run operations."""

from __future__ import annotations

from typing import ClassVar


class EngineError(RuntimeError):
    """Base engine failure with a stable code and retry guidance."""

    code: ClassVar[str] = "engine_error"
    retryable: ClassVar[bool] = False

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        """Keep a readable message and optional underlying failure."""
        super().__init__(message)
        self.cause = cause

    def to_envelope(self) -> dict[str, object]:
        """Return the public structured error payload."""
        return {"error": {"code": self.code, "message": str(self), "retryable": self.retryable}}


class ArtifactError(EngineError):
    """Base failure for artifact storage and workspace operations."""

    code = "artifact_error"


class ArtifactIntegrityError(ArtifactError):
    """An artifact failed its content or model integrity check."""

    code = "artifact_integrity_error"


class WorkspaceBusyError(ArtifactError):
    """Another run currently holds the workspace lock."""

    code = "workspace_busy"
    retryable = True


class WorkspaceLockError(ArtifactError):
    """The workspace lock could not be acquired or opened."""

    code = "workspace_lock_error"


class WorkspaceMismatchError(ArtifactError):
    """A run was used with a different workspace."""

    code = "workspace_mismatch"


class RunNotFoundError(ArtifactError):
    """The requested run does not exist."""

    code = "run_not_found"


class RunStateError(ArtifactError):
    """The requested operation is invalid in the current run state."""

    code = "run_state_error"


class ProfileError(ArtifactError):
    """A validation profile is missing or invalid."""

    code = "profile_error"


class SpecContractError(EngineError):
    """A task specification violates the engine contract."""

    code = "spec_contract_error"


class GitOperationError(ArtifactError):
    """A Git operation failed while inspecting or restoring a worktree."""

    code = "git_operation_error"


class RollbackError(ArtifactError):
    """A worktree path could not be restored."""

    code = "rollback_error"
