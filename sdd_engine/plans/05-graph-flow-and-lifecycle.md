# Plan 05: Single-Graph Node Decomposition, Rollback Reconciliation, Hydration Order, and Run Cancellation

Status: done
Project rules: AGENTS.md, docs/coding/common.md, docs/coding/python.md, skills/python-dev/SKILL.md
Target files: sdd_engine/graph.py, sdd_engine/guidance.py, sdd_engine/service.py, sdd_engine/mcp_server.py, sdd_engine/cli.py, sdd_engine/models.py, pyproject.toml, tests/test_graph.py
Depends on: 01-limits-paths-and-errors.md, 03-store-and-worktree-isolation.md, 04-spec-and-submission-contracts.md
Fixes: L1 (generate node SRP & re-hydration on resume), L2 (18 compiled subgraphs), L3 (retry budget naming & bounds), L4 (GraphPatch None semantics), L5 (RouteDecision ceremony), L6 (_step lock error wrapping), L7 (two overlapping rollback systems), L8 (unmapped OSError in restore), L9 (lock held across submit check), L10 (diagnostics hydrated before existing files), C6b (cancel_task & submit crash recovery), C6c (packaging skills & OSError mapping in _load_skill), C6d (validation timeout bounds), K2 (stop injecting workflow skill into prompt), K7 (untrusted prompt field annotations), Q3 (CHECKPOINT_ALLOWLIST deduplication), Q8 (unit-testable module-level nodes)

## Outcome and boundary

Replace the 18 compiled target subgraphs and closure-based `generate`/`validate`/`rollback` nodes with a single `StateGraph(GraphState)` built from module-level node functions (`hydrate`, `await_submission`, `check_contract`, `apply_files`, `validate`, `rollback`) so resuming from `interrupt()` never re-runs hydration (`L1`, `L2`, `Q8`). Hydrate repair diagnostics before `existing_files` (`L10`), stop injecting the `sdd-implement-<tier>` workflow skill into `engineering_guidance` (`K2`), map `OSError` in `_load_skill` to `ArtifactError` and configure wheel skill discovery (`C6c`), reconcile rollback so failed runs preserve scope reporting and handle `OSError` cleanly (`L7`, `L8`), add `cancel_task` and `submit` exception recovery so a worktree is never permanently stranded (`C6b`, `L9`), and clean up `GraphPatch`, `RouteDecision`, and `_step` error wrapping (`L4`, `L5`, `L6`).

## Acceptance criteria

1. **Single graph and no re-hydration on `submit` (`L1`, `L2`, `Q8`)**:
   - `build_graph` compiles a single `StateGraph(GraphState)` reading `state.target` in `validate`, with module-level node functions (`hydrate_node`, `await_submission_node`, `check_contract_node`, `apply_files_node`, `validate_node`, `rollback_node`) bound via `functools.partial(..., dependencies=dependencies)`.
   - `hydrate_node` stores the `GenerationPrompt` in the artifact store (`state.prompt_artifact: ArtifactRef | None = None`), and `await_submission_node` only loads `state.prompt_artifact` and calls `interrupt(prompt)`.
   - Calling `submit` after `begin_task` invokes `PromptHydrator.hydrate` **0 times** when the submission passes validation on the first try (and **1 time** when a repair round is needed), and modifying a target file on disk between `begin_task` and `submit` does not cause a hydration failure on `submit`.
2. **Diagnostics hydrated before existing files (`L10`)**:
   - `PromptHydrator.hydrate` loads `specification`, `context`, `engineering_guidance`, `validation_feedback`, and `generation_feedback` **before** loading `existing_files`. If `existing_files` would exceed the remaining `max_context_bytes` budget, `validation_feedback` and `generation_feedback` are already loaded and preserved.
3. **Only engineering (`*-dev`) skills injected, and missing skills raise `ArtifactError` (`K2`, `C6c`)**:
   - `PromptHydrator.hydrate` loads only `TARGET_SKILLS[state.target]` (never `sdd-implement-<tier>`).
   - `_load_skill` catches `OSError` (including `FileNotFoundError`) and raises `ArtifactError`, and falls back to `/home/htxzz77/Projects/skills` or packaged data when `project_root / "skills"` is absent.
