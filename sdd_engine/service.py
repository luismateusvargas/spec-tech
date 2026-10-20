"""Agent-neutral task API shared by the MCP server and command-line client."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from sdd_engine.artifacts import WorkspaceRegistry
from sdd_engine.errors import (
    ProfileError,
    RunStateError,
    SpecContractError,
    WorkspaceMismatchError,
)
from sdd_engine.graph import EngineDependencies, SddEngine, build_engine, checkpoint_serializer
from sdd_engine.guidance import PromptHydrator
from sdd_engine.limits import MAX_REPORT_BYTES
from sdd_engine.models import (
    FailureReport,
    GenerationOutput,
    GraphInput,
    GraphState,
    OriginalFile,
    RunPhase,
    RunStatus,
    Target,
    Tier,
    ValidationReport,
)
from sdd_engine.paths import canonical_relative_path
from sdd_engine.scope import (
    committed_blob,
    head,
    restore_tree,
    scope_report,
    tree_paths,
    worktree_tree,
)
from sdd_engine.store import ProjectStore, RunRecord, StoredProfile, project_database
from sdd_engine.validation import (
    DockerCommandRunner,
    NativeValidator,
    ValidationProfile,
    standard_commands,
)

# The header block runs from the top of the spec to its first level-two heading.
_SECTION_HEADING = re.compile(r"^## ", re.MULTILINE)
# Horizontal whitespace only, so a key never takes its value from the following line.
_STATUS_LINE = re.compile(r"^(?i:status):[ \t]*(?P<value>[^\r\n]*?)[ \t\r]*$", re.MULTILINE)
_TARGET_FILES_LINE = re.compile(
    r"^(?i:target files):[ \t]*(?P<value>[^\r\n]*?)[ \t\r]*$", re.MULTILINE
)


def parse_spec_header(spec_text: str) -> tuple[str, ...] | None:
    """Require a ready spec and return the `Target files:` its header declares, if any.

    Only the header block counts, so a `status:` line inside a later section is ignored.

    # Errors

    Raises `SpecContractError` unless the header has exactly one `Status: ready` line, or
    when its `Target files:` line is repeated, empty, or names an unsafe or repeated path.
    """
    section = _SECTION_HEADING.search(spec_text)
    header = spec_text if section is None else spec_text[: section.start()]
    statuses = [match.group("value") for match in _STATUS_LINE.finditer(header)]
    if statuses != ["ready"]:
        raise SpecContractError(
            f"task specification header must declare 'Status: ready', found {statuses}"
        )
    declared = [match.group("value") for match in _TARGET_FILES_LINE.finditer(header)]
    if not declared:
        return None
    if len(declared) > 1:
        raise SpecContractError("task specification header repeats 'Target files:'")
    paths = [item.strip().strip("`").strip() for item in declared[0].split(",")]
    if not any(paths):
        raise SpecContractError("task specification header has an empty 'Target files:' line")
    try:
        files = tuple(canonical_relative_path(path) for path in paths)
    except ValueError as error:
        raise SpecContractError(f"task specification 'Target files:': {error}") from error
    if len(set(files)) != len(files):
        raise SpecContractError("task specification 'Target files:' repeats a path")
    return files


def _store_for(workspace: str) -> tuple[Path, ProjectStore]:
    root = Path(workspace).expanduser().resolve(strict=True)
    return root, ProjectStore(project_database(root))


def _run_store(workspace: str, run_id: str) -> tuple[Path, ProjectStore, RunRecord]:
    root, store = _store_for(workspace)
    record = store.run(run_id)
    if record.workspace.resolve() != root:
        raise WorkspaceMismatchError(
            f"run {run_id!r} belongs to worktree {record.workspace}, not {root}"
        )
    return root, store, record


def _current_profile(store: ProjectStore, record: RunRecord) -> StoredProfile:
    """Reject a profile changed since this run began."""
    stored = store.get_profile_record(record.request.target)
    if (stored.revision, stored.digest) != (record.profile_revision, record.profile_digest):
        raise ProfileError("validation profile changed during the active run")
    return stored


def _engine(
    store: ProjectStore,
    workspace: Path,
    run_id: str,
    stored_profile: StoredProfile,
    connection: sqlite3.Connection,
) -> SddEngine:
    registry = WorkspaceRegistry({run_id: workspace})
    dependencies = EngineDependencies(
        artifacts=store,
        workspaces=registry,
        prompts=PromptHydrator(Path(__file__).resolve().parents[1], store, registry),
        validator=NativeValidator(
            {stored_profile.target: stored_profile.profile},
            DockerCommandRunner(),
            {stored_profile.target: (stored_profile.revision, stored_profile.digest)},
        ),
    )
    return build_engine(dependencies, SqliteSaver(connection, serde=checkpoint_serializer()))


def configure_profile(workspace: str, target: str, profile: dict[str, object]) -> dict[str, object]:
    """Set one validation profile through the separate administrator interface."""
    root, store = _store_for(workspace)
    parsed_target = Target(target)
    if "commands" not in profile:
        profile = {
            **profile,
            "commands": [
                command.model_dump(mode="json")
                for command in standard_commands(parsed_target, root)
            ],
        }
    revision = store.set_profile(parsed_target, ValidationProfile.model_validate(profile))
    return {"target": parsed_target.value, "revision": revision}


def get_profile(workspace: str, target: str) -> dict[str, object]:
    """Read the active administrator-configured validation profile."""
    _, store = _store_for(workspace)
    return store.get_profile(Target(target)).model_dump(mode="json")


def begin_task(
    workspace: str,
    *,
    tier: str,
    target: str,
    model: str,
    spec: str | None = None,
    spec_path: str | None = None,
    target_files: list[str] | None = None,
    context: list[str] | None = None,
) -> dict[str, object]:
    """Record a planned model and pause the engine at its first implementer prompt.

    # Arguments

    `spec_path` binds the run to a spec committed at `HEAD` and unchanged in the worktree;
    `spec`, when also given, must equal that text. Without `spec_path`, `spec` is the spec
    text. `target_files` may be omitted when the spec header declares `Target files:`, and
    must name the same paths when both are given.

    # Errors

    Raises `SpecContractError` when the spec is not ready, cannot be bound to `HEAD`, or
    disagrees with the given text or target files.
    """
    if not model.strip():
        raise ValueError("the planned implementer model is required")
    root, store = _store_for(workspace)
    spec_blob: str | None = None
    if spec_path is not None:
        spec_blob, spec_text = committed_blob(root, spec_path)
        spec_path = canonical_relative_path(spec_path)
        if spec is not None and spec != spec_text:
            raise SpecContractError(f"spec differs from {spec_path!r} committed at HEAD")
    elif spec is not None:
        spec_text = spec
    else:
        raise SpecContractError("begin_task requires spec or spec_path")
    declared_files = parse_spec_header(spec_text)
    if target_files is None:
        if declared_files is None:
            raise SpecContractError(
                "target_files is required when the spec header declares no 'Target files:'"
            )
        target_files = list(declared_files)
    elif declared_files is not None:
        try:
            requested = {canonical_relative_path(path) for path in target_files}
        except ValueError as error:
            raise SpecContractError(f"target_files: {error}") from error
        if requested != set(declared_files):
            raise SpecContractError(
                f"target_files must match the spec header's 'Target files:' {list(declared_files)}"
            )
    parsed_target = Target(target)
    stored_profile = store.get_profile_record(parsed_target)
    run_id = uuid.uuid4().hex
    specification = store.put(spec_text.encode("utf-8"), "text/markdown")
    references = tuple(store.put(item.encode("utf-8"), "text/plain") for item in (context or []))
    request = GraphInput(
        run_id=run_id,
        workspace_id=run_id,
        target=parsed_target,
        tier=Tier(tier),
        specification=specification,
        target_files=tuple(target_files),
        context=references,
    )
    store.insert_run(
        run_id,
        root,
        model,
        request,
        head(root),
        worktree_tree(root),
        stored_profile.revision,
        stored_profile.digest,
        spec_path,
        spec_blob,
    )
    try:
        with store.connect() as connection:
            result = _engine(store, root, run_id, stored_profile, connection).begin(request)
    except Exception:
        # An unavailable workspace or broken checkpoint must not strand the unique
        # active-run slot. The original error still reaches the caller.
        store.update_run(run_id, phase=RunPhase.FINISHED.value, outcome=RunStatus.FAILED.value)
        raise
    _persist_step(store, run_id, result)
    return {"run_id": run_id, "model": model, **result}


def submit(workspace: str, run_id: str, files: dict[str, object]) -> dict[str, object]:
    """Resume a pending run with the implementer's structured generation result."""
    root, store, _ = _run_store(workspace, run_id)
    registry = WorkspaceRegistry({run_id: root})
    with registry.lock(run_id):
        record = store.run(run_id)
        if record.phase is not RunPhase.PENDING or record.prompt is None:
            raise RunStateError("run is not awaiting a submission")
        stored_profile = _current_profile(store, record)
        try:
            generated = GenerationOutput.model_validate(files)
        except ValueError:
            generated = None
        try:
            if generated is not None:
                previous = set(record.submitted)
                previous.update(item.path for item in generated.files)
                store.update_run(run_id, submitted=json.dumps(sorted(previous)))
            with store.connect() as connection:
                result = _engine(store, root, run_id, stored_profile, connection).submit(
                    run_id, run_id, files, workspace_locked=True
                )
            _persist_step(store, run_id, result)
        except Exception:
            _finalize_run(root, store, store.run(run_id), failed=True)
            raise
    return {"run_id": run_id, **result}


