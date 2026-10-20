"""Runtime loading of project engineering skills and ephemeral code prompts."""

from __future__ import annotations

from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from sdd_engine.artifacts import ArtifactError, ArtifactStore, WorkspaceRegistry
from sdd_engine.models import (
    MAX_FAILURE_REPORT_BYTES,
    ArtifactRef,
    GenerationOutput,
    GenerationPrompt,
    GraphState,
    Target,
    WorkspaceFile,
)

TARGET_SKILLS: dict[Target, tuple[str, ...]] = {
    Target.JAVASCRIPT: ("javascript-dev",),
    Target.TYPESCRIPT: ("typescript-dev",),
    Target.PYTHON: ("python-dev",),
    Target.RUST: ("rust-dev",),
    Target.GO: ("go-dev",),
    Target.CPP: ("cpp-dev",),
    Target.CPP_CV: ("cpp-dev", "cpp-cv-dev"),
    Target.CPP_AAA: ("cpp-dev", "cpp-aaa-dev"),
    Target.MYSQL: ("database-dev",),
    Target.POSTGRESQL: ("database-dev",),
    Target.PRISMA_JAVASCRIPT: ("database-dev", "javascript-dev"),
    Target.PRISMA_TYPESCRIPT: ("database-dev", "typescript-dev"),
    Target.SQLALCHEMY_ALEMBIC: ("database-dev", "python-dev"),
    Target.DIESEL: ("database-dev", "rust-dev"),
    Target.REACT_JAVASCRIPT: ("javascript-dev", "react-dev"),
    Target.REACT_TYPESCRIPT: ("typescript-dev", "react-dev"),
    Target.VUE_JAVASCRIPT: ("javascript-dev", "vue-dev"),
    Target.VUE_TYPESCRIPT: ("typescript-dev", "vue-dev"),
}


class GenerationError(RuntimeError):
    """Raised when a code generator fails before returning a contract candidate."""


class PromptHydrator:
    """Loads only the spec, referenced files, and selected skills needed by a node."""

    def __init__(
        self,
        project_root: Path,
        artifacts: ArtifactStore,
        workspaces: WorkspaceRegistry,
        max_context_bytes: int = 2_000_000,
    ) -> None:
        """Configure runtime skill paths and bounded context hydration."""
        self._project_root = project_root.expanduser().resolve(strict=True)
        self._artifacts = artifacts
        self._workspaces = workspaces
        self._max_context_bytes = max_context_bytes

    def hydrate(self, state: GraphState) -> GenerationPrompt:
        """Build a node-local prompt; raw context is never written to graph state.

        The prompt carries the latest native-check diagnostics and, separately, the latest
        generation failure when it is a different report.
        """
        byte_count = 0

        def load_text(reference: ArtifactRef) -> str:
            nonlocal byte_count
            remaining = self._max_context_bytes - byte_count
            if remaining <= 0:
                raise ArtifactError("hydrated context exceeded the configured total limit")
            value = self._artifacts.get_text(reference, remaining)
            byte_count += len(value.encode("utf-8"))
            return value

        specification = load_text(state.specification)
        references = tuple(load_text(reference) for reference in state.context)
        skills = (f"sdd-implement-{state.tier.value}", *TARGET_SKILLS[state.target])
        guidance = tuple(self._load_skill(name) for name in skills)
        byte_count += sum(len(item.encode("utf-8")) for item in guidance)
        if byte_count > self._max_context_bytes:
            raise ArtifactError(
                "hydrated context and engineering guidance exceeded the configured limit"
            )

        # Show every approved file as it is now: the original on a first attempt, or the
        # previous generation during a repair.
        existing_files: list[WorkspaceFile] = []
        for path in state.target_files:
            remaining = self._max_context_bytes - byte_count
            content = self._workspaces.read_text(state.workspace_id, path, max(remaining, 0))
            if content is not None:
                byte_count += len(content.encode("utf-8"))
                existing_files.append(WorkspaceFile(path=path, content=content))

        validation_feedback = None
        if state.validation_feedback is not None:
            validation_feedback = self._artifacts.get_text(
                state.validation_feedback, MAX_FAILURE_REPORT_BYTES
            )
        generation_feedback = None
        if state.failure_report is not None and state.failure_report != state.validation_feedback:
            generation_feedback = self._artifacts.get_text(
                state.failure_report, MAX_FAILURE_REPORT_BYTES
            )

        return GenerationPrompt(
            run_id=state.run_id,
            target=state.target,
            tier=state.tier,
            allowed_target_files=state.target_files,
            target_entities=state.target_entities,
            specification_text=specification,
            referenced_context=references,
            engineering_guidance=guidance,
            existing_files=tuple(existing_files),
            validation_feedback=validation_feedback,
            generation_feedback=generation_feedback,
        )

    def _load_skill(self, skill_name: str) -> str:
        """Read a known project skill at invocation time and reject path escapes."""
        skill_path = (self._project_root / "skills" / skill_name / "SKILL.md").resolve(strict=True)
        skill_root = (self._project_root / "skills").resolve(strict=True)
        if not skill_path.is_relative_to(skill_root):
            raise ArtifactError(
                f"skill path {skill_name!r} escaped the configured skills directory"
            )
        content = skill_path.read_text(encoding="utf-8")
        if len(content.encode("utf-8")) > self._max_context_bytes:
            raise ArtifactError(f"skill {skill_name!r} exceeds the configured context limit")
        return content


class StructuredCodeGenerator:
    """LangChain model adapter that requires a Pydantic code-generation result."""

    def __init__(self, model: BaseChatModel) -> None:
        """Bind a chat model to the strict generation result schema."""
        self._model = model.with_structured_output(GenerationOutput)

    def generate(self, prompt: GenerationPrompt) -> GenerationOutput:
        """Generate whole files under the declared artifact contract.

        # Errors

        Raises `ValueError` (including LangChain output-parser errors) or `ValidationError`
        for a response that breaks the contract, and `GenerationError` for model or
        provider failures.
        """
        system_text = (
            "You are the code-writing step of an SDD implementation. Implement the task spec by "
            "returning the complete content of every file you create or change; only paths in "
            "allowed_target_files may be written, and files you omit stay as they are. Include "
            "the tests the spec and skills call for: native checks, including the test suite, "
            "run on the result, and a missing or failing suite fails the run. During a repair, "
            "fix the diagnostics in validation_feedback and generation_feedback. The calling "
            "agent handles git checkpoints, project memory, and review, so skip those skill "
            "steps. Follow the supplied project skills and spec. Return the exact structured "
            "contract requested. Documentation metadata must have # Arguments and # Errors "
            "sections and must not contain code examples. Do not claim that code is compiled "
            "or verified."
        )
        user_text = prompt.model_dump_json(indent=2)
        try:
            result = self._model.invoke(
                [SystemMessage(content=system_text), HumanMessage(content=user_text)]
            )
        except ValueError:
            raise
        # Providers raise unrelated exception hierarchies; translate them at this port.
        except Exception as error:
            raise GenerationError(
                f"code generation model failed: {type(error).__name__}: {error}"
            ) from error
        generated = GenerationOutput.model_validate(result)
        undeclared = [
            item.path for item in generated.files if item.path not in prompt.allowed_target_files
        ]
        if undeclared:
            raise ValueError(f"generated files were not declared in the GraphInput: {undeclared}")
        return generated
