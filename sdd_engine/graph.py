"""Single LangGraph workflow with bounded submission and validation repair loops."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass
from functools import partial
from typing import Any, Literal, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.errors import GraphInterrupt
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt
from pydantic import ValidationError

from sdd_engine.artifacts import (
    ArtifactError,
    ArtifactStore,
    WorkspaceBusyError,
    WorkspaceRegistry,
)
from sdd_engine.guidance import PromptHydrator
from sdd_engine.limits import (
    MAX_DIAGNOSTIC_CHARS,
    MAX_FAILURE_REPORT_BYTES,
    MAX_GENERATED_ARTIFACT_BYTES,
    MAX_ORIGINAL_FILE_BYTES,
    MAX_PROMPT_ARTIFACT_BYTES,
)
from sdd_engine.models import (
    ArtifactRef,
    FailureReport,
    GenerationOutput,
    GenerationPrompt,
    GraphInput,
    GraphPatch,
    GraphState,
    OriginalFile,
    RunStatus,
    Target,
    Tier,
    ValidationReport,
)
from sdd_engine.validation import NativeValidator, ValidationInfrastructureError

# Node events carry identifiers, counters, statuses, and timings; never artifact content.
logger = logging.getLogger(__name__)

# Engine types that graph state stores in checkpoints. LangGraph warns on, and in strict
# msgpack mode blocks, deserializing any type outside its allowlist.
CHECKPOINT_TYPES: tuple[type, ...] = (
    ArtifactRef,
    GraphState,
    OriginalFile,
    RunStatus,
    Target,
    Tier,
)
CHECKPOINT_ALLOWLIST = [(kind.__module__, kind.__name__) for kind in CHECKPOINT_TYPES]


def checkpoint_serializer() -> JsonPlusSerializer:
    """Return a checkpoint serializer that allows only LangGraph's safe types and the engine's.

    Pass it as the `serde` of a checkpointer given to `build_engine`.
    """
    return JsonPlusSerializer(allowed_msgpack_modules=CHECKPOINT_ALLOWLIST)


@dataclass(frozen=True)
class EngineDependencies:
    """Infrastructure and retry limits shared by graph nodes."""

    artifacts: ArtifactStore
    workspaces: WorkspaceRegistry
    prompts: PromptHydrator
    validator: NativeValidator
    max_generation_attempts: int = 3
    max_validation_attempts: int = 3
    max_total_submissions: int = 9

    def __post_init__(self) -> None:
        """Reject retry configurations that can create unbounded graph loops."""
        if not 1 <= self.max_generation_attempts <= 10:
            raise ValueError("max_generation_attempts must be between 1 and 10")
        if not 1 <= self.max_validation_attempts <= 10:
            raise ValueError("max_validation_attempts must be between 1 and 10")
        if not 1 <= self.max_total_submissions <= 100:
            raise ValueError("max_total_submissions must be between 1 and 100")

    @property
    def max_submissions_per_round(self) -> int:
        """Name the contract retry budget for one validation round."""
        return self.max_generation_attempts

    @property
    def max_repair_rounds(self) -> int:
        """Name the number of native validation attempts."""
        return self.max_validation_attempts


def build_graph(
    dependencies: EngineDependencies,
    checkpointer: BaseCheckpointSaver[str] | None = None,
) -> CompiledStateGraph[GraphState, None, GraphState, GraphState]:
    """Compile one target-independent graph with a separate hydration checkpoint."""
    graph: StateGraph[GraphState, None, GraphState, GraphState] = StateGraph(GraphState)
    for name, node in (
        ("hydrate", hydrate_node),
        ("await_submission", await_submission_node),
        ("check_contract", check_contract_node),
        ("apply_files", apply_files_node),
        ("validate", validate_node),
        ("rollback", rollback_node),
    ):
        _add_strict_node(
            graph, name, _observed(name, partial(node, dependencies=dependencies), dependencies)
        )
    graph.add_edge(START, "hydrate")
    graph.add_conditional_edges("hydrate", _route_after_hydration)
    graph.add_conditional_edges("await_submission", _route_after_submission)
    graph.add_conditional_edges("check_contract", _route_after_contract)
    graph.add_conditional_edges("apply_files", _route_after_application)
    graph.add_conditional_edges("validate", _route_after_validation)
    graph.add_edge("rollback", END)
    if checkpointer is not None:
        # Extends an explicit or strict-mode allowlist; a permissive serializer is unchanged.
        checkpointer = checkpointer.with_allowlist(CHECKPOINT_ALLOWLIST)
    return graph.compile(checkpointer=checkpointer)


def build_engine(
    dependencies: EngineDependencies,
    checkpointer: BaseCheckpointSaver[str] | None = None,
) -> SddEngine:
    """Build a public engine wrapper around the compiled LangGraph application."""
    return SddEngine(build_graph(dependencies, checkpointer), dependencies)


class SddEngine:
    """Validated entry and exit boundary for one LangGraph SDD run."""

    def __init__(
        self,
        graph: CompiledStateGraph[GraphState, None, GraphState, GraphState],
        dependencies: EngineDependencies,
    ) -> None:
        """Wrap a compiled graph while keeping invocation contracts explicit."""
        self._graph = graph
        self._dependencies = dependencies

    def begin(self, request: GraphInput) -> dict[str, object]:
        """Start a run and return its first agent prompt or terminal state."""
        validated_request = GraphInput.model_validate(request)
        initial_state = GraphState.model_validate(validated_request.model_dump())
        return self._step(initial_state, validated_request.workspace_id, validated_request.run_id)

    def submit(
        self, run_id: str, workspace_id: str, response: object, *, workspace_locked: bool = False
    ) -> dict[str, object]:
        """Resume a paused run with the implementer's structured file submission."""
        return self._step(Command(resume=response), workspace_id, run_id, workspace_locked)

    def _step(
        self,
        value: GraphState | Command[Any],
        workspace_id: str,
        run_id: str,
        workspace_locked: bool = False,
    ) -> dict[str, object]:
        """Advance the graph under a worktree lock and expose only prompt or state."""
        with ExitStack() as stack:
            if not workspace_locked:
                try:
                    stack.enter_context(self._dependencies.workspaces.lock(workspace_id))
                except WorkspaceBusyError:
                    raise
                except ArtifactError as error:
                    raise ArtifactError("the workspace could not be locked") from error
            result = self._graph.invoke(
                value,
                config={"configurable": {"thread_id": run_id}},
            )
        if "__interrupt__" in result:
            values = result["__interrupt__"]
            return {
                "prompt": GenerationPrompt.model_validate(values[0].value).model_dump(mode="json")
            }
        return {"state": GraphState.model_validate(result).model_dump(mode="json")}


