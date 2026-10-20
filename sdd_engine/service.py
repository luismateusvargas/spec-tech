"""Agent-neutral task API shared by the MCP server and command-line client."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from sdd_engine.artifacts import ArtifactError, WorkspaceRegistry
from sdd_engine.graph import EngineDependencies, SddEngine, build_engine, checkpoint_serializer
from sdd_engine.guidance import PromptHydrator
from sdd_engine.models import (
    FailureReport,
    GenerationOutput,
    GraphInput,
    GraphState,
    RunStatus,
    Target,
    Tier,
    ValidationReport,
)
from sdd_engine.scope import head, restore_tree, scope_report, tree_paths, worktree_tree
from sdd_engine.store import ProjectStore, project_database
from sdd_engine.validation import DockerCommandRunner, NativeValidator, ValidationProfile

_BLOCKED_SPEC = re.compile(r"^\s*Status\s*:\s*blocked\b", re.IGNORECASE | re.MULTILINE)


def _store_for(workspace: str) -> tuple[Path, ProjectStore]:
    root = Path(workspace).expanduser().resolve(strict=True)
    return root, ProjectStore(project_database(root))


def _run_store(workspace: str, run_id: str) -> tuple[ProjectStore, dict[str, object]]:
    _, store = _store_for(workspace)
    return store, store.run(run_id)


def _engine(
    store: ProjectStore,
    workspace: Path,
    run_id: str,
    target: Target,
    connection: sqlite3.Connection,
) -> SddEngine:
    registry = WorkspaceRegistry({run_id: workspace})
    dependencies = EngineDependencies(
        artifacts=store,
        workspaces=registry,
        prompts=PromptHydrator(Path(__file__).resolve().parents[1], store, registry),
        validator=NativeValidator({target: store.get_profile(target)}, DockerCommandRunner()),
    )
    return build_engine(dependencies, SqliteSaver(connection, serde=checkpoint_serializer()))


def configure_profile(workspace: str, target: str, profile: dict[str, object]) -> dict[str, object]:
    """Set one validation profile through the separate administrator interface."""
    _, store = _store_for(workspace)
    parsed_target = Target(target)
    revision = store.set_profile(parsed_target, ValidationProfile.model_validate(profile))
    return {"target": parsed_target.value, "revision": revision}


def get_profile(workspace: str, target: str) -> dict[str, object]:
    """Read the active administrator-configured validation profile."""
    _, store = _store_for(workspace)
    return store.get_profile(Target(target)).model_dump(mode="json")


def begin_task(
    workspace: str,
    spec: str,
    tier: str,
    target: str,
    target_files: list[str],
    model: str,
    context: list[str] | None = None,
) -> dict[str, object]:
    """Record a planned model and pause the engine at its first implementer prompt."""
    if not model.strip():
        raise ValueError("the planned implementer model is required")
    if _BLOCKED_SPEC.search(spec):
        raise ValueError("cannot implement a task specification with Status: blocked")
    root, store = _store_for(workspace)
    parsed_target = Target(target)
    store.get_profile(parsed_target)
    run_id = uuid.uuid4().hex
    specification = store.put(spec.encode("utf-8"), "text/markdown")
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
    store.insert_run(run_id, root, model, request, head(root), worktree_tree(root))
    try:
        with store.connect() as connection:
            result = _engine(store, root, run_id, parsed_target, connection).begin(request)
    except Exception:
        # An unavailable workspace or broken checkpoint must not strand the unique
        # active-run slot. The original error still reaches the caller.
        store.update_run(run_id, phase="finished", outcome=RunStatus.FAILED.value)
        raise
    _persist_step(store, run_id, result)
    return {"run_id": run_id, "model": model, **result}


def submit(workspace: str, run_id: str, files: dict[str, object]) -> dict[str, object]:
    """Resume a pending run with the implementer's structured generation result."""
    store, row = _run_store(workspace, run_id)
    if row["phase"] != "pending" or row["prompt"] is None:
        raise ArtifactError("run is not awaiting a submission")
    request = GraphInput.model_validate_json(str(row["request"]))
    root = Path(str(row["workspace"]))
    with store.connect() as connection:
        result = _engine(store, root, run_id, request.target, connection).submit(
            run_id, run_id, files
        )
    try:
        generated = GenerationOutput.model_validate(files)
    except ValueError:
        generated = None
    if generated is not None:
        previous = set(json.loads(str(row["submitted"])))
        previous.update(item.path for item in generated.files)
        store.update_run(run_id, submitted=json.dumps(sorted(previous)))
    _persist_step(store, run_id, result)
    return {"run_id": run_id, **result}


def _persist_step(store: ProjectStore, run_id: str, result: dict[str, object]) -> None:
    if "prompt" in result:
        store.update_run(run_id, prompt=json.dumps(result["prompt"]), phase="pending")
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
        phase="terminal",
    )


def finish_task(workspace: str, run_id: str) -> dict[str, object]:
    """Diff the run's Git trees and restore all changes after a failed run."""
    store, row = _run_store(workspace, run_id)
    if row["phase"] == "finished":
        return get_run_report(workspace, run_id)
    if row["phase"] != "terminal":
        raise ArtifactError("run is still awaiting an implementer submission")
    root = Path(str(row["workspace"]))
    start_tree = str(row["start_tree"])
    finish_tree = worktree_tree(root, preserve=tree_paths(root, start_tree))
    request = GraphInput.model_validate_json(str(row["request"]))
    report = scope_report(
        root,
        start_tree,
        finish_tree,
        set(json.loads(str(row["submitted"]))),
        set(request.target_files),
    )
    report["head_changed"] = head(root) != row["head"]
    if row["outcome"] == RunStatus.FAILED.value:
        try:
            restore_tree(root, start_tree, finish_tree, str(row["head"]))
            report["restored"] = True
        except ArtifactError as error:
            report["restored"] = False
            report["rollback_error"] = str(error)
    store.update_run(run_id, scope_report=json.dumps(report), phase="finished")
    return get_run_report(workspace, run_id)


def get_run_report(workspace: str, run_id: str) -> dict[str, object]:
    """Return status, model, validation, failure, and the persisted scope report."""
    store, row = _run_store(workspace, run_id)
    response: dict[str, object] = {
        "run_id": run_id,
        "workspace": row["workspace"],
        "model": row["model"],
        "phase": row["phase"],
        "outcome": row["outcome"],
        "prompt": None if row["prompt"] is None else json.loads(str(row["prompt"])),
        "scope_report": (
            None if row["scope_report"] is None else json.loads(str(row["scope_report"]))
        ),
    }
    if row["state"] is not None:
        state = GraphState.model_validate_json(str(row["state"]))
        response["state"] = state.model_dump(mode="json")
        if state.validation_report is not None:
            response["validation_report"] = store.get_model(
                state.validation_report, ValidationReport, 1_000_000
            ).model_dump(mode="json")
        if state.failure_report is not None:
            response["failure_report"] = store.get_model(
                state.failure_report, FailureReport, 1_000_000
            ).model_dump(mode="json")
    return response
