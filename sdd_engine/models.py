"""Strict contracts used at every orchestration and worker boundary."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from sdd_engine.limits import (
    MAX_CATEGORY_CHARS,
    MAX_COMMAND_NAME_CHARS,
    MAX_CONTEXT_REFS,
    MAX_DIAGNOSTIC_CHARS,
    MAX_PATH_CHARS,
    MAX_SUMMARY_CHARS,
    MAX_TARGET_FILES,
)
from sdd_engine.limits import (
    MAX_FAILURE_REPORT_BYTES as MAX_FAILURE_REPORT_BYTES,
)
from sdd_engine.paths import canonical_relative_path

ItemT = TypeVar("ItemT")

# Model-level strict mode rejects JSON arrays for tuples and enum values as strings, which
# LangChain output parsers, API payloads, and checkpoint round trips all produce. These
# containers opt out of that one check; their items and every scalar remain strict.
JsonTuple = Annotated[tuple[ItemT, ...], Field(strict=False)]


class StrictModel(BaseModel):
    """Base model that rejects scalar coercion and unknown contract fields."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Target(StrEnum):
    """Supported language, frontend, and persistence work targets."""

    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    PYTHON = "python"
    RUST = "rust"
    GO = "go"
    CPP = "cpp"
    CPP_CV = "cpp-cv"
    CPP_AAA = "cpp-aaa"
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"
    PRISMA_JAVASCRIPT = "prisma-javascript"
    PRISMA_TYPESCRIPT = "prisma-typescript"
    SQLALCHEMY_ALEMBIC = "sqlalchemy-alembic"
    DIESEL = "diesel"
    REACT_JAVASCRIPT = "react-javascript"
    REACT_TYPESCRIPT = "react-typescript"
    VUE_JAVASCRIPT = "vue-javascript"
    VUE_TYPESCRIPT = "vue-typescript"


class Tier(StrEnum):
    """Project tier that selects the `sdd-implement-<tier>` skill for generation."""

    SIMPLE = "simple"
    SAAS = "saas"
    GAME = "game"


class RunStatus(StrEnum):
    """Lifecycle states used to route one bounded SDD execution."""

    READY = "ready"
    GENERATED = "generated"
    REFINEMENT_REQUIRED = "refinement_required"
    VALIDATION_FAILED = "validation_failed"
    VALIDATED = "validated"
    FAILED = "failed"


class RunPhase(StrEnum):
    """Persistence phase of a run awaiting input, completion, or finalization."""

    PENDING = "pending"
    TERMINAL = "terminal"
    FINISHED = "finished"


TargetValue = Annotated[Target, Field(strict=False)]
TierValue = Annotated[Tier, Field(strict=False)]
StatusValue = Annotated[RunStatus, Field(strict=False)]


def _require_safe_relative_path(value: str) -> str:
    """Canonicalize an approved workspace-relative path."""
    return canonical_relative_path(value)


def _require_unique_paths(value: tuple[str, ...]) -> tuple[str, ...]:
    """Bound a path list and reject duplicates."""
    if not value or len(value) > MAX_TARGET_FILES or len(set(value)) != len(value):
        raise ValueError(f"must contain 1 to {MAX_TARGET_FILES} unique paths")
    return value


SafeRelativePath = Annotated[
    str, Field(min_length=1, max_length=MAX_PATH_CHARS), AfterValidator(_require_safe_relative_path)
]
# Approved workspace-relative paths a run may write.
TargetFiles = Annotated[JsonTuple[SafeRelativePath], AfterValidator(_require_unique_paths)]


class ArtifactRef(StrictModel):
    """Content-addressed pointer to data held outside graph state."""

    digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    byte_length: Annotated[int, Field(ge=0)]
    media_type: Annotated[str, Field(min_length=1, max_length=128)]


class ErrorHandlingMapping(StrictModel):
    """Describes conversion from an infrastructure failure to a domain error."""

    failure: Annotated[str, Field(min_length=1, max_length=240)]
    domain_exception: Annotated[str, Field(min_length=1, max_length=240)]
    treatment: Annotated[str, Field(min_length=1, max_length=1000)]


class OriginalFile(StrictModel):
    """A workspace file as it was before the run first wrote it, for rollback on failure."""

    path: Annotated[str, Field(min_length=1, max_length=MAX_PATH_CHARS)]
    # None when the file did not exist; rollback then deletes it.
    content: ArtifactRef | None
    mode: Annotated[int, Field(ge=0, le=0o7777)] | None
    # The highest directory the write created, removed on rollback if it is empty again.
    created_directory: Annotated[str, Field(min_length=1, max_length=MAX_PATH_CHARS)] | None


class GraphInput(StrictModel):
    """Validated request accepted by the public graph invocation boundary."""

    run_id: Annotated[str, Field(min_length=1, max_length=128)]
    workspace_id: Annotated[str, Field(min_length=1, max_length=128)]
    target: TargetValue
    tier: TierValue
    specification: ArtifactRef
    target_files: TargetFiles
    context: JsonTuple[ArtifactRef] = ()
    target_entities: JsonTuple[Annotated[str, Field(min_length=1, max_length=256)]] = ()

    @field_validator("context")
    @classmethod
    def limit_context_references(cls, value: tuple[ArtifactRef, ...]) -> tuple[ArtifactRef, ...]:
        """Bound the number of hydrated artifacts a run can request."""
        if len(value) > MAX_CONTEXT_REFS:
            raise ValueError(f"context may contain at most {MAX_CONTEXT_REFS} artifact references")
        return value