4. **`cancel_task` and `submit` crash recovery (`C6b`, `L9`)**:
   - `cancel_task(workspace, run_id)` aborts a `pending` or `terminal` run, restores changed files (`restore_tree` + `original_files`), records `outcome="failed"` and `phase="finished"`, and releases the active-workspace slot so a new `begin_task` on the same worktree succeeds immediately.
   - `submit` acquires the workspace lock before checking `record.phase`, and on any unexpected exception transitions the run to `finished` (`outcome="failed"`) after attempting rollback so the worktree is never permanently stranded.
5. **Reconciled rollback and `OSError` safety (`L7`, `L8`)**:
   - On a failed run, `finish_task` captures `finish_tree` and `scope_report` (or combines `submitted` target files with `finish_tree`) so `scope_report["changes"]` accurately reflects what the run touched, and any `RollbackError`/`ArtifactError`/`OSError` during restoration sets `report["restored"] = False` and `report["rollback_error"]` while still marking `phase = "finished"`.
6. **Narrow `_step` lock error handling (`L6`)**:
   - `SddEngine._step` catches `WorkspaceBusyError` (re-raising it as `WorkspaceBusyError`) and `ArtifactError` **only** around acquiring `workspaces.lock(workspace_id)`, never relabeling an `ArtifactError` from `graph.invoke` as `"the workspace could not be locked"`.

## Implementation plan

