"""Hierarchical LangGraph router with strict node contracts and repair loops."""

from __future__ import annotations

from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Any, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
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
    MAX_GENERATED_ARTIFACT_BYTES,
    MAX_ORIGINAL_FILE_BYTES,
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
    RouteDecision,
    RunStatus,
    Target,
    Tier,
    ValidationReport,
)
from sdd_engine.validation import NativeValidator, ValidationInfrastructureError

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


def checkpoint_serializer() -> JsonPlusSerializer:
    """Return a checkpoint serializer that allows only LangGraph's safe types and the engine's.

    Pass it as the `serde` of a checkpointer given to `build_engine`.
    """
    return JsonPlusSerializer(
        allowed_msgpack_modules=[(kind.__module__, kind.__name__) for kind in CHECKPOINT_TYPES]
    )


@dataclass(frozen=True)
class EngineDependencies:
    """Infrastructure dependencies shared by language-specialist subgraphs."""

    artifacts: ArtifactStore
    workspaces: WorkspaceRegistry
    prompts: PromptHydrator
    validator: NativeValidator
    max_generation_attempts: int = 3
    max_validation_attempts: int = 3

    def __post_init__(self) -> None:
        """Reject retry configurations that can create unbounded graph loops."""
        if not 1 <= self.max_generation_attempts <= 10:
            raise ValueError("max_generation_attempts must be between 1 and 10")
        if not 1 <= self.max_validation_attempts <= 10:
            raise ValueError("max_validation_attempts must be between 1 and 10")


def build_graph(
    dependencies: EngineDependencies,
    checkpointer: BaseCheckpointSaver[str] | None = None,
) -> CompiledStateGraph[GraphState, None, GraphState, GraphState]:
    """Compile a router graph whose target-specific subgraphs share strict wrappers."""
    outer: StateGraph[GraphState, None, GraphState, GraphState] = StateGraph(GraphState)
    target_routes: dict[Hashable, str] = {}

    for target in Target:
        route = _route_name(target)
        outer.add_node(route, _build_specialist_subgraph(target, dependencies))
        target_routes[route] = route
        outer.add_edge(route, END)

    outer.add_conditional_edges(START, _route_target, target_routes)
    if checkpointer is not None:
        # Extends an explicit or strict-mode allowlist; a permissive serializer is unchanged.
        checkpointer = checkpointer.with_allowlist(
            [(kind.__module__, kind.__name__) for kind in CHECKPOINT_TYPES]
        )
    return outer.compile(checkpointer=checkpointer)


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

    def submit(self, run_id: str, workspace_id: str, response: object) -> dict[str, object]:
        """Resume a paused run with the implementer's structured file submission."""
        return self._step(Command(resume=response), workspace_id, run_id)

    def _step(
        self, value: GraphState | Command[Any], workspace_id: str, run_id: str
    ) -> dict[str, object]:
        """Advance the graph under a worktree lock and expose only prompt or state."""
        try:
            with self._dependencies.workspaces.lock(workspace_id):
                result = self._graph.invoke(
                    value,
                    config={"configurable": {"thread_id": run_id}},
                )
        except WorkspaceBusyError as error:
            raise ArtifactError("another run is using this workspace") from error
        except ArtifactError as error:
            raise ArtifactError("the workspace could not be locked") from error
        if "__interrupt__" in result:
            values = result["__interrupt__"]
            return {
                "prompt": GenerationPrompt.model_validate(values[0].value).model_dump(mode="json")
            }
        return {"state": GraphState.model_validate(result).model_dump(mode="json")}