def _record_failure(
    dependencies: EngineDependencies, category: str, summary: str, error: Exception | None = None
) -> ArtifactRef:
    """Store bounded failure detail outside checkpoint state."""
    return dependencies.artifacts.put_model(
        FailureReport(
            category=category,
            summary=summary,
            diagnostics="" if error is None else str(error)[:MAX_DIAGNOSTIC_CHARS],
        )
    )


def _snapshot_original(
    dependencies: EngineDependencies, workspace_id: str, path: str
) -> OriginalFile:
    """Store a file's pre-write bytes before changing it."""
    snapshot = dependencies.workspaces.snapshot(workspace_id, path, MAX_ORIGINAL_FILE_BYTES)
    content = (
        None
        if snapshot.content is None
        else dependencies.artifacts.put(snapshot.content, "application/octet-stream")
    )
    return OriginalFile(
        path=path,
        content=content,
        mode=snapshot.mode,
        created_directory=snapshot.created_directory,
    )


def hydrate_node(raw_state: GraphState, *, dependencies: EngineDependencies) -> dict[str, object]:
    """Store the complete prompt before the interrupting node starts."""
    state = _validate_state(raw_state)
    try:
        prompt_ref = dependencies.artifacts.put_model(dependencies.prompts.hydrate(state))
    except ArtifactError as error:
        failure_ref = _record_failure(
            dependencies,
            "hydration",
            "Generation inputs could not be loaded within their limits.",
            error,
        )
        return _validated_patch(
            state,
            GraphPatch(prompt_artifact=None, failure_report=failure_ref, status=RunStatus.FAILED),
        )
    return _validated_patch(state, GraphPatch(prompt_artifact=prompt_ref))