1. In [`sdd_engine/models.py`](../models.py):
   - Add `prompt_artifact: ArtifactRef | None = None` to `GraphState` and `GraphPatch`.
   - Remove `RouteDecision` ([`models.py:302-305`](../models.py#L302-L305)) or keep it as a deprecated alias while routing functions return `Literal[...]` (`L5`).
   - Add `untrusted_inputs_notice: str` to `GenerationPrompt` noting that `existing_files`, `referenced_context`, and `validation_feedback` contain untrusted workspace/command output (`K7`).
2. In [`sdd_engine/guidance.py`](../guidance.py):
   - Change line 73 from `skills = (f"sdd-implement-{state.tier.value}", *TARGET_SKILLS[state.target])` to `skills = TARGET_SKILLS[state.target]` (`K2`).
   - Move lines 91–96 (`validation_feedback` and `generation_feedback` loading) **above** lines 83–89 (`existing_files` loading) (`L10`).
   - In `_load_skill` ([`guidance.py:112-123`](../guidance.py#L112-L123)), wrap `resolve(strict=True)` and `read_text(encoding="utf-8")` in `try ... except OSError as error: raise ArtifactError(f"could not load skill {skill_name!r}") from error` (`C6c`).
3. In [`sdd_engine/graph.py`](../graph.py):
   - Define `CHECKPOINT_ALLOWLIST: list[tuple[str, str]] = [(kind.__module__, kind.__name__) for kind in CHECKPOINT_TYPES]` once and use it in both `checkpoint_serializer()` and `build_graph()` (`Q3`).
   - In `EngineDependencies`, support clear budget names (`max_generation_attempts: int = 3`, `max_validation_attempts: int = 3`, plus properties/aliases `max_submissions_per_round` and `max_repair_rounds`, and `max_total_submissions: int = 9`) (`L3`).
   - Extract module-level node functions (`L1`, `L2`, `Q8`):
     - `hydrate_node(raw_state: GraphState, *, dependencies: EngineDependencies) -> dict[str, object]`: runs `dependencies.prompts.hydrate(state)`, stores `prompt_ref = dependencies.artifacts.put_model(prompt)`, and returns `_validated_patch(state, GraphPatch(prompt_artifact=prompt_ref))`. On `ArtifactError`, records `FailureReport(category="hydration", ...)` and sets `status=RunStatus.FAILED`.
     - `await_submission_node(raw_state: GraphState, *, dependencies: EngineDependencies) -> dict[str, object]`: loads `prompt = dependencies.artifacts.get_model(state.prompt_artifact, GenerationPrompt, limits.MAX_CONTEXT_BYTES)` and calls `submission = interrupt(prompt.model_dump(mode="json"))`, then validates `GenerationOutput` and `target_files` (or passes to `check_contract_node`), snapshots and writes files (`apply_files_node`), and stores `generated_artifact`. Because `hydrate_node` is a separate preceding node, LangGraph's resume of `await_submission_node` only reads the immutable `state.prompt_artifact` from SQLite and never re-reads the worktree!
     - `validate_node(raw_state: GraphState, *, dependencies: EngineDependencies) -> dict[str, object]`: validates using `state.target` (`dependencies.validator.validate(state.target, workspace)`), storing `validation_report` and `validation_feedback`.
     - `rollback_node(raw_state: GraphState, *, dependencies: EngineDependencies) -> dict[str, object]`: restores `state.original_files` in reverse order.
   - Replace the 18-target outer loop in `build_graph` with a single `StateGraph(GraphState)`:
     - `START -> "hydrate" -> "await_submission" -> ...` with `Literal["hydrate", "validate", "rollback", "__end__"]` routing functions.
   - Fix `SddEngine._step` ([`graph.py:137-156`](../graph.py#L137-L156)) so lock errors and `graph.invoke` errors are handled separately (`L6`).
   - In `_validated_patch(state: GraphState, patch: GraphPatch)` ([`graph.py:423-428`](../graph.py#L423-L428)), remove the redundant `GraphPatch.model_validate(patch)` no-op (`L4`).
4. In [`sdd_engine/service.py`](../service.py), [`sdd_engine/mcp_server.py`](../mcp_server.py), and [`sdd_engine/cli.py`](../cli.py):
   - Add `cancel_task(workspace: str, run_id: str) -> dict[str, object]` (`C6b`):
     - Verify worktree ownership via `_run_store`.
     - If `record.phase == RunPhase.FINISHED`, return `get_run_report(workspace, run_id)`.
     - Capture `finish_tree`, compute `scope_report`, restore `original_files` (from `snapshots`/`state`) and `restore_tree(root, record.start_tree, finish_tree, record.head)`, update run to `phase=RunPhase.FINISHED, outcome=RunStatus.FAILED.value, prompt=None`, and return `get_run_report(workspace, run_id)`.
   - Expose `cancel_task` as an `@implementer.tool()` in `mcp_server.py` and in `cli.py` choices.
   - In `submit`, wrap `_engine(...).submit(...)` in `try ... except Exception:` that marks the run failed/finished and rolls back on unexpected runtime errors so the worktree is never left locked in `pending`.
5. In [`pyproject.toml`](../../pyproject.toml#L25-L26), configure setuptools package data or fallback skill path resolution so installed wheels can locate the engineering guides (`C6c`).

## Verification

- Run `uv run pytest tests/test_graph.py`:
  - Verify `PromptHydrator.hydrate` is called once during `begin_task` and 0 times during a passing `submit`.
  - Verify `cancel_task` on a `pending` run restores any worktree edits, sets `phase == "finished"` and `outcome == "failed"`, and allows a subsequent `begin_task` on the same worktree.
  - Verify unit tests calling `hydrate_node`, `validate_node`, and `rollback_node` directly with fake stores/runners cover: hydration failure, validation infrastructure failure, exhausted generation attempts, exhausted validation attempts, and rollback failure (`Q8`).
  - Verify `PromptHydrator.hydrate` loads `validation_feedback` and `generation_feedback` even when `existing_files` is near the 2 MB limit (`L10`).
- Run `uv run ruff check sdd_engine tests`, `uv run ruff format --check sdd_engine tests`, and `uv run mypy sdd_engine tests`.

## Open decisions and sources

- **Synchronous vs. asynchronous `submit` (`C6d`)**: Keep `submit` synchronous by default so existing MCP callers and tests receive the next `prompt` or `state` directly, while lowering `ValidationProfile.timeout_seconds` default from `600` to `120` seconds (still configurable up to `3600`).
