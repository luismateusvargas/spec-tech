# Plan 01: Shared Limits, Canonical Path Validation, and Domain Error Taxonomy

Status: done
Project rules: AGENTS.md, docs/coding/common.md, docs/coding/python.md, skills/python-dev/SKILL.md
Target files: sdd_engine/limits.py, sdd_engine/errors.py, sdd_engine/paths.py, sdd_engine/models.py, sdd_engine/artifacts.py, sdd_engine/scope.py, tests/test_models.py, tests/test_artifacts.py
Depends on: none
Fixes: Q4, K6 (path sanitization & duplication), C5 (blocking tool paths as target files), L6 (error taxonomy), L8 (OSError mapping), Q7 (error hierarchy)

## Outcome and boundary

Establish a single source of truth for byte/character/count bounds (`sdd_engine/limits.py`), a single canonicalizing workspace-relative path validator (`sdd_engine/paths.py`), and a specific domain exception hierarchy (`sdd_engine/errors.py`) with `ArtifactError` preserved as a subclass for backward compatibility. Higher-level Docker staging, SQLite schema changes, spec header parsing, and LangGraph node refactoring stay in Plans 02–05.

## Acceptance criteria

1. **Canonical path normalization and deduplication (`K6`)**: `canonical_relative_path("src/./x.py")` and `canonical_relative_path("src//x.py")` both normalize to `"src/x.py"`, so `TargetFiles` and `GenerationOutput.files` reject aliased duplicates (`["src/x.py", "src/./x.py"]`) with a validation error.
2. **Case-insensitive `.git`, control characters, and tool directories rejected (`K6`, `C5`)**: Paths containing NUL bytes (`"src/x\x00.py"`), control characters (`ord(c) < 0x20`), backslashes, `..`, any path segment matching `.git` case-insensitively (`".GIT/hooks/pre-commit"`), or protected validator tool directories (`"node_modules/.bin/tsc"`, `"build/CTestTestfile.cmake"`) are rejected by `SafeRelativePath`, `WorkspaceRegistry._resolve_file`, and `scope._safe_path`.
3. **Centralized size limits (`Q4`)**: All inline magic numbers (`16_000`, `16_000_000`, `4_000_000`, `2_000_000`, `1_000_000`, `512`, `128`, `64`) across `models.py`, `validation.py`, `graph.py`, `guidance.py`, and `service.py` are replaced with named constants imported from `sdd_engine/limits.py`.
4. **Domain exception hierarchy and `OSError` wrapping (`L6`, `L8`, `Q7`)**: `EngineError` defines `.code: str` and `.retryable: bool` along with specific subclasses (`ArtifactError`, `ArtifactIntegrityError`, `WorkspaceBusyError`, `WorkspaceLockError`, `WorkspaceMismatchError`, `RunNotFoundError`, `RunStateError`, `ProfileError`, `SpecContractError`, `GitOperationError`, `RollbackError`), and `scope.restore_tree` wraps filesystem `OSError`s into `RollbackError(..., cause=exc)` (`raise RollbackError(...) from error`).

## Implementation plan

1. Create `sdd_engine/limits.py` defining:
   - `MAX_PATH_CHARS = 512`
   - `MAX_TARGET_FILES = 128`
   - `MAX_CONTEXT_REFS = 64`
   - `MAX_COMMAND_NAME_CHARS = 128`
   - `MAX_DIAGNOSTIC_CHARS = 16_000`
   - `MAX_SUMMARY_CHARS = 2_000`
   - `MAX_CATEGORY_CHARS = 96`
   - `MAX_FAILURE_REPORT_BYTES = 6 * (MAX_CATEGORY_CHARS + MAX_SUMMARY_CHARS + MAX_DIAGNOSTIC_CHARS) + 256`
   - `MAX_FILE_CHARS = 1_000_000`
   - `MAX_SUBMISSION_BYTES = 3_000_000`
   - `MAX_GENERATED_ARTIFACT_BYTES = 4_000_000`
   - `MAX_CONTEXT_BYTES = 2_000_000`
   - `MAX_REPORT_BYTES = 1_000_000`
   - `MAX_ORIGINAL_FILE_BYTES = 16_000_000`