def await_submission_node(
    raw_state: GraphState, *, dependencies: EngineDependencies
) -> dict[str, object]:
    """Interrupt with a frozen prompt and validate the resumed payload."""
    state = _validate_state(raw_state)
    if state.prompt_artifact is None:
        failure_ref = _record_failure(
            dependencies, "missing_prompt", "Submission cannot proceed without a hydrated prompt."
        )
        return _validated_patch(
            state, GraphPatch(failure_report=failure_ref, status=RunStatus.FAILED)
        )
    prompt = dependencies.artifacts.get_model(
        state.prompt_artifact, GenerationPrompt, MAX_PROMPT_ARTIFACT_BYTES
    )
    submitted = interrupt(prompt.model_dump(mode="json"))
    attempt = state.generation_attempts + 1
    try:
        generated = GenerationOutput.model_validate(submitted)
    except (ValidationError, ValueError) as error:
        failures = state.generation_failures + 1
        failure_ref = _record_failure(
            dependencies,
            "generation_contract",
            "Generated output did not satisfy its strict Pydantic contract.",
            error,
        )
        return _validated_patch(
            state,
            GraphPatch(
                generation_attempts=attempt,
                generation_failures=failures,
                failure_report=failure_ref,
                status=_contract_retry_status(dependencies, attempt, failures),
            ),
        )
    generated_ref = dependencies.artifacts.put_model(generated)
    return _validated_patch(
        state,
        GraphPatch(
            generated_artifact=generated_ref,
            generation_attempts=attempt,
            status=RunStatus.GENERATED,
        ),
    )


def check_contract_node(
    raw_state: GraphState, *, dependencies: EngineDependencies
) -> dict[str, object]:
    """Reject generated paths outside this run's approved target list."""
    state = _validate_state(raw_state)
    if state.generated_artifact is None:
        failure_ref = _record_failure(
            dependencies, "missing_generation", "The submission has no generated artifact."
        )
        return _validated_patch(
            state, GraphPatch(failure_report=failure_ref, status=RunStatus.FAILED)
        )
    generated = dependencies.artifacts.get_model(
        state.generated_artifact, GenerationOutput, MAX_GENERATED_ARTIFACT_BYTES
    )
    undeclared = [item.path for item in generated.files if item.path not in state.target_files]
    if not undeclared:
        return _validated_patch(state, GraphPatch(status=RunStatus.GENERATED))
    failures = state.generation_failures + 1
    failure_ref = _record_failure(
        dependencies,
        "generation_contract",
        "Generated output includes paths outside the approved target files.",
        ValueError(f"generated files are not approved target paths: {undeclared}"),
    )
    return _validated_patch(
        state,
        GraphPatch(
            generation_failures=failures,
            failure_report=failure_ref,
            status=_contract_retry_status(dependencies, state.generation_attempts, failures),
        ),
    )


def apply_files_node(
    raw_state: GraphState, *, dependencies: EngineDependencies
) -> dict[str, object]:
    """Snapshot and write each approved whole file."""
    state = _validate_state(raw_state)
    if state.generated_artifact is None:
        failure_ref = _record_failure(
            dependencies, "missing_generation", "Files cannot be applied without a submission."
        )
        return _validated_patch(
            state, GraphPatch(failure_report=failure_ref, status=RunStatus.FAILED)
        )
    generated = dependencies.artifacts.get_model(
        state.generated_artifact, GenerationOutput, MAX_GENERATED_ARTIFACT_BYTES
    )
    original_files = state.original_files
    try:
        for item in generated.files:
            if all(original.path != item.path for original in original_files):
                original_files = (
                    *original_files,
                    _snapshot_original(dependencies, state.workspace_id, item.path),
                )
            dependencies.workspaces.write_text(state.workspace_id, item.path, item.content)
    except (ArtifactError, OSError) as error:
        failure_ref = _record_failure(
            dependencies, "workspace_write", "A generated file could not be written.", error
        )
        return _validated_patch(
            state,
            GraphPatch(
                original_files=original_files, failure_report=failure_ref, status=RunStatus.FAILED
            ),
        )
    return _validated_patch(
        state,
        GraphPatch(
            original_files=original_files,
            failure_report=None,
            generation_failures=0,
            status=RunStatus.GENERATED,
        ),
    )


