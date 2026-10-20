"""End-to-end routing, retry, and failure-reporting behavior of the compiled engine."""

from __future__ import annotations

import json
import logging

import pytest
from conftest import (
    PROJECT_ROOT,
    TARGET_FILE,
    WORKSPACE_ID,
    Harness,
    ScriptedRunner,
    generation_args,
    llm_generator,
)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from sdd_engine.graph import checkpoint_serializer
from sdd_engine.models import (
    ArtifactRef,
    CommandResult,
    FailureReport,
    GenerationOutput,
    GraphState,
    RunStatus,
    ValidationReport,
)
from sdd_engine.validation import ValidationInfrastructureError


def unapproved_file_args() -> dict[str, object]:
    return generation_args(files=[{"path": "other.py", "content": "x"}])


def failure_of(harness: Harness, state: GraphState) -> FailureReport:
    assert state.failure_report is not None
    return harness.store.get_model(state.failure_report, FailureReport, 1_000_000)


def test_structured_llm_output_is_written_and_validated(harness: Harness) -> None:
    generator, model = llm_generator(generation_args())
    runner = ScriptedRunner()

    state = harness.build(generator, runner).invoke(harness.request)

    assert state.status is RunStatus.VALIDATED
    assert (state.generation_attempts, state.validation_attempts) == (1, 1)
    assert state.failure_report is None
    assert (harness.workspace / TARGET_FILE).read_text(encoding="utf-8") == "VALUE = 1\n"
    assert runner.calls == ["ruff-check", "mypy-strict"]
    assert state.generated_artifact is not None
    stored = harness.store.get_model(state.generated_artifact, GenerationOutput, 1_000_000)
    assert stored.error_handling_mapping[0].domain_exception == "StorageError"
    skills = [
        (PROJECT_ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        for name in ("sdd-implement-simple", "python-dev")
    ]
    assert json.loads(model.prompts[0])["engineering_guidance"] == skills


def test_contract_failure_is_retried_then_succeeds(harness: Harness) -> None:
    generator, model = llm_generator(
        generation_args(documentation_metadata="missing sections"), generation_args()
    )

    state = harness.build(generator).invoke(harness.request)

    assert state.status is RunStatus.VALIDATED
    assert state.generation_attempts == 2
    repair_prompt = json.loads(model.prompts[1])
    assert "# Arguments and # Errors" in repair_prompt["generation_feedback"]
    assert repair_prompt["validation_feedback"] is None


def test_unapproved_target_file_exhausts_generation_budget(harness: Harness) -> None:
    generator, _ = llm_generator(*(unapproved_file_args() for _ in range(3)))
    runner = ScriptedRunner()

    state = harness.build(generator, runner).invoke(harness.request)

    assert state.status is RunStatus.FAILED
    assert state.generation_attempts == 3
    assert failure_of(harness, state).category == "generation_contract"
    assert not (harness.workspace / "other.py").exists()
    assert runner.calls == []


def test_provider_error_is_reported_and_retried(harness: Harness) -> None:
    generator, _ = llm_generator(ConnectionError("upstream reset"), generation_args())

    state = harness.build(generator).invoke(harness.request)

    assert state.status is RunStatus.VALIDATED
    assert state.generation_attempts == 2


def test_persistent_provider_error_fails_with_report(harness: Harness) -> None:
    generator, _ = llm_generator(*(TimeoutError("rate limited") for _ in range(3)))

    state = harness.build(generator).invoke(harness.request)

    assert state.status is RunStatus.FAILED
    failure = failure_of(harness, state)
    assert failure.category == "generation_error"
    assert "TimeoutError: rate limited" in failure.diagnostics


def test_native_failure_feeds_diagnostics_into_repair(harness: Harness) -> None:
    generator, model = llm_generator(generation_args(), generation_args())
    runner = ScriptedRunner(
        [CommandResult(command_name="ruff-check", exit_code=1, stdout="F401 unused import os")]
    )

    state = harness.build(generator, runner).invoke(harness.request)

    assert state.status is RunStatus.VALIDATED
    assert (state.generation_attempts, state.validation_attempts) == (2, 2)
    repair_prompt = json.loads(model.prompts[1])
    assert "F401 unused import os" in repair_prompt["validation_feedback"]
    assert repair_prompt["existing_files"] == [{"path": TARGET_FILE, "content": "VALUE = 1\n"}]


def test_native_failures_exhaust_validation_budget(harness: Harness) -> None:
    generator, _ = llm_generator(*(generation_args() for _ in range(3)))
    runner = ScriptedRunner(
        [CommandResult(command_name="ruff-check", exit_code=1, stdout="E501") for _ in range(3)]
    )

    state = harness.build(generator, runner).invoke(harness.request)

    assert state.status is RunStatus.FAILED
    assert state.validation_attempts == 3
    assert failure_of(harness, state).category == "native_validation"
    assert state.validation_report is not None
    report = harness.store.get_model(state.validation_report, ValidationReport, 1_000_000)
    assert not report.passed


def test_large_non_ascii_diagnostics_reach_the_repair_prompt(harness: Harness) -> None:
    # Regression: a JSON-encoded report above 32,000 bytes crashed the repair hydration.
    generator, model = llm_generator(generation_args(), generation_args())
    runner = ScriptedRunner(
        [CommandResult(command_name="ruff-check", exit_code=1, stdout="─" * 15_000)]
    )

    state = harness.build(generator, runner).invoke(harness.request)

    assert state.status is RunStatus.VALIDATED
    assert "─" * 100 in json.loads(model.prompts[1])["validation_feedback"]


def test_validation_infrastructure_error_fails_without_repair(harness: Harness) -> None:
    generator, model = llm_generator(generation_args())
    runner = ScriptedRunner([ValidationInfrastructureError("image not found")])

    state = harness.build(generator, runner).invoke(harness.request)

    assert state.status is RunStatus.FAILED
    assert state.validation_attempts == 0
    assert len(model.prompts) == 1
    failure = failure_of(harness, state)
    assert failure.category == "validation_infrastructure"
    assert "image not found" in failure.diagnostics


def test_missing_validation_profile_fails_with_report(harness: Harness) -> None:
    generator, _ = llm_generator(generation_args())

    state = harness.build(generator, profiles={}).invoke(harness.request)

    assert state.status is RunStatus.FAILED
    assert failure_of(harness, state).category == "validation_infrastructure"


def test_missing_specification_fails_hydration_without_generating(harness: Harness) -> None:
    generator, model = llm_generator(generation_args())
    request = harness.request.model_copy(
        update={
            "specification": harness.request.specification.model_copy(update={"digest": "0" * 64})
        }
    )

    state = harness.build(generator).invoke(request)

    assert state.status is RunStatus.FAILED
    assert state.generation_attempts == 0
    assert model.prompts == []
    assert failure_of(harness, state).category == "hydration"


def test_workspace_write_failure_fails_with_report(harness: Harness) -> None:
    # A read-only parent directory makes the atomic write fail.
    parent = (harness.workspace / TARGET_FILE).parent
    parent.mkdir()
    parent.chmod(0o500)
    generator, _ = llm_generator(generation_args())

    try:
        state = harness.build(generator).invoke(harness.request)
    finally:
        parent.chmod(0o700)

    assert state.status is RunStatus.FAILED
    assert failure_of(harness, state).category == "workspace_write"


def test_unreadable_target_path_fails_hydration(harness: Harness) -> None:
    (harness.workspace / TARGET_FILE).mkdir(parents=True)
    generator, model = llm_generator(generation_args())

    state = harness.build(generator).invoke(harness.request)

    assert state.status is RunStatus.FAILED
    assert failure_of(harness, state).category == "hydration"
    assert model.prompts == []


def test_one_generation_writes_several_files(harness: Harness) -> None:
    request = harness.request.model_copy(update={"target_files": (TARGET_FILE, "tests/test_x.py")})
    generator, model = llm_generator(
        generation_args(
            files=[
                {"path": TARGET_FILE, "content": "VALUE = 1\n"},
                {"path": "tests/test_x.py", "content": "def test_value() -> None: ...\n"},
            ]
        )
    )

    state = harness.build(generator).invoke(request)

    assert state.status is RunStatus.VALIDATED
    assert (harness.workspace / "tests" / "test_x.py").is_file()
    assert [original.path for original in state.original_files] == [TARGET_FILE, "tests/test_x.py"]
    assert json.loads(model.prompts[0])["allowed_target_files"] == [TARGET_FILE, "tests/test_x.py"]


def test_first_prompt_shows_existing_target_files(harness: Harness) -> None:
    target = harness.workspace / TARGET_FILE
    target.parent.mkdir(parents=True)
    target.write_text("ORIGINAL = 0\n", encoding="utf-8")
    generator, model = llm_generator(generation_args())

    harness.build(generator).invoke(harness.request)

    existing = json.loads(model.prompts[0])["existing_files"]
    assert existing == [{"path": TARGET_FILE, "content": "ORIGINAL = 0\n"}]


def test_failed_multi_file_run_restores_every_file(harness: Harness) -> None:
    request = harness.request.model_copy(update={"target_files": (TARGET_FILE, "README.md")})
    (harness.workspace / "README.md").write_text("docs\n", encoding="utf-8")
    files = [
        {"path": TARGET_FILE, "content": "VALUE = 1\n"},
        {"path": "README.md", "content": "changed\n"},
    ]
    generator, _ = llm_generator(*(generation_args(files=files) for _ in range(3)))
    runner = ScriptedRunner(
        [CommandResult(command_name="ruff-check", exit_code=1) for _ in range(3)]
    )

    state = harness.build(generator, runner).invoke(request)

    assert state.workspace_restored
    assert (harness.workspace / "README.md").read_text(encoding="utf-8") == "docs\n"
    assert sorted(path.name for path in harness.workspace.iterdir()) == ["README.md"]


def test_checkpointed_run_round_trips_state(harness: Harness) -> None:
    generator, _ = llm_generator(generation_args(), generation_args())
    runner = ScriptedRunner([CommandResult(command_name="ruff-check", exit_code=1)])

    state = harness.build(generator, runner, checkpointer=InMemorySaver()).invoke(harness.request)

    assert state.status is RunStatus.VALIDATED
    assert state.validation_attempts == 2


def test_contract_failure_during_repair_has_its_own_budget(harness: Harness) -> None:
    # Two failed checks used to spend the shared budget, so one contract failure ended the run.
    broken = generation_args(documentation_metadata="missing sections")
    generator, _ = llm_generator(
        generation_args(), broken, generation_args(), broken, generation_args()
    )
    runner = ScriptedRunner(
        [CommandResult(command_name="ruff-check", exit_code=1, stdout="E501") for _ in range(2)]
    )

    state = harness.build(generator, runner).invoke(harness.request)

    assert state.status is RunStatus.VALIDATED
    assert (state.generation_attempts, state.generation_failures) == (5, 0)
    assert state.validation_attempts == 3


def test_generation_budget_applies_per_round(harness: Harness) -> None:
    broken = generation_args(documentation_metadata="missing sections")
    generator, _ = llm_generator(generation_args(), broken, broken, broken)
    runner = ScriptedRunner([CommandResult(command_name="ruff-check", exit_code=1)])

    state = harness.build(generator, runner).invoke(harness.request)

    assert state.status is RunStatus.FAILED
    assert (state.generation_attempts, state.generation_failures) == (4, 3)
    assert failure_of(harness, state).category == "generation_contract"


def test_compiler_diagnostics_survive_a_contract_failure_during_repair(
    harness: Harness,
) -> None:
    broken = generation_args(documentation_metadata="missing sections")
    generator, model = llm_generator(generation_args(), broken, generation_args())
    runner = ScriptedRunner(
        [CommandResult(command_name="ruff-check", exit_code=1, stdout="F401 unused import os")]
    )

    state = harness.build(generator, runner).invoke(harness.request)

    assert state.status is RunStatus.VALIDATED
    retry_prompt = json.loads(model.prompts[2])
    assert "F401 unused import os" in retry_prompt["validation_feedback"]
    assert "# Arguments and # Errors" in retry_prompt["generation_feedback"]
    assert state.validation_feedback is None


@pytest.mark.parametrize(
    "serde",
    [checkpoint_serializer(), JsonPlusSerializer(allowed_msgpack_modules=None)],
    ids=["engine-serializer", "strict-serializer"],
)
def test_checkpoints_restore_engine_types_without_warnings(
    harness: Harness, caplog: pytest.LogCaptureFixture, serde: JsonPlusSerializer
) -> None:
    caplog.set_level(logging.WARNING)
    generator, _ = llm_generator(generation_args(), generation_args())
    runner = ScriptedRunner([CommandResult(command_name="ruff-check", exit_code=1)])
    engine = harness.build(generator, runner, checkpointer=InMemorySaver(serde=serde))

    engine.invoke(harness.request)
    # Read through the compiled graph's saver, which carries the engine allowlist.
    saver = engine._graph.checkpointer
    assert isinstance(saver, InMemorySaver)
    checkpoint = saver.get_tuple({"configurable": {"thread_id": harness.request.run_id}})

    assert checkpoint is not None
    values = checkpoint.checkpoint["channel_values"]
    assert values["status"] is RunStatus.VALIDATED
    assert isinstance(values["specification"], ArtifactRef)
    assert not [record for record in caplog.records if "msgpack" in record.getMessage()]


def test_failed_run_restores_an_existing_file(harness: Harness) -> None:
    target = harness.workspace / TARGET_FILE
    target.parent.mkdir(parents=True)
    target.write_text("ORIGINAL = 0\n", encoding="utf-8")
    generator, _ = llm_generator(*(generation_args() for _ in range(3)))
    runner = ScriptedRunner(
        [CommandResult(command_name="ruff-check", exit_code=1, stdout="E501") for _ in range(3)]
    )

    state = harness.build(generator, runner).invoke(harness.request)

    assert state.status is RunStatus.FAILED
    assert state.workspace_restored
    assert failure_of(harness, state).category == "native_validation"
    assert target.read_text(encoding="utf-8") == "ORIGINAL = 0\n"


def test_failed_run_removes_a_new_file_and_its_directories(harness: Harness) -> None:
    generator, _ = llm_generator(generation_args())
    runner = ScriptedRunner([ValidationInfrastructureError("image not found")])

    state = harness.build(generator, runner).invoke(harness.request)

    assert state.status is RunStatus.FAILED
    assert state.workspace_restored
    assert list(harness.workspace.iterdir()) == []


def test_validated_run_keeps_its_changes(harness: Harness) -> None:
    generator, _ = llm_generator(generation_args())

    state = harness.build(generator).invoke(harness.request)

    assert state.status is RunStatus.VALIDATED
    assert not state.workspace_restored
    assert [original.path for original in state.original_files] == [TARGET_FILE]
    assert (harness.workspace / TARGET_FILE).read_text(encoding="utf-8") == "VALUE = 1\n"


def test_failed_run_without_writes_skips_rollback(harness: Harness) -> None:
    generator, _ = llm_generator(*(unapproved_file_args() for _ in range(3)))

    state = harness.build(generator).invoke(harness.request)

    assert state.status is RunStatus.FAILED
    assert state.original_files == ()
    assert not state.workspace_restored


def test_rollback_failure_is_reported(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_restore(*args: object) -> None:
        raise OSError("read-only file system")

    monkeypatch.setattr(harness.registry, "restore", broken_restore)
    generator, _ = llm_generator(generation_args())
    runner = ScriptedRunner([ValidationInfrastructureError("image not found")])

    state = harness.build(generator, runner).invoke(harness.request)

    assert state.status is RunStatus.FAILED
    assert not state.workspace_restored
    failure = failure_of(harness, state)
    assert failure.category == "rollback"
    assert "read-only file system" in failure.diagnostics


def test_busy_workspace_fails_without_running(harness: Harness) -> None:
    generator, model = llm_generator(generation_args())

    with harness.registry.lock(WORKSPACE_ID):
        state = harness.build(generator).invoke(harness.request)

    assert state.status is RunStatus.FAILED
    assert failure_of(harness, state).category == "workspace_busy"
    assert model.prompts == []
    assert not (harness.workspace / TARGET_FILE).exists()