def _persist_step(store: ProjectStore, run_id: str, result: dict[str, object]) -> None:
    if "prompt" in result:
        store.update_run(run_id, prompt=json.dumps(result["prompt"]), phase=RunPhase.PENDING.value)
        return
    state = GraphState.model_validate(result["state"])
    store.save_snapshots(
        run_id, [original.model_dump(mode="json") for original in state.original_files]
    )
    store.update_run(
        run_id,
        state=state.model_dump_json(),
        prompt=None,
        outcome=state.status.value,
        phase=RunPhase.TERMINAL.value,
    )


def finish_task(workspace: str, run_id: str) -> dict[str, object]:
    """Diff the run's Git trees and restore all changes after a failed run."""
    root, store, _ = _run_store(workspace, run_id)
    with WorkspaceRegistry({run_id: root}).lock(run_id):
        record = store.run(run_id)
        if record.phase is RunPhase.FINISHED:
            return get_run_report(workspace, run_id)
        _current_profile(store, record)
        if record.phase is not RunPhase.TERMINAL:
            raise RunStateError("run is still awaiting an implementer submission")
        _finalize_run(root, store, record, failed=record.outcome is RunStatus.FAILED)
    return get_run_report(workspace, run_id)


def cancel_task(workspace: str, run_id: str) -> dict[str, object]:
    """Abort an owned run, restore its worktree, and free its active slot."""
    root, store, _ = _run_store(workspace, run_id)
    with WorkspaceRegistry({run_id: root}).lock(run_id):
        record = store.run(run_id)
        if record.phase is not RunPhase.FINISHED:
            _finalize_run(root, store, record, failed=True)
    return get_run_report(workspace, run_id)


