# Plan 03: Typed Persistence, Artifact Store Deduplication, and Worktree Ownership

Status: done
Project rules: AGENTS.md, docs/coding/common.md, docs/coding/python.md, skills/python-dev/SKILL.md
Target files: sdd_engine/store.py, sdd_engine/artifacts.py, sdd_engine/service.py, sdd_engine/models.py, tests/test_artifacts.py, tests/test_graph.py
Depends on: 01-limits-paths-and-errors.md, 02-sandbox-and-profile-hardening.md
Fixes: L11 (cross-worktree run access), C2 (profile revision & digest recorded per run), Q1 (duplicate ArtifactStore implementation & inline hashlib import), Q5 (RunPhase enum, typed RunRecord, store SRP), Q6 (wire standard_commands in configure_profile, clean up snapshots table)

## Outcome and boundary

Enforce strict worktree ownership so one worktree path cannot inspect, submit to, or finish another worktree's run (`L11`); record the active `profile_revision` and `profile_digest` on each run and refuse `submit`/`finish_task` if the profile changed mid-run (`C2`); replace untyped `dict[str, object]` rows and string phase literals with `RunPhase(StrEnum)` and a frozen `RunRecord` (`Q5`); deduplicate `ArtifactStore` methods between `artifacts.py` and `store.py` (`Q1`); and allow `configure_profile` to default `commands` to `standard_commands(target, root)` when omitted (`Q6`).

## Acceptance criteria

1. **Cross-worktree run isolation (`L11`)**: Starting a run in `wt-main` and calling `get_run_report(wt_sibling, run_id)`, `submit(wt_sibling, run_id, ...)`, or `finish_task(wt_sibling, run_id)` raises `WorkspaceMismatchError` (`ArtifactError` subclass) without modifying `wt-main` or advancing the run.
2. **Mid-run profile tampering detection (`C2`)**: `begin_task` records `profile_revision` and `profile_digest` on the `runs` row and in `ValidationReport`. Calling `configure_profile` while a run is `pending` or `terminal` causes subsequent `submit` or `finish_task` for that run to fail with `ProfileError` ("validation profile changed during the active run").
3. **Typed `RunPhase` and `RunRecord` (`Q5`)**: `RunPhase` (`PENDING = "pending"`, `TERMINAL = "terminal"`, `FINISHED = "finished"`) replaces raw phase strings across `store.py` and `service.py`, and `store.run(run_id)` returns a typed `RunRecord` instead of `dict[str, object]`.
4. **Single `ArtifactStore` base implementation (`Q1`)**: `put_model`, `get_text`, and `get_model` are implemented once on a base `BaseArtifactStore` class in `sdd_engine/artifacts.py` inherited by `ProjectStore` (and `FileArtifactStore` in tests), and `import hashlib` is at module top level in `sdd_engine/store.py`.
5. **Default `standard_commands` in `configure_profile` (`Q6`)**: Calling `configure_profile(workspace, "python", {"image": "busybox:1.37"})` without `"commands"` populates `commands` from `standard_commands(Target.PYTHON, root)`.

## Implementation plan

1. In [`sdd_engine/models.py`](../models.py), add `RunPhase(StrEnum)` with `PENDING = "pending"`, `TERMINAL = "terminal"`, and `FINISHED = "finished"`, and add optional `profile_revision: Annotated[int, Field(ge=1)] | None = None` and `profile_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None` to `ValidationReport` ([`models.py:266-273`](../models.py#L266-L273)).
2. In [`sdd_engine/artifacts.py`](../artifacts.py#L40-L126):
   - Provide a `BaseArtifactStore` mixin/abstract base class implementing `put_model`, `get_text`, and `get_model` in terms of `put` and `get`, plus a shared `_verify_bytes(content: bytes, reference: ArtifactRef) -> bytes` helper.
   - Make `FileArtifactStore` and `ProjectStore` inherit from `BaseArtifactStore`.
3. In [`sdd_engine/store.py`](../store.py):
   - Move `import hashlib` to module top level ([`store.py:164,176`](../store.py#L164)).
   - Define frozen `@dataclass(frozen=True) class StoredProfile` (`target: Target`, `profile: ValidationProfile`, `revision: int`, `digest: str`) and `@dataclass(frozen=True) class RunRecord` (`run_id: str`, `workspace: Path`, `model: str`, `request: GraphInput`, `head: str`, `start_tree: str`, `phase: RunPhase`, `profile_revision: int`, `profile_digest: str`, `spec_path: str | None`, `spec_blob: str | None`, `outcome: RunStatus | None`, `state: GraphState | None`, `prompt: dict[str, object] | None`, `submitted: tuple[str, ...]`, `scope_report: dict[str, object] | None`).
   - Bump schema `PRAGMA user_version` to `3` with an idempotent migration from v1/v2 adding `profile_revision INTEGER NOT NULL DEFAULT 1`, `profile_digest TEXT NOT NULL DEFAULT ''`, `spec_path TEXT`, and `spec_blob TEXT` to `runs`.
   - Have `get_profile_record(target: Target) -> StoredProfile` return both the `ValidationProfile`, its `revision`, and its SHA-256 `digest` (raising `ProfileError` when missing).
   - Raise `RunNotFoundError` when `run_id` is absent in `run(run_id) -> RunRecord`.
4. In [`sdd_engine/service.py`](../service.py):
   - Update `_run_store(workspace: str, run_id: str) -> tuple[Path, ProjectStore, RunRecord]` to compare `record.workspace.resolve() != root` and raise `WorkspaceMismatchError(f"run {run_id!r} belongs to worktree {record.workspace}, not {root}")`.
   - In `begin_task`, load `stored_profile = store.get_profile_record(parsed_target)` and store `stored_profile.revision` and `stored_profile.digest` in `insert_run`.
   - In `submit` and `finish_task`, verify the current `store.get_profile_record(record.request.target)` matches `(record.profile_revision, record.profile_digest)`, raising `ProfileError("validation profile changed during the active run")` if modified.
   - In `configure_profile(workspace, target, profile)`, if `"commands"` is not in `profile`, populate `profile = {**profile, "commands": [cmd.model_dump(mode="json") for cmd in standard_commands(parsed_target, root)]}`.

## Verification

- Run `uv run pytest tests/test_artifacts.py tests/test_graph.py`:
  - Add a test in `tests/test_graph.py` with two linked git worktrees (`main` and `sibling`), verifying that calling `get_run_report`, `submit`, or `finish_task` with `sibling` for a run started on `main` raises `WorkspaceMismatchError`.
  - Add a test verifying that calling `configure_profile` mid-run causes `submit` and `finish_task` to raise `ProfileError`.
  - Add a test verifying `configure_profile` without `commands` populates `standard_commands`.
- Run `uv run ruff check sdd_engine tests`, `uv run ruff format --check sdd_engine tests`, and `uv run mypy sdd_engine tests`.

## Open decisions and sources

- Keep `snapshots` table in `store.py` so Plan 05 can use it (or `record.state.original_files`) during `finish_task` / `cancel_task` rollback of gitignored target files, maintaining compatibility with `tests/test_graph.py:91`.