def _build_specialist_subgraph(
    target: Target, dependencies: EngineDependencies
) -> CompiledStateGraph[GraphState, None, GraphState, GraphState]:
    """Build an isolated generate/validate loop for one selected stack target."""
    specialist: StateGraph[GraphState, None, GraphState, GraphState] = StateGraph(GraphState)

    def record_failure(category: str, summary: str, error: Exception | None = None) -> ArtifactRef:
        failure = FailureReport(
            category=category,
            summary=summary,
            diagnostics="" if error is None else str(error)[:MAX_DIAGNOSTIC_CHARS],
        )
        return dependencies.artifacts.put_model(failure)

    def snapshot_original(workspace_id: str, path: str) -> OriginalFile:
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

    def rollback(raw_state: GraphState) -> dict[str, Any]:
        state = _validate_state(raw_state)
        try:
            # Restore in reverse so a later file's directories are removed before earlier ones.
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
            failure_ref = record_failure(
                "rollback",
                "The run failed and its workspace changes could not be fully restored.",
                RuntimeError(f"{error}\n\nOriginal failure: {cause}"),
            )
            patch = GraphPatch(failure_report=failure_ref, status=RunStatus.FAILED)
            return _validated_patch(state, patch)
        return _validated_patch(state, GraphPatch(workspace_restored=True))

    def generate(raw_state: GraphState) -> dict[str, Any]:
        state = _validate_state(raw_state)
        try:
            prompt = dependencies.prompts.hydrate(state)
        except ArtifactError as error:
            # Missing or oversized inputs do not change between attempts, so do not retry.
            failure_ref = record_failure(
                "hydration", "Generation inputs could not be loaded within their limits.", error
            )
            patch = GraphPatch(failure_report=failure_ref, status=RunStatus.FAILED)
            return _validated_patch(state, patch)

        attempt = state.generation_attempts + 1
        # Each generation round, the first or a repair after failed checks, has its own budget.
        failures = state.generation_failures + 1
        retry_status = (
            RunStatus.REFINEMENT_REQUIRED
            if failures < dependencies.max_generation_attempts
            else RunStatus.FAILED
        )
        try:
            generated = GenerationOutput.model_validate(interrupt(prompt.model_dump(mode="json")))
            undeclared = [
                item.path for item in generated.files if item.path not in state.target_files
            ]
            if undeclared:
                raise ValueError(f"generated files are not approved target paths: {undeclared}")
        except (ValidationError, ValueError) as error:
            failure_ref = record_failure(
                "generation_contract",
                "Generated output did not satisfy its strict Pydantic contract.",
                error,
            )
            patch = GraphPatch(
                generation_attempts=attempt,
                generation_failures=failures,
                failure_report=failure_ref,
                status=retry_status,
            )
            return _validated_patch(state, patch)
        original_files = state.original_files
        try:
            for item in generated.files:
                if all(original.path != item.path for original in original_files):
                    # Record each file before the run first changes it, so a failed run can
                    # undo it, including files written before a later write fails.
                    original_files = (
                        *original_files,
                        snapshot_original(state.workspace_id, item.path),
                    )
                dependencies.workspaces.write_text(state.workspace_id, item.path, item.content)
        except (ArtifactError, OSError) as error:
            failure_ref = record_failure(
                "workspace_write", "A generated file could not be written.", error
            )
            patch = GraphPatch(
                generation_attempts=attempt,
                original_files=original_files,
                failure_report=failure_ref,
                status=RunStatus.FAILED,
            )
            return _validated_patch(state, patch)
        generated_ref = dependencies.artifacts.put_model(generated)
        patch = GraphPatch(
            original_files=original_files,
            generated_artifact=generated_ref,
            failure_report=None,
            generation_attempts=attempt,
            generation_failures=0,
            status=RunStatus.GENERATED,
        )
        return _validated_patch(state, patch)

    def validate(raw_state: GraphState) -> dict[str, Any]:
        state = _validate_state(raw_state)
        failure_ref: ArtifactRef | None = None
        if state.generated_artifact is None:
            failure_ref = record_failure(
                "missing_generation", "Validation cannot run before a generated artifact exists."
            )
            patch = GraphPatch(failure_report=failure_ref, status=RunStatus.FAILED)
            return _validated_patch(state, patch)

        try:
            generated = dependencies.artifacts.get_model(
                state.generated_artifact, GenerationOutput, MAX_GENERATED_ARTIFACT_BYTES
            )
            workspace = dependencies.workspaces.get(state.workspace_id)
        except ArtifactError as error:
            failure_ref = record_failure(
                "artifact_contract", "The generated artifact or workspace is unavailable.", error
            )
            patch = GraphPatch(failure_report=failure_ref, status=RunStatus.FAILED)
            return _validated_patch(state, patch)
        if any(item.path not in state.target_files for item in generated.files):
            failure_ref = record_failure(
                "artifact_contract",
                "A stored generated file is outside the approved target paths.",
            )
            patch = GraphPatch(failure_report=failure_ref, status=RunStatus.FAILED)
            return _validated_patch(state, patch)
        try:
            report = dependencies.validator.validate(target, workspace)
        except ValidationInfrastructureError as error:
            # The generated code was never checked; repairing it cannot fix the toolchain.
            failure_ref = record_failure(
                "validation_infrastructure", "Native checks could not be executed.", error
            )
            patch = GraphPatch(failure_report=failure_ref, status=RunStatus.FAILED)
            return _validated_patch(state, patch)
        report_ref = dependencies.artifacts.put_model(report)
        next_attempt = state.validation_attempts + 1
        if report.passed:
            status = RunStatus.VALIDATED
            failure_ref = None
        else:
            failure = FailureReport(
                category="native_validation",
                summary=report.summary,
                diagnostics=_format_report(report),
            )
            failure_ref = dependencies.artifacts.put_model(failure)
            status = (
                RunStatus.VALIDATION_FAILED
                if next_attempt < dependencies.max_validation_attempts
                else RunStatus.FAILED
            )
        patch = GraphPatch(
            validation_report=report_ref,
            failure_report=failure_ref,
            validation_feedback=failure_ref,
            validation_attempts=next_attempt,
            status=status,
        )
        return _validated_patch(state, patch)

    _add_strict_node(specialist, "generate", generate)
    _add_strict_node(specialist, "validate", validate)
    _add_strict_node(specialist, "rollback", rollback)
    specialist.add_edge(START, "generate")
    specialist.add_conditional_edges(
        "generate",
        _route_after_generation,
        {"generate": "generate", "validate": "validate", "rollback": "rollback", "end": END},
    )
    specialist.add_conditional_edges(
        "validate",
        _route_after_validation,
        {"generate": "generate", "rollback": "rollback", "end": END},
    )
    specialist.add_edge("rollback", END)
    return specialist.compile()