def _restore_originals(
    root: Path, store: ProjectStore, record: RunRecord, originals: tuple[OriginalFile, ...]
) -> None:
    """Restore recorded pre-write bytes before the broader Git-tree restoration."""
    registry = WorkspaceRegistry({record.run_id: root})
    for original in reversed(originals):
        content = (
            None
            if original.content is None
            else store.get(original.content, original.content.byte_length)
        )
        registry.restore(
            record.run_id, original.path, content, original.mode, original.created_directory
        )


def _finalize_run(root: Path, store: ProjectStore, record: RunRecord, *, failed: bool) -> None:
    """Persist scope and terminal phase even when a restoration step fails."""
    report: dict[str, object] = {"start_tree": record.start_tree, "changes": []}
    finish_tree: str | None = None
    head_changed: bool | None = None
    errors: list[str] = []
    try:
        head_changed = head(root) != record.head
        finish_tree = worktree_tree(root, preserve=tree_paths(root, record.start_tree))
        report = scope_report(
            root,
            record.start_tree,
            finish_tree,
            set(record.submitted),
            set(record.request.target_files),
        )
        report["head_changed"] = head_changed
    except Exception as error:
        # Finalization must record a failed run even when scope inspection fails.
        errors.append(str(error))
    if failed:
        # Graph rollback may have erased a generated file before the final Git diff.
        findings = report.get("changes", [])
        if isinstance(findings, list):
            existing = {item["path"] for item in findings if isinstance(item, dict)}
            for path in sorted(set(record.submitted) & set(record.request.target_files) - existing):
                findings.append({"path": path, "label": "declared", "flags": []})
            findings.sort(key=lambda item: str(item["path"]))
        if head_changed is False:
            try:
                originals = (
                    record.state.original_files
                    if record.state is not None
                    else store.snapshots(record.run_id)
                )
                _restore_originals(root, store, record, originals)
            except Exception as error:
                errors.append(str(error))
        if finish_tree is not None:
            try:
                restore_tree(root, record.start_tree, finish_tree, record.head)
            except Exception as error:
                errors.append(str(error))
        report["restored"] = not errors
        if errors:
            report["rollback_error"] = "; ".join(errors)
    elif errors:
        report["scope_error"] = "; ".join(errors)
    final_state = record.state
    if failed and final_state is not None:
        final_state = final_state.model_copy(update={"status": RunStatus.FAILED})
    store.update_run(
        record.run_id,
        scope_report=json.dumps(report),
        phase=RunPhase.FINISHED.value,
        outcome=RunStatus.FAILED.value
        if failed
        else record.outcome.value
        if record.outcome
        else None,
        state=None if final_state is None else final_state.model_dump_json(),
        prompt=None,
    )


def get_run_report(workspace: str, run_id: str) -> dict[str, object]:
    """Return status, model, validation, failure, and the persisted scope report."""
    _, store, record = _run_store(workspace, run_id)
    response: dict[str, object] = {
        "run_id": run_id,
        "workspace": str(record.workspace),
        "model": record.model,
        "phase": record.phase.value,
        "outcome": None if record.outcome is None else record.outcome.value,
        "prompt": record.prompt,
        "scope_report": record.scope_report,
    }
    if record.state is not None:
        state = record.state
        response["state"] = state.model_dump(mode="json")
        if state.validation_report is not None:
            response["validation_report"] = store.get_model(
                state.validation_report, ValidationReport, MAX_REPORT_BYTES
            ).model_dump(mode="json")
        if state.failure_report is not None:
            response["failure_report"] = store.get_model(
                state.failure_report, FailureReport, MAX_REPORT_BYTES
            ).model_dump(mode="json")
    return response