2. Create `sdd_engine/errors.py` with base class `EngineError(RuntimeError)` (carrying `code: str`, `retryable: bool = False`, and `to_envelope() -> dict[str, object]`). Make `ArtifactError(EngineError)` the base for storage/workspace errors so existing `except ArtifactError` callers continue to work during migration, and define `WorkspaceBusyError(ArtifactError)` (`retryable=True`), `WorkspaceLockError(ArtifactError)`, `ArtifactIntegrityError(ArtifactError)`, `WorkspaceMismatchError(ArtifactError)`, `RunNotFoundError(ArtifactError)`, `RunStateError(ArtifactError)`, `ProfileError(ArtifactError)`, `SpecContractError(EngineError)`, `GitOperationError(ArtifactError)`, and `RollbackError(ArtifactError)`.
3. Create `sdd_engine/paths.py` with:
   - `canonical_relative_path(value: str, *, allow_tool_dirs: bool = False) -> str`:
     - Reject empty strings, `"\\" in value`, or `any(ord(c) < 0x20 or ord(c) == 0x7F for c in value)`.
     - Parse `path = PurePosixPath(value)`; reject `path.is_absolute()`, `not path.parts`, or `".." in path.parts`.
     - Reject any segment where `part.casefold() == ".git"`.
     - When `not allow_tool_dirs`, reject target paths under `node_modules/` (specifically `node_modules/.bin` or any `node_modules` segment) and top-level `build/` (or `CMakeFiles/`) so implementer submissions cannot overwrite validator binaries (`C5`).
     - Return `path.as_posix()`.
   - `resolve_workspace_path(root: Path, relative_path: str, *, allow_tool_dirs: bool = False) -> Path`:
     - Call `canonical_relative_path`, join with `root`, verify `destination.resolve(strict=False).is_relative_to(root.resolve())`, and raise `ArtifactError` on escape.
4. Update [`sdd_engine/models.py`](../models.py#L79-L100) to use `canonical_relative_path` in `SafeRelativePath` and constants from `sdd_engine/limits.py`.
5. Update [`sdd_engine/artifacts.py`](../artifacts.py#L23-L30) to re-export `ArtifactError` and `WorkspaceBusyError` from `sdd_engine/errors.py`, and use `resolve_workspace_path` in `WorkspaceRegistry._resolve_file` ([`artifacts.py:276-290`](../artifacts.py#L276-L290)).
6. Update [`sdd_engine/scope.py`](../scope.py#L31-L40) to use `resolve_workspace_path(..., allow_tool_dirs=True)` in `_safe_path` ([`scope.py:118-125`](../scope.py#L118-L125)), raise `GitOperationError` from `_git`, and catch `OSError` in `restore_tree` ([`scope.py:128-170`](../scope.py#L128-L170)), wrapping it in `RollbackError(f"failed to restore {relative!r}: {error}") from error`.

## Verification

- Run `uv run pytest tests/test_models.py tests/test_artifacts.py`:
  - Verify `["src/x.py", "src/./x.py", "src//x.py"]` is rejected as duplicate paths after canonicalization.
  - Verify `".GIT/hooks/pre-commit"`, `"src/x\x00.py"`, `"src/x\n.py"`, and `"node_modules/.bin/tsc"` are rejected by `GraphInput` and `GenerationOutput`.
  - Verify `restore_tree` on a read-only directory raises `RollbackError` (an `ArtifactError` subclass) instead of raw `PermissionError`.
- Run `uv run ruff check sdd_engine tests`, `uv run ruff format --check sdd_engine tests`, and `uv run mypy sdd_engine tests`.

## Open decisions and sources

- None. Note that `scope._safe_path` sets `allow_tool_dirs=True` so `restore_tree` can still clean up or restore files if an external command wrote under `build/`, while `SafeRelativePath` (`allow_tool_dirs=False`) blocks implementer submissions from targeting `node_modules/` or `build/`.