def _route_target(raw_state: GraphState) -> str:
    """Validate graph state before selecting a language-specific subgraph."""
    state = _validate_state(raw_state)
    decision = RouteDecision(destination=_route_name(state.target))
    return decision.destination


def _route_after_generation(raw_state: GraphState) -> str:
    """Drop invalid generation updates and retry only within the configured bound."""
    state = _validate_state(raw_state)
    if state.status is RunStatus.GENERATED:
        return RouteDecision(destination="validate").destination
    if state.status is RunStatus.REFINEMENT_REQUIRED:
        return RouteDecision(destination="generate").destination
    return _route_on_failure(state)


def _route_after_validation(raw_state: GraphState) -> str:
    """Return failed native diagnostics to generation or finish the bounded run."""
    state = _validate_state(raw_state)
    if state.status is RunStatus.VALIDATED:
        return RouteDecision(destination="end").destination
    if state.status is RunStatus.VALIDATION_FAILED:
        return RouteDecision(destination="generate").destination
    return _route_on_failure(state)


def _route_on_failure(state: GraphState) -> str:
    """Undo the run's workspace writes before a failed run ends."""
    if state.status is RunStatus.FAILED and state.original_files:
        return RouteDecision(destination="rollback").destination
    return RouteDecision(destination="end").destination


def _validate_state(raw_state: GraphState | dict[str, object]) -> GraphState:
    """Apply the strict state contract even after LangGraph node updates."""
    return GraphState.model_validate(raw_state)


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
    validated_patch = GraphPatch.model_validate(patch)
    update = validated_patch.model_dump(exclude_unset=True)
    GraphState.model_validate(state.model_dump() | update)
    return update


def _route_name(target: Target) -> str:
    """Convert the fixed target enum into a safe graph node identifier."""
    decision = RouteDecision(destination=target.value.replace("-", "_"))
    return decision.destination


def _format_report(report: ValidationReport) -> str:
    """Create bounded compiler feedback for the next node-local hydration."""
    sections = [report.summary]
    for result in report.commands:
        sections.append(
            f"[{result.command_name}] exit_code={result.exit_code} timed_out={result.timed_out}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return "\n\n".join(sections)[:MAX_DIAGNOSTIC_CHARS]
