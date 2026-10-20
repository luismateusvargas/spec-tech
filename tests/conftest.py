"""Shared fakes and engine wiring for SDD engine tests."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver

from sdd_engine.artifacts import FileArtifactStore, WorkspaceRegistry
from sdd_engine.graph import CodeGenerator, EngineDependencies, SddEngine, build_engine
from sdd_engine.guidance import PromptHydrator, StructuredCodeGenerator
from sdd_engine.models import CommandResult, GraphInput, Target, Tier
from sdd_engine.validation import CommandSpec, NativeValidator, ValidationProfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ID = "task-worktree"
TARGET_FILE = "pkg/module.py"


def generation_args(**overrides: object) -> dict[str, object]:
    """Return JSON-shaped tool-call arguments for a valid GenerationOutput."""
    args: dict[str, object] = {
        "files": [{"path": TARGET_FILE, "content": "VALUE = 1\n"}],
        "documentation_metadata": "# Arguments\nNone.\n\n# Errors\nNone.",
        "error_handling_mapping": [
            {
                "failure": "OSError while reading",
                "domain_exception": "StorageError",
                "treatment": "Wrap and re-raise with the path.",
            }
        ],
    }
    args.update(overrides)
    return args


class ScriptedToolModel(BaseChatModel):
    """Chat model that answers each call with the next scripted tool call or exception."""

    responses: list[dict[str, object] | Exception]
    prompts: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "scripted-tool-model"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.prompts.append(str(messages[-1].content))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        message = AIMessage(
            content="",
            tool_calls=[{"name": "GenerationOutput", "args": response, "id": "call-1"}],
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


@dataclass
class ScriptedRunner:
    """Command runner that returns scripted results, or raises scripted errors, in order."""

    outcomes: list[CommandResult | Exception] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)

    def run(
        self, command: CommandSpec, workspace: Path, profile: ValidationProfile
    ) -> CommandResult:
        self.calls.append(command.name)
        if not self.outcomes:
            return CommandResult(command_name=command.name, exit_code=0)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@dataclass
class Harness:
    """Engine plus the collaborators a test inspects."""

    store: FileArtifactStore
    registry: WorkspaceRegistry
    workspace: Path
    request: GraphInput
    build: Callable[..., SddEngine]


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    workspace = tmp_path / "worktree"
    workspace.mkdir()
    store = FileArtifactStore(tmp_path / "artifacts")
    registry = WorkspaceRegistry({WORKSPACE_ID: workspace}, lock_directory=tmp_path / "locks")
    specification = store.put(b"Expose VALUE = 1 from pkg/module.py.", "text/markdown")
    request = GraphInput(
        run_id="run-001",
        workspace_id=WORKSPACE_ID,
        target=Target.PYTHON,
        tier=Tier.SIMPLE,
        specification=specification,
        target_files=(TARGET_FILE,),
    )

    def build(
        generator: CodeGenerator,
        runner: ScriptedRunner | None = None,
        checkpointer: BaseCheckpointSaver[str] | None = None,
        profiles: dict[Target, ValidationProfile] | None = None,
    ) -> SddEngine:
        if profiles is None:
            profiles = {
                Target.PYTHON: ValidationProfile(
                    image="python:3.12-slim",
                    commands=(
                        CommandSpec(name="ruff-check", argv=("ruff", "check", ".")),
                        CommandSpec(name="mypy-strict", argv=("mypy", "--strict", ".")),
                    ),
                )
            }
        dependencies = EngineDependencies(
            artifacts=store,
            workspaces=registry,
            prompts=PromptHydrator(PROJECT_ROOT, store, registry),
            generator=generator,
            validator=NativeValidator(profiles, runner or ScriptedRunner()),
        )
        return build_engine(dependencies, checkpointer)

    return Harness(
        store=store, registry=registry, workspace=workspace, request=request, build=build
    )


def llm_generator(
    *responses: dict[str, object] | Exception,
) -> tuple[StructuredCodeGenerator, ScriptedToolModel]:
    """Wrap a scripted model in the production structured-output adapter."""
    model = ScriptedToolModel(responses=list(responses), prompts=[])
    return StructuredCodeGenerator(model), model
