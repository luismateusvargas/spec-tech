"""Runtime loading of project engineering skills and ephemeral code prompts."""

from __future__ import annotations

from pathlib import Path

from sdd_engine.artifacts import ArtifactError, ArtifactStore, WorkspaceRegistry
from sdd_engine.models import (
    ArtifactRef,
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
            validation_feedback = load_text(state.validation_feedback)
        generation_feedback = None
        if state.failure_report is not None and state.failure_report != state.validation_feedback:
            generation_feedback = load_text(state.failure_report)

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
