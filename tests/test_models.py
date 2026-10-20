"""Contract validation at the public, LLM, and checkpoint boundaries."""

from __future__ import annotations

import pytest
from conftest import generation_args
from pydantic import ValidationError

from sdd_engine.models import (
    CommandResult,
    GenerationOutput,
    GraphInput,
    GraphState,
    RunStatus,
    Target,
    Tier,
    ValidationReport,
)

SPEC = {"digest": "a" * 64, "byte_length": 10, "media_type": "text/markdown"}


def api_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_id": "run-1",
        "workspace_id": "ws-1",
        "target": "rust",
        "tier": "saas",
        "specification": SPEC,
        "target_files": ["src/lib.rs"],
        "context": [SPEC],
    }
    payload.update(overrides)
    return payload


def test_graph_input_accepts_json_shaped_api_payload() -> None:
    request = GraphInput.model_validate(api_payload())

    assert request.target is Target.RUST
    assert request.tier is Tier.SAAS
    assert request.target_files == ("src/lib.rs",)
    assert request.context[0].digest == "a" * 64


def test_graph_state_accepts_checkpoint_shaped_values() -> None:
    state = GraphState.model_validate(api_payload(status="validation_failed"))

    assert state.status is RunStatus.VALIDATION_FAILED


def test_generation_output_accepts_parser_lists() -> None:
    output = GenerationOutput.model_validate(generation_args())

    assert isinstance(output.error_handling_mapping, tuple)


@pytest.mark.parametrize(
    "overrides",
    [
        {"run_id": 7},
        {"target": "cobol"},
        {"tier": "enterprise"},
        {"tier": None},
        {"target_files": "src/lib.rs"},
        {"specification": {**SPEC, "byte_length": "10"}},
        {"unexpected": True},
    ],
)
def test_graph_input_still_rejects_coercion_and_unknown_fields(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        GraphInput.model_validate(api_payload(**overrides))


@pytest.mark.parametrize("path", ["/etc/passwd", "../outside.rs", "src/../../x.rs", "src\\lib.rs"])
def test_graph_input_rejects_unsafe_target_paths(path: str) -> None:
    with pytest.raises(ValidationError, match="safe relative POSIX path"):
        GraphInput.model_validate(api_payload(target_files=[path]))


def test_graph_input_rejects_duplicate_target_paths() -> None:
    with pytest.raises(ValidationError, match="unique paths"):
        GraphInput.model_validate(api_payload(target_files=["a.rs", "a.rs"]))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"documentation_metadata": "# Arguments only"}, "# Arguments and # Errors"),
        ({"documentation_metadata": "# Arguments\n# Errors\n```x```"}, "inline code"),
        ({"files": [{"path": "../escape.py", "content": "x"}]}, "safe relative POSIX path"),
        ({"files": [{"path": ".", "content": "x"}]}, "identify a file"),
        ({"files": []}, "1 to 128 unique paths"),
        (
            {"files": [{"path": "a.py", "content": "1"}, {"path": "a.py", "content": "2"}]},
            "1 to 128 unique paths",
        ),
    ],
)
def test_generation_output_enforces_contract(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        GenerationOutput.model_validate(generation_args(**overrides))


def test_validation_report_status_must_match_commands() -> None:
    failed = CommandResult(command_name="check", exit_code=1)

    with pytest.raises(ValidationError, match="passed must match"):
        ValidationReport(target=Target.GO, passed=True, commands=(failed,), summary="x")


def test_graph_state_bounds_target_path_length() -> None:
    with pytest.raises(ValidationError):
        GraphState.model_validate(api_payload(target_files=["a" * 513]))


def test_graph_input_requires_a_tier() -> None:
    payload = api_payload()
    del payload["tier"]

    with pytest.raises(ValidationError, match="tier"):
        GraphInput.model_validate(payload)