def validate_node(raw_state: GraphState, *, dependencies: EngineDependencies) -> dict[str, object]:
    """Run native checks for the target recorded in graph state."""
    state = _validate_state(raw_state)
    if state.generated_artifact is None:
        failure_ref = _record_failure(
            dependencies, "missing_generation", "Validation cannot run before generation."
        )
        return _validated_patch(
            state, GraphPatch(failure_report=failure_ref, status=RunStatus.FAILED)
        )
    try:
        generated = dependencies.artifacts.get_model(
            state.generated_artifact, GenerationOutput, MAX_GENERATED_ARTIFACT_BYTES
        )
        workspace = dependencies.workspaces.get(state.workspace_id)
    except ArtifactError as error:
        failure_ref = _record_failure(
            dependencies,
            "artifact_contract",
            "The generated artifact or workspace is unavailable.",
            error,
        )
        return _validated_patch(
            state, GraphPatch(failure_report=failure_ref, status=RunStatus.FAILED)
        )
    if any(item.path not in state.target_files for item in generated.files):
        failure_ref = _record_failure(
            dependencies, "artifact_contract", "A stored generated file is outside approved paths."
        )
        return _validated_patch(
            state, GraphPatch(failure_report=failure_ref, status=RunStatus.FAILED)
        )
    try:
        report = dependencies.validator.validate(state.target, workspace)
    except ValidationInfrastructureError as error:
        failure_ref = _record_failure(
            dependencies, "validation_infrastructure", "Native checks could not be executed.", error
        )
        return _validated_patch(
            state, GraphPatch(failure_report=failure_ref, status=RunStatus.FAILED)
        )
    report_ref = dependencies.artifacts.put_model(report)
    next_attempt = state.validation_attempts + 1
    if report.passed:
        return _validated_patch(
            state,
            GraphPatch(
                validation_report=report_ref,
                failure_report=None,
                validation_feedback=None,
                validation_attempts=next_attempt,
                status=RunStatus.VALIDATED,
            ),
        )
    failure_ref = dependencies.artifacts.put_model(
        FailureReport(
            category="native_validation", summary=report.summary, diagnostics=_format_report(report)
        )
    )
    status = (
        RunStatus.VALIDATION_FAILED
        if next_attempt < dependencies.max_repair_rounds
        and state.generation_attempts < dependencies.max_total_submissions
        else RunStatus.FAILED
    )
    return _validated_patch(
        state,
        GraphPatch(
            validation_report=report_ref,
            failure_report=failure_ref,
            validation_feedback=failure_ref,
            validation_attempts=next_attempt,
            status=status,
        ),
    )


def rollback_node(raw_state: GraphState, *, dependencies: EngineDependencies) -> dict[str, object]:
    """Restore recorded originals; the service also restores all Git-tree changes."""
    state = _validate_state(raw_state)
    try:
        for original in reversed(state.original_files):
            content = (
                None
                if original.content is None
                else dependencies.artifacts.get(original.content, MAX_ORIGINAL_FILE_BYTES)
            )
            dependencies.workspaces.restore(
                state.workspace_id,
                original.path,
                content,
                original.mode,
                original.created_directory,
            )
    except (ArtifactError, OSError) as error:
        cause = (
            "unknown"
            if state.failure_report is None
            else f"failure report {state.failure_report.digest}"
        )
        failure_ref = _record_failure(
            dependencies,
            "rollback",
            "The run failed and its workspace changes could not be fully restored.",
            RuntimeError(f"{error}\n\nOriginal failure: {cause}"),
        )
        return _validated_patch(
            state, GraphPatch(failure_report=failure_ref, status=RunStatus.FAILED)
        )
    return _validated_patch(state, GraphPatch(workspace_restored=True))


def _contract_retry_status(
    dependencies: EngineDependencies, attempt: int, failures: int
) -> RunStatus:
    """Keep both per-round and whole-run submission counts bounded."""
    if (
        failures >= dependencies.max_submissions_per_round
        or attempt >= dependencies.max_total_submissions
    ):
        return RunStatus.FAILED
    return RunStatus.REFINEMENT_REQUIRED


def _route_on_failure(state: GraphState) -> Literal["rollback", "__end__"]:
    """Restore recorded writes before ending a failed run."""
    return "rollback" if state.status is RunStatus.FAILED and state.original_files else "__end__"


def _route_after_hydration(
    raw_state: GraphState,
) -> Literal["await_submission", "rollback", "__end__"]:
    """Await input only after a prompt was stored successfully."""
    state = _validate_state(raw_state)
    if state.status is RunStatus.FAILED or state.prompt_artifact is None:
        return _route_on_failure(state)
    return "await_submission"


