# Plan 04: Committed Spec Gate, Submission Contracts, and Typed MCP Schemas

Status: ready
Project rules: AGENTS.md, docs/coding/common.md, docs/coding/python.md, skills/python-dev/SKILL.md
Target files: sdd_engine/models.py, sdd_engine/service.py, sdd_engine/mcp_server.py, sdd_engine/scope.py, tests/test_models.py, tests/test_graph.py
Depends on: 01-limits-paths-and-errors.md, 03-store-and-worktree-isolation.md
Fixes: C3 (spec status allowlist & committed spec binding), C4 (typed MCP schemas & prompt submission_schema), C6a (oversized submission pre-write cap), K3 (documentation_metadata & error_handling_mapping contract), K5 (status vocabulary alignment), Q3 (GraphInput/GraphState field deduplication)

## Outcome and boundary

Enforce that task specs have `Status: ready` in their header block (`C3`, `K5`) and support binding runs to a committed spec file in `HEAD` (including parsing a `Target files:` header when present); bound `WorkspaceFile.content` and total `GenerationOutput` bytes in `models.py` before any file is written (`C6a`); tighten `documentation_metadata` (removing `@returns` as an error-section substitute) and allow explicit `no_failure_paths: bool = False` in `GenerationOutput` (`K3`); include `submission_schema` in `GenerationPrompt` and expose typed schemas on MCP tools (`C4`) without breaking in-graph contract retry tracking (Fact-Check #3); and deduplicate `GraphInput` / `GraphState` fields (`Q3`).

## Acceptance criteria

1. **Header-only `Status: ready` allowlist (`C3`, `K5`)**:
   - `require_ready_spec(spec_text)` inspects only the header block before the first `\n## ` heading and requires exactly one `Status: ready` line (`^Status:\s*ready\s*$`, case-insensitive on `Status:`).
   - Specs with `Status: draft`, `Status: blocked`, `Status: draft | ready | blocked`, or no `Status:` line raise `SpecContractError`.
   - A spec with `Status: ready` in its header and an indented `status: blocked` inside `## Open decisions` is **accepted**.
2. **Committed spec binding and `Target files:` header parsing (`C3`)**:
   - When `spec_path` is passed to `begin_task` (or when `spec` names a workspace-relative `.md` file committed in `HEAD` that has no uncommitted worktree modifications), the engine reads the spec blob from `HEAD` (`git cat-file blob HEAD:<spec_path>`), verifies the worktree file matches `HEAD`, records `spec_path` and `spec_blob`, and if the spec header declares `Target files: path1, path2`, derives or validates `target_files` against that list.
3. **Oversized submissions rejected as retryable `generation_contract` failures before disk write (`C6a`)**:
   - `WorkspaceFile.content` is capped at `limits.MAX_FILE_CHARS` (`1_000_000` chars) and `GenerationOutput` validates `sum(len(f.content.encode("utf-8")) for f in self.files) <= limits.MAX_SUBMISSION_BYTES` (`3_000_000` bytes).
   - Submitting a 5 MB file in `submit` does **not** write `big.py` to disk, does **not** fail terminally with `artifact_contract`, increments `generation_attempts` to `1`, records a `FailureReport(category="generation_contract")`, and returns a retry `prompt` with `generation_feedback`.
4. **Honest documentation and error-mapping contract (`K3`)**:
   - `documentation_metadata` requires both an argument marker (`# Arguments`, `Args:`, or `@param`) and a genuine error marker (`# Errors`, `Raises:`, or `@throws` — `@returns` alone is rejected), with non-empty text following each marker so the literal `"Args: Raises:"` is rejected.
   - `GenerationOutput` adds `no_failure_paths: bool = False`; `error_handling_mapping` may be empty `()` only when `no_failure_paths=True` (and must be non-empty when `no_failure_paths=False`).
5. **Typed MCP tool schemas and self-describing `GenerationPrompt` (`C4`, Fact-Check #3)**:
   - `GenerationPrompt` includes `submission_schema: dict[str, object]` (populated from `GenerationOutput.model_json_schema()`) and `submission_semantics: str` explaining that `files` is a non-empty set of whole files within `allowed_target_files` and files written in earlier rounds remain on disk.
   - `mcp_server.py` annotates `tier: Tier`, `target: Target`, and `files: SubmissionPayload` (a `TypedDict` mirroring `GenerationOutput` fields so FastMCP publishes the full JSON Schema for `files`, `documentation_metadata`, `error_handling_mapping`, and `no_failure_paths` while still letting invalid content reach the graph's `check_contract` node for retry accounting).
6. **`GraphState` inherits `GraphInput` fields (`Q3`)**: `GraphState` subclasses `GraphInput` (or shares a common `_RunIdentity(StrictModel)` base) so `run_id`, `workspace_id`, `target`, `tier`, `specification`, `target_files`, `context`, and `target_entities` are defined once.

## Implementation plan

1. In [`sdd_engine/models.py`](../models.py):
   - Extract `_GraphBase(StrictModel)` (or have `GraphState(GraphInput)`) so the 8 input fields are declared once (`Q3`).
   - Update `WorkspaceFile.content` to `Annotated[str, Field(max_length=limits.MAX_FILE_CHARS)]`.
   - On `GenerationOutput`:
     - Add `no_failure_paths: bool = False`.
     - Replace `require_error_mapping` with a `@model_validator(mode="after")` that enforces:
       - If `not self.error_handling_mapping and not self.no_failure_paths`, raise `ValueError("error_handling_mapping must contain at least one entry unless no_failure_paths is True")`.
       - If `self.error_handling_mapping and self.no_failure_paths`, raise `ValueError("error_handling_mapping must be empty when no_failure_paths is True")`.
       - Check total UTF-8 byte length of `self.files` <= `limits.MAX_SUBMISSION_BYTES`.
     - Update `require_documentation_sections` to remove `"@returns" in value` from `has_errors` and require non-whitespace documentation body after both the arguments header/tag and the errors header/tag (rejecting `"Args: Raises:"`).
   - On `GenerationPrompt` ([`models.py:226-241`](../models.py#L226-L241)), add:
     - `submission_semantics: str = "Submit whole-file replacements for one or more paths in allowed_target_files. Files written in earlier rounds remain on disk."`
     - `submission_schema: dict[str, object] = Field(default_factory=GenerationOutput.model_json_schema)`
2. In [`sdd_engine/scope.py`](../scope.py), add `committed_blob(workspace: Path, relative_path: str) -> tuple[str, str]` which verifies `relative_path` via `canonical_relative_path`, reads the blob SHA from `HEAD` (`git rev-parse HEAD:{path}`), checks `git status --porcelain -- {path}` is clean, and returns `(blob_sha, text)`.
3. In [`sdd_engine/service.py`](../service.py):
   - Replace `_BLOCKED_SPEC` ([`service.py:30`](../service.py#L30)) with `parse_spec_header(spec_text: str) -> tuple[str, tuple[str, ...] | None]`:
     - Extract `header = spec_text.split("\n## ", 1)[0]`.
     - Match `^Status:\s*(?P<status>[^\n]+?)\s*$` (`re.MULTILINE`). If `statuses != ["ready"]`, raise `SpecContractError(f"task specification header must declare 'Status: ready', found {statuses}")`.
     - Optionally match `^Target files:\s*(?P<files>[^\n]+?)\s*$` (`re.MULTILINE`). If present, split on commas into canonical relative paths.
   - In `begin_task`:
     - Add optional `spec_path: str | None = None` parameter (and allow `target_files: list[str] | None = None` when `Target files:` is present in the spec header).
     - When `spec_path` is provided, load `(spec_blob, spec_text)` from `HEAD` via `committed_blob(root, spec_path)`; if `spec` was also passed and differs from `spec_text`, raise `SpecContractError`.
     - Call `parse_spec_header(spec_text)` (requiring `Status: ready` when `Status:` is present or when `spec_path` is used; note: check existing tests in `tests/test_graph.py` and update `_begin` in `tests/test_graph.py` to include `Status: ready\n`!).
     - If the spec header declares `Target files:`, use them when `target_files` is omitted or verify `tuple(canonical_relative_path(p) for p in target_files)` matches the spec header's `Target files:`.
4. In [`sdd_engine/mcp_server.py`](../mcp_server.py):
   - Define `TypedDict` schemas `WorkspaceFileInput`, `ErrorHandlingMappingInput`, and `SubmissionPayload` (with `Required`/`NotRequired` annotations) and use `tier: Tier`, `target: Target`, and `files: SubmissionPayload` on `begin_task` and `submit` so FastMCP's `list_tools()` exposes the complete typed JSON Schema to MCP clients without prematurely rejecting retryable contract errors before the graph runs.

## Verification

- Run `uv run pytest tests/test_models.py tests/test_graph.py`:
  - Update `tests/test_models.py:64` (replace `@returns` positive case with a negative test verifying `@param ... @returns ...` without `@throws`/`# Errors`/`Raises:` is rejected, and `"Args: Raises:"` is rejected).
  - Add unit test in `tests/test_models.py` for `no_failure_paths=True` with `error_handling_mapping=()`.
  - Add integration test in `tests/test_graph.py` submitting a 5 MB file (`"x" * 5_000_000`) and verifying `submit` returns a retry `prompt` with `generation_contract` feedback instead of a terminal `artifact_contract` failure, and that the oversized file is not written to disk.
  - Add tests in `tests/test_graph.py` for `Status: draft`, unfilled `Status: draft | ready | blocked`, ready spec with indented `status: blocked` under `## Open decisions`, and `spec_path` bound to `HEAD` with `Target files:`.
  - Add a test inspecting `asyncio.run(mcp_server.implementer.list_tools())` verifying `tier` and `target` have `enum` schemas and `submit`'s `files` input schema lists `files`, `documentation_metadata`, and `error_handling_mapping`.
- Run `uv run ruff check sdd_engine tests`, `uv run ruff format --check sdd_engine tests`, and `uv run mypy sdd_engine tests`.

## Open decisions and sources

- Keeping the parameter name `files: SubmissionPayload` on `submit(workspace, run_id, files)` (or accepting an alias `submission` in `service.submit`) preserves backward compatibility with all existing callers and tests while still publishing the full `GenerationOutput` object schema in MCP.