class GraphState(StrictModel):
    """Minimal pointer-based state shared between LangGraph nodes."""

    run_id: Annotated[str, Field(min_length=1, max_length=128)]
    workspace_id: Annotated[str, Field(min_length=1, max_length=128)]
    target: TargetValue
    tier: TierValue
    specification: ArtifactRef
    target_files: TargetFiles
    context: JsonTuple[ArtifactRef] = ()
    target_entities: JsonTuple[Annotated[str, Field(min_length=1, max_length=256)]] = ()
    generated_artifact: ArtifactRef | None = None
    validation_report: ArtifactRef | None = None
    failure_report: ArtifactRef | None = None
    # The latest failed native check, kept apart from failure_report so that a contract
    # failure during a repair does not hide the compiler diagnostics being repaired.
    validation_feedback: ArtifactRef | None = None
    original_files: JsonTuple[OriginalFile] = ()
    workspace_restored: bool = False
    generation_attempts: Annotated[int, Field(ge=0)] = 0
    # Consecutive failed generations since the last successful one; bounds each round.
    generation_failures: Annotated[int, Field(ge=0)] = 0
    validation_attempts: Annotated[int, Field(ge=0)] = 0
    status: StatusValue = RunStatus.READY


class WorkspaceFile(StrictModel):
    """One whole workspace file: generated output, or existing content shown to the model."""

    path: SafeRelativePath
    content: str


class GenerationOutput(StrictModel):
    """Strict code-generation contract validated before any output is persisted."""

    files: JsonTuple[WorkspaceFile]
    documentation_metadata: Annotated[str, Field(min_length=1)]
    error_handling_mapping: JsonTuple[ErrorHandlingMapping]

    @field_validator("error_handling_mapping")
    @classmethod
    def require_error_mapping(
        cls, value: tuple[ErrorHandlingMapping, ...]
    ) -> tuple[ErrorHandlingMapping, ...]:
        """Require an explicit account of at least one failure treatment."""
        if not value:
            raise ValueError("error_handling_mapping must contain at least one entry")
        return value

    @field_validator("files")
    @classmethod
    def require_unique_files(cls, value: tuple[WorkspaceFile, ...]) -> tuple[WorkspaceFile, ...]:
        """Require at least one file and at most one entry per path."""
        _require_unique_paths(tuple(item.path for item in value))
        return value

    @field_validator("documentation_metadata")
    @classmethod
    def require_documentation_sections(cls, value: str) -> str:
        """Require argument and error documentation without embedded examples."""
        has_arguments = "# Arguments" in value or "Args:" in value or "@param" in value
        has_errors = (
            "# Errors" in value or "Raises:" in value or "@throws" in value or "@returns" in value
        )
        if not has_arguments or not has_errors:
            raise ValueError(
                "documentation_metadata must contain # Arguments and # Errors "
                "(or Args:/Raises: or @param/@throws)"
            )
        if "```" in value:
            raise ValueError("documentation_metadata must not contain inline code examples")
        return value


class GenerationPrompt(StrictModel):
    """Ephemeral hydrated prompt passed only to a generation worker."""

    run_id: str
    target: TargetValue
    tier: TierValue
    allowed_target_files: JsonTuple[str]
    target_entities: JsonTuple[str]
    specification_text: str
    referenced_context: JsonTuple[str]
    engineering_guidance: JsonTuple[str]
    # Current content of every approved target file that exists in the workspace.
    existing_files: JsonTuple[WorkspaceFile] = ()
    validation_feedback: str | None = None
    generation_feedback: str | None = None


class FailureReport(StrictModel):
    """Bounded diagnostic payload stored externally and referenced from state."""

    category: Annotated[str, Field(min_length=1, max_length=MAX_CATEGORY_CHARS)]
    summary: Annotated[str, Field(min_length=1, max_length=MAX_SUMMARY_CHARS)]
    diagnostics: Annotated[str, Field(max_length=MAX_DIAGNOSTIC_CHARS)] = ""


class CommandResult(StrictModel):
    """Result of one allowlisted native compiler or static-analysis command."""

    command_name: Annotated[str, Field(min_length=1, max_length=MAX_COMMAND_NAME_CHARS)]
    exit_code: int
    stdout: Annotated[str, Field(max_length=MAX_DIAGNOSTIC_CHARS)] = ""
    stderr: Annotated[str, Field(max_length=MAX_DIAGNOSTIC_CHARS)] = ""
    timed_out: bool = False


class ValidationReport(StrictModel):
    """Structured outcome of all native checks for a generated artifact."""

    target: TargetValue
    passed: bool
    commands: JsonTuple[CommandResult]
    summary: Annotated[str, Field(min_length=1, max_length=MAX_SUMMARY_CHARS)]
    profile_revision: Annotated[int, Field(ge=1)] | None = None
    profile_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None

    @model_validator(mode="after")
    def require_all_commands_pass(self) -> ValidationReport:
        """Keep the report status consistent with every command result."""
        if not self.commands:
            raise ValueError("validation report must contain at least one command result")
        commands_passed = all(
            result.exit_code == 0 and not result.timed_out for result in self.commands
        )
        if self.passed != commands_passed:
            raise ValueError("passed must match the status of all command results")
        return self


class GraphPatch(StrictModel):
    """Validated partial state update returned by a graph node wrapper."""

    generated_artifact: ArtifactRef | None = None
    validation_report: ArtifactRef | None = None
    failure_report: ArtifactRef | None = None
    validation_feedback: ArtifactRef | None = None
    original_files: JsonTuple[OriginalFile] | None = None
    workspace_restored: bool | None = None
    generation_attempts: Annotated[int, Field(ge=0)] | None = None
    generation_failures: Annotated[int, Field(ge=0)] | None = None
    validation_attempts: Annotated[int, Field(ge=0)] | None = None
    status: Annotated[RunStatus | None, Field(strict=False)] = None


class RouteDecision(StrictModel):
    """Validated destination selected by a conditional graph edge."""

    destination: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
