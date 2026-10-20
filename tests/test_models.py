"""Contract validation at the public, implementer, and checkpoint boundaries."""

from __future__ import annotations

import pytest
from conftest import generation_args
from pydantic import ValidationError

from sdd_engine.limits import MAX_FILE_CHARS
from sdd_engine.models import (
    CommandResult,
    GenerationOutput,
    GenerationPrompt,
    GraphInput,
    GraphState,
    RunStatus,
    Target,
    Tier,
    ValidationReport,
)
from sdd_engine.paths import canonical_relative_path

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
    "doc",
    [
        "# Arguments\nNone.\n\n# Errors\nNone.",
        "Args:\n    x: int\n\nRaises:\n    ValueError: on bad input.",
        "@param x The value\n@throws Error on failure",
        "Args:\n    x: int\n\nReturns:\n    int\n\nRaises:\n    ValueError: on bad input.",
    ],
)
def test_generation_output_accepts_language_native_doc_sections(doc: str) -> None:
    output = GenerationOutput.model_validate(generation_args(documentation_metadata=doc))

    assert output.documentation_metadata == doc


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


@pytest.mark.parametrize(
    "path", ["/etc/passwd", "../outside.rs", "src/../../x.rs", "src\\lib.rs", ".git/config"]
)
def test_graph_input_rejects_unsafe_target_paths(path: str) -> None:
    with pytest.raises(ValidationError, match="safe relative POSIX path"):
        GraphInput.model_validate(api_payload(target_files=[path]))


def test_graph_input_rejects_duplicate_target_paths() -> None:
    with pytest.raises(ValidationError, match="unique paths"):
        GraphInput.model_validate(api_payload(target_files=["a.rs", "a.rs"]))


@pytest.mark.parametrize("alias", ["src/./x.py", "src//x.py"])
def test_canonical_paths_reject_aliased_duplicates(alias: str) -> None:
    request = GraphInput.model_validate(api_payload(target_files=[alias]))
    output = GenerationOutput.model_validate(
        generation_args(files=[{"path": alias, "content": "x"}])
    )

    assert canonical_relative_path(alias) == "src/x.py"
    assert request.target_files == ("src/x.py",)
    assert output.files[0].path == "src/x.py"
    with pytest.raises(ValidationError, match="unique paths"):
        GraphInput.model_validate(api_payload(target_files=["src/x.py", alias]))
    with pytest.raises(ValidationError, match="unique paths"):
        GenerationOutput.model_validate(
            generation_args(
                files=[
                    {"path": "src/x.py", "content": "x"},
                    {"path": alias, "content": "y"},
                ]
            )
        )


@pytest.mark.parametrize(
    "path",
    [
        ".GIT/hooks/pre-commit",
        "src/x\x00.py",
        "src/x\n.py",
        "src/x\x7f.py",
        "node_modules/.bin/tsc",
        "src/node_modules/pkg/index.js",
        "build/CTestTestfile.cmake",
        "src/CMakeFiles/check.cmake",
    ],
)
def test_models_reject_protected_or_control_character_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        GraphInput.model_validate(api_payload(target_files=[path]))
    with pytest.raises(ValidationError):
        GenerationOutput.model_validate(generation_args(files=[{"path": path, "content": "x"}]))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"documentation_metadata": "# Arguments only"}, "# Arguments and # Errors"),
        ({"documentation_metadata": "@param x The value\n@returns The result"}, "# Errors"),
        ({"documentation_metadata": "Args: Raises:"}, "each followed by text"),
        ({"documentation_metadata": "Args:\n    x: int\nRaises:\n"}, "each followed by text"),
        (
            {"documentation_metadata": "# Arguments\nx: value.\n# Errors\nNone.\n```x```"},
            "inline code",
        ),
        ({"files": [{"path": "../escape.py", "content": "x"}]}, "safe relative POSIX path"),
        ({"files": [{"path": ".", "content": "x"}]}, "identify a file"),
        ({"files": []}, "1 to 128 unique paths"),
        ({"error_handling_mapping": []}, "at least one entry unless no_failure_paths"),
        ({"no_failure_paths": True}, "must be empty when no_failure_paths"),
        ({"files": [{"path": "big.py", "content": "x" * (MAX_FILE_CHARS + 1)}]}, "at most"),
        (
            {
                "files": [
                    {"path": f"part{index}.py", "content": "x" * MAX_FILE_CHARS}
                    for index in range(4)
                ]
            },
            "a submission may contain at most 3000000",
        ),
        (
            {
                "files": [
                    {"path": f"part{index}.py", "content": "\x01" * 700_000} for index in range(2)
                ]
            },
            "as stored JSON",
        ),
        (
            {"files": [{"path": "a.py", "content": "1"}, {"path": "a.py", "content": "2"}]},
            "1 to 128 unique paths",
        ),
    ],
)
def test_generation_output_enforces_contract(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        GenerationOutput.model_validate(generation_args(**overrides))


def test_generation_output_accepts_an_explicit_absence_of_failure_paths() -> None:
    output = GenerationOutput.model_validate(
        generation_args(error_handling_mapping=[], no_failure_paths=True)
    )

    assert output.error_handling_mapping == ()
    assert output.no_failure_paths is True


def test_generation_prompt_describes_the_submission_contract() -> None:
    prompt = GenerationPrompt(
        run_id="run-1",
        target=Target.PYTHON,
        tier=Tier.SIMPLE,
        allowed_target_files=("pkg/module.py",),
        target_entities=(),
        specification_text="Status: ready",
        referenced_context=(),
        engineering_guidance=(),
    )

    assert prompt.submission_schema == GenerationOutput.model_json_schema()
    assert "allowed_target_files" in prompt.submission_semantics
    assert "no_failure_paths" in prompt.submission_semantics


def test_graph_state_extends_the_graph_input_fields() -> None:
    assert issubclass(GraphState, GraphInput)
    assert list(GraphState.model_fields)[: len(GraphInput.model_fields)] == list(
        GraphInput.model_fields
    )


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