def _route_after_submission(
    raw_state: GraphState,
) -> Literal["check_contract", "hydrate", "rollback", "__end__"]:
    """Send valid payloads to the path contract and invalid ones to repair."""
    state = _validate_state(raw_state)
    if state.status is RunStatus.GENERATED:
        return "check_contract"
    if state.status is RunStatus.REFINEMENT_REQUIRED:
        return "hydrate"
    return _route_on_failure(state)


def _route_after_contract(
    raw_state: GraphState,
) -> Literal["apply_files", "hydrate", "rollback", "__end__"]:
    """Write approved files or ask for a bounded correction."""
    state = _validate_state(raw_state)
    if state.status is RunStatus.GENERATED:
        return "apply_files"
    if state.status is RunStatus.REFINEMENT_REQUIRED:
        return "hydrate"
    return _route_on_failure(state)


def _route_after_application(
    raw_state: GraphState,
) -> Literal["validate", "rollback", "__end__"]:
    """Validate only after every file was applied."""
    state = _validate_state(raw_state)
    return "validate" if state.status is RunStatus.GENERATED else _route_on_failure(state)


def _route_after_validation(
    raw_state: GraphState,
) -> Literal["hydrate", "rollback", "__end__"]:
    """Repair failed checks or finish the bounded run."""
    state = _validate_state(raw_state)
    if state.status is RunStatus.VALIDATION_FAILED:
        return "hydrate"
    if state.status is RunStatus.VALIDATED:
        return "__end__"
    return _route_on_failure(state)


def _validate_state(raw_state: GraphState | dict[str, object]) -> GraphState:
    """Apply the strict state contract even after LangGraph node updates."""
    return GraphState.model_validate(raw_state)


def _observed(
    name: str,
    node: Callable[[GraphState], dict[str, object]],
    dependencies: EngineDependencies,
) -> Callable[[GraphState], dict[str, object]]:
    """Log a node's entry and exit with its run, attempt, outcome, and duration."""

    def run(raw_state: GraphState) -> dict[str, object]:
        state = _validate_state(raw_state)
        fields: dict[str, object] = {
            "run_id": state.run_id,
            "node": name,
            "attempt": state.generation_attempts,
        }
        logger.debug("node %s started", name, extra=fields)
        started = time.monotonic()
        try:
            update = node(state)
        except GraphInterrupt:
            logger.info("node %s is awaiting a submission", name, extra=fields)
            raise
        except Exception as error:
            fields.update(
                error_type=type(error).__name__,
                duration_ms=round((time.monotonic() - started) * 1000),
            )
            logger.error("node %s raised %s", name, type(error).__name__, extra=fields)
            raise
        after = _validate_state(state.model_dump() | update)
        failure_category = None
        if "failure_report" in update and after.failure_report is not None:
            failure_category = _failure_category(dependencies, after.failure_report)
        fields.update(
            attempt=after.generation_attempts,
            status=after.status.value,
            failure_category=failure_category,
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        logger.info("node %s finished with status %s", name, after.status.value, extra=fields)
        return update

    return run


def _failure_category(dependencies: EngineDependencies, reference: ArtifactRef) -> str | None:
    """Read the category of a failure a node just recorded; logging never fails a node."""
    try:
        report = dependencies.artifacts.get_model(
            reference, FailureReport, MAX_FAILURE_REPORT_BYTES
        )
    except ArtifactError:
        return None
    return report.category


def _add_strict_node(
    graph: StateGraph[GraphState, None, GraphState, GraphState],
    name: str,
    node: Callable[[GraphState], Any],
) -> None:
    """Register one already-wrapped callable on a Pydantic-backed LangGraph."""
    # LangGraph's add_node overload rejects callables that consume a BaseModel
    # state, even though its runtime node adapter supports them.
    graph.add_node(name, cast(Any, node))


def _validated_patch(state: GraphState, patch: GraphPatch) -> dict[str, object]:
    """Validate each node output and its merged next state before returning it."""
    update: dict[str, object] = patch.model_dump(exclude_unset=True)
    GraphState.model_validate(state.model_dump() | update)
    return update


def _format_report(report: ValidationReport) -> str:
    """Create bounded compiler feedback for the next node-local hydration."""
    sections = [report.summary]
    for result in report.commands:
        sections.append(
            f"[{result.command_name}] exit_code={result.exit_code} timed_out={result.timed_out}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return "\n\n".join(sections)[:MAX_DIAGNOSTIC_CHARS]
