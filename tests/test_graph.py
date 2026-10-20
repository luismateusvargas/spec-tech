"""Agent handoff, durable state, scope reporting, and failure restoration."""

from __future__ import annotations

import asyncio
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
from conftest import TARGET_FILE, generation_args
from mcp.server.fastmcp.exceptions import ToolError

from sdd_engine import mcp_server
from sdd_engine.artifacts import ArtifactError
from sdd_engine.errors import (
    ProfileError,
    RunNotFoundError,
    SpecContractError,
    WorkspaceMismatchError,
)
from sdd_engine.limits import MAX_FILE_CHARS
from sdd_engine.models import CommandResult, GraphInput, RunPhase, RunStatus, Target, Tier
from sdd_engine.service import (
    begin_task,
    configure_profile,
    finish_task,
    get_run_report,
    submit,
)
from sdd_engine.store import ProjectStore, project_database
from sdd_engine.validation import CommandSpec, ValidationProfile, standard_commands

SPEC = "# Task\n\nStatus: ready\n\n## Outcome\n\nExpose VALUE = 1.\n"
SPEC_PATH = "specs/task.md"


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root), *args), check=True, capture_output=True, text=True
    )
    return completed.stdout


def _commit(root: Path, *args: str) -> None:
    _git(root, "-c", "user.email=test@example.test", "-c", "user.name=Test", "commit", *args)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a disposable Git worktree and a passing isolated check runner."""
    root = tmp_path / "project"
    root.mkdir()
    _git(root, "init", "-q")
    _commit(root, "--allow-empty", "-qm", "initial")
    profile = ValidationProfile(
        image="busybox:1.37", commands=(CommandSpec(name="check", argv=("true",)),)
    )
    configure_profile(str(root), "python", profile.model_dump(mode="json"))

    def pass_check(
        self: object, command: CommandSpec, workspace: Path, profile: ValidationProfile
    ) -> CommandResult:
        return CommandResult(command_name=command.name, exit_code=0)

    monkeypatch.setattr("sdd_engine.validation.DockerCommandRunner.run", pass_check)
    return root


def _begin(root: Path, **overrides: Any) -> dict[str, object]:
    arguments: dict[str, Any] = {
        "tier": "simple",
        "target": "python",
        "model": "planned-model",
        "spec": SPEC,
        "target_files": [TARGET_FILE],
    }
    arguments.update(overrides)
    return begin_task(str(root), **arguments)


def test_begin_pauses_and_persists_prompt(project: Path) -> None:
    result = _begin(project)
    prompt = result["prompt"]
    assert isinstance(prompt, dict)
    assert prompt["specification_text"] == SPEC
    assert prompt["allowed_target_files"] == [TARGET_FILE]
    report = cast(dict[str, Any], get_run_report(str(project), str(result["run_id"])))
    assert report["model"] == "planned-model"
    assert report["phase"] == "pending"
    assert report["prompt"] == prompt
    assert project_database(project) == project / ".git" / "spec-tech" / "engine.db"


def test_submit_validates_and_finish_records_declared_change(project: Path) -> None:
    run_id = str(_begin(project)["run_id"])
    result = cast(dict[str, Any], submit(str(project), run_id, generation_args()))
    assert result["state"]["status"] == RunStatus.VALIDATED.value
    assert (project / TARGET_FILE).read_text(encoding="utf-8") == "VALUE = 1\n"
    report = cast(dict[str, Any], finish_task(str(project), run_id))
    assert report["scope_report"]["changes"] == [
        {"path": TARGET_FILE, "label": "declared", "flags": []}
    ]
    assert report["validation_report"]["passed"] is True
    record = ProjectStore(project_database(project)).run(run_id)
    assert record.profile_revision == 1
    assert (
        record.profile_digest
        == ValidationProfile(
            image="busybox:1.37", commands=(CommandSpec(name="check", argv=("true",)),)
        ).digest()
    )
    assert report["validation_report"]["profile_revision"] == record.profile_revision
    assert report["validation_report"]["profile_digest"] == record.profile_digest
    store = ProjectStore(project_database(project))
    with store.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0] > 0


def test_bad_submission_retries_with_contract_feedback(project: Path) -> None:
    run_id = str(_begin(project)["run_id"])
    first = cast(
        dict[str, Any],
        submit(str(project), run_id, generation_args(documentation_metadata="missing")),
    )
    assert "# Arguments and # Errors" in first["prompt"]["generation_feedback"]
    second = cast(dict[str, Any], submit(str(project), run_id, generation_args()))
    assert second["state"]["status"] == RunStatus.VALIDATED.value
    assert second["state"]["generation_attempts"] == 2


def test_failed_run_restores_agent_edits(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_check(
        self: object, command: CommandSpec, workspace: Path, profile: ValidationProfile
    ) -> CommandResult:
        return CommandResult(command_name=command.name, exit_code=1)

    monkeypatch.setattr("sdd_engine.validation.DockerCommandRunner.run", fail_check)
    run_id = str(_begin(project)["run_id"])
    (project / "rogue.py").write_text("# noqa\n", encoding="utf-8")
    for _ in range(3):
        result = cast(dict[str, Any], submit(str(project), run_id, generation_args()))
    assert result["state"]["status"] == RunStatus.FAILED.value
    report = cast(dict[str, Any], finish_task(str(project), run_id))
    assert report["scope_report"]["restored"] is True
    assert report["scope_report"]["changes"] == [
        {"path": "rogue.py", "label": "undeclared", "flags": ["suppression_added"]}
    ]
    assert not (project / "rogue.py").exists()
    assert not (project / TARGET_FILE).exists()


def test_head_move_refuses_broader_rollback(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_check(
        self: object, command: CommandSpec, workspace: Path, profile: ValidationProfile
    ) -> CommandResult:
        return CommandResult(command_name=command.name, exit_code=1)

    monkeypatch.setattr("sdd_engine.validation.DockerCommandRunner.run", fail_check)
    run_id = str(_begin(project)["run_id"])
    (project / "rogue.py").write_text("x\n", encoding="utf-8")
    for _ in range(3):
        submit(str(project), run_id, generation_args())
    _commit(project, "--allow-empty", "-qm", "moved")
    report = cast(dict[str, Any], finish_task(str(project), run_id))
    assert report["scope_report"]["head_changed"] is True
    assert report["scope_report"]["restored"] is False
    assert (project / "rogue.py").exists()


def test_profile_history_and_git_target_rejection(project: Path) -> None:
    profile = ValidationProfile(
        image="busybox:1.37", commands=(CommandSpec(name="check", argv=("true",)),)
    )
    result = configure_profile(str(project), "python", profile.model_dump(mode="json"))
    assert result["revision"] == 2
    with ProjectStore(project_database(project)).connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM profile_history").fetchone()[0] == 2
    with pytest.raises(ValueError):
        GraphInput.model_validate(
            {
                "run_id": "r",
                "workspace_id": "w",
                "target": "python",
                "tier": "simple",
                "specification": {"digest": "0" * 64, "byte_length": 0, "media_type": "text/plain"},
                "target_files": [".git/config"],
            }
        )


def test_finish_rejects_pending_run(project: Path) -> None:
    run_id = str(_begin(project)["run_id"])
    with pytest.raises(ArtifactError, match="awaiting"):
        finish_task(str(project), run_id)


def test_second_run_on_the_same_worktree_waits_for_finish(project: Path) -> None:
    first = _begin(project)
    with pytest.raises(ArtifactError, match="unfinished"):
        _begin(project)
    submit(str(project), str(first["run_id"]), generation_args())
    finish_task(str(project), str(first["run_id"]))
    assert "prompt" in _begin(project)


def test_worktrees_share_the_project_database(project: Path) -> None:
    sibling = project.parent / "sibling"
    _git(project, "worktree", "add", "--detach", str(sibling))
    assert project_database(sibling) == project_database(project)


def test_run_rejects_access_from_sibling_worktree(project: Path) -> None:
    sibling = project.parent / "sibling"
    _git(project, "worktree", "add", "--detach", str(sibling))
    run_id = str(_begin(project)["run_id"])

    with pytest.raises(WorkspaceMismatchError, match="belongs to worktree"):
        get_run_report(str(sibling), run_id)
    with pytest.raises(WorkspaceMismatchError, match="belongs to worktree"):
        submit(str(sibling), run_id, generation_args())
    with pytest.raises(WorkspaceMismatchError, match="belongs to worktree"):
        finish_task(str(sibling), run_id)

    record = ProjectStore(project_database(project)).run(run_id)
    assert record.phase is RunPhase.PENDING
    assert not (project / TARGET_FILE).exists()
    assert not (sibling / TARGET_FILE).exists()
    assert "state" in submit(str(project), run_id, generation_args())


def test_profile_change_blocks_pending_run(project: Path) -> None:
    run_id = str(_begin(project)["run_id"])
    profile = ValidationProfile(
        image="busybox:1.37", commands=(CommandSpec(name="another-check", argv=("true",)),)
    )
    configure_profile(str(project), "python", profile.model_dump(mode="json"))

    with pytest.raises(ProfileError, match="changed during the active run"):
        submit(str(project), run_id, generation_args())
    with pytest.raises(ProfileError, match="changed during the active run"):
        finish_task(str(project), run_id)
    assert ProjectStore(project_database(project)).run(run_id).phase is RunPhase.PENDING
    assert not (project / TARGET_FILE).exists()


def test_profile_change_blocks_terminal_run(project: Path) -> None:
    run_id = str(_begin(project)["run_id"])
    submit(str(project), run_id, generation_args())
    configure_profile(str(project), "python", {"image": "busybox:1.37"})

    with pytest.raises(ProfileError, match="changed during the active run"):
        finish_task(str(project), run_id)
    assert ProjectStore(project_database(project)).run(run_id).phase is RunPhase.TERMINAL


def test_profile_digest_detects_body_change_without_revision(project: Path) -> None:
    run_id = str(_begin(project)["run_id"])
    changed = ValidationProfile(
        image="busybox:1.37", commands=(CommandSpec(name="changed", argv=("true",)),)
    )
    with ProjectStore(project_database(project)).connect() as connection:
        connection.execute(
            "UPDATE profiles SET body = ? WHERE target = ?",
            (changed.model_dump_json(), Target.PYTHON.value),
        )

    with pytest.raises(ProfileError, match="changed during the active run"):
        submit(str(project), run_id, generation_args())


def test_configure_profile_uses_standard_commands_when_omitted(project: Path) -> None:
    configure_profile(str(project), "python", {"image": "busybox:1.37"})

    actual = ProjectStore(project_database(project)).get_profile(Target.PYTHON)
    assert actual.commands == standard_commands(Target.PYTHON, project)


@pytest.mark.parametrize("version", [1, 2])
def test_store_upgrades_existing_run_rows_to_schema_three(tmp_path: Path, version: int) -> None:
    database = tmp_path / "engine.db"
    request = GraphInput.model_validate(
        {
            "run_id": "existing",
            "workspace_id": "existing",
            "target": "python",
            "tier": "simple",
            "specification": {"digest": "0" * 64, "byte_length": 0, "media_type": "text/plain"},
            "target_files": [TARGET_FILE],
        }
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE runs (run_id TEXT PRIMARY KEY, workspace TEXT NOT NULL, "
            "model TEXT NOT NULL, request TEXT NOT NULL, head TEXT NOT NULL, "
            "start_tree TEXT NOT NULL, phase TEXT NOT NULL, outcome TEXT, state TEXT, "
            "prompt TEXT, submitted TEXT NOT NULL DEFAULT '[]', scope_report TEXT)"
        )
        connection.execute(
            "INSERT INTO runs(run_id, workspace, model, request, head, start_tree, phase) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "existing",
                str(tmp_path),
                "model",
                request.model_dump_json(),
                "head",
                "tree",
                "pending",
            ),
        )
        connection.execute("PRAGMA user_version=1" if version == 1 else "PRAGMA user_version=2")

    store = ProjectStore(database)
    upgraded = ProjectStore(database).run("existing")

    assert upgraded.phase is RunPhase.PENDING
    assert (upgraded.profile_revision, upgraded.profile_digest) == (1, "")
    assert (upgraded.spec_path, upgraded.spec_blob) == (None, None)
    with store.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        indexes = {str(row["name"]) for row in connection.execute("PRAGMA index_list(runs)")}
        assert "runs_active_workspace" in indexes


def test_store_reports_missing_run_with_domain_error(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "engine.db")

    with pytest.raises(RunNotFoundError, match="does not exist"):
        store.run("missing")


def test_ignore_edit_does_not_hide_a_starting_untracked_file(project: Path) -> None:
    (project / "notes.txt").write_text("starting notes\n", encoding="utf-8")
    run_id = str(_begin(project)["run_id"])
    (project / ".gitignore").write_text("notes.txt\n", encoding="utf-8")
    submit(str(project), run_id, generation_args())
    report = cast(dict[str, Any], finish_task(str(project), run_id))
    paths = {item["path"] for item in report["scope_report"]["changes"]}
    assert paths == {".gitignore", TARGET_FILE}
    assert (project / "notes.txt").read_text(encoding="utf-8") == "starting notes\n"


def test_deleted_test_file_is_flagged_for_review(project: Path) -> None:
    old_test = project / "tests" / "test_old.py"
    old_test.parent.mkdir()
    old_test.write_text("def test_old() -> None: pass\n", encoding="utf-8")
    run_id = str(_begin(project)["run_id"])
    old_test.unlink()
    submit(str(project), run_id, generation_args())
    report = cast(dict[str, Any], finish_task(str(project), run_id))
    findings = {item["path"]: item for item in report["scope_report"]["changes"]}
    assert findings["tests/test_old.py"] == {
        "path": "tests/test_old.py",
        "label": "undeclared",
        "flags": ["test_deleted"],
    }


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        ("# Task\n\nStatus: blocked\n\n## Outcome\nWait for decision.\n", "'blocked'"),
        ("# Task\n\nStatus: draft\n", "'draft'"),
        ("# Task\n\nStatus: draft | ready | blocked\n", "'draft | ready | blocked'"),
        ("# Task\n\nExpose VALUE = 1.\n", r"found \[\]"),
        ("# Task\n\nStatus: ready\nStatus: ready\n", "'ready', 'ready'"),
        ("# Task\n\nStatus:\nready\n", r"found \[''\]"),
        ("## Outcome\n\nStatus: ready\n", r"found \[\]"),
    ],
)
def test_begin_requires_a_ready_spec_header(project: Path, spec: str, message: str) -> None:
    with pytest.raises(SpecContractError, match=message):
        _begin(project, spec=spec)

    assert "prompt" in _begin(project)


def test_begin_reads_status_only_from_the_spec_header(project: Path) -> None:
    spec = "# Task\n\nstatus: Ready\n\n## Open decisions\n\n  status: blocked\nStatus: blocked\n"

    with pytest.raises(SpecContractError, match="'Ready'"):
        _begin(project, spec=spec)
    result = _begin(project, spec=spec.replace("Ready", "ready", 1))

    assert "prompt" in result


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"spec": None}, "requires spec or spec_path"),
        ({"target_files": None}, "target_files is required"),
        (
            {"spec": SPEC.replace("\n\n## ", "\nTarget files: pkg/other.py\n\n## ")},
            "must match the spec header",
        ),
        (
            {"spec": SPEC.replace("\n\n## ", "\nTarget files: ../outside.py\n\n## ")},
            "safe relative POSIX path",
        ),
        (
            {"spec": SPEC.replace("\n\n## ", "\nTarget files: a.py, ./a.py\n\n## ")},
            "repeats a path",
        ),
    ],
)
def test_begin_rejects_inconsistent_spec_arguments(
    project: Path, overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(SpecContractError, match=message):
        _begin(project, **overrides)


@pytest.fixture
def committed_spec(project: Path) -> str:
    """Commit a ready spec that declares its target files."""
    spec = (
        "# Task\n\nStatus: ready\nTarget files: `pkg/module.py`, pkg/other.py\n\n"
        "## Outcome\n\nExpose VALUE = 1.\n"
    )
    (project / "specs").mkdir()
    (project / SPEC_PATH).write_text(spec, encoding="utf-8")
    _git(project, "add", "--", SPEC_PATH)
    _commit(project, "-qm", "spec")
    return spec


def test_begin_binds_a_committed_spec_and_its_target_files(
    project: Path, committed_spec: str
) -> None:
    result = _begin(project, spec=None, spec_path=SPEC_PATH, target_files=None)

    prompt = cast(dict[str, Any], result["prompt"])
    assert prompt["specification_text"] == committed_spec
    assert prompt["allowed_target_files"] == ["pkg/module.py", "pkg/other.py"]
    record = ProjectStore(project_database(project)).run(str(result["run_id"]))
    expected_blob = _git(project, "rev-parse", f"HEAD:{SPEC_PATH}").strip()
    assert (record.spec_path, record.spec_blob) == (SPEC_PATH, expected_blob)


def test_committed_spec_accepts_matching_text_and_target_files(
    project: Path, committed_spec: str
) -> None:
    result = _begin(
        project,
        spec=committed_spec,
        spec_path=f"./{SPEC_PATH}",
        target_files=["pkg/other.py", "pkg/./module.py"],
    )

    record = ProjectStore(project_database(project)).run(str(result["run_id"]))
    assert record.spec_path == SPEC_PATH


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"spec": SPEC}, "differs from 'specs/task.md' committed at HEAD"),
        ({"target_files": [TARGET_FILE]}, "must match the spec header"),
        ({"spec_path": "specs/missing.md"}, "not committed at HEAD"),
        ({"spec_path": "specs"}, "not a regular file"),
        ({"spec_path": "../task.md"}, "safe relative POSIX path"),
    ],
)
def test_committed_spec_binding_rejects_mismatches(
    project: Path, committed_spec: str, overrides: dict[str, object], message: str
) -> None:
    arguments: dict[str, object] = {"spec": None, "spec_path": SPEC_PATH, "target_files": None}
    arguments.update(overrides)

    with pytest.raises(SpecContractError, match=message):
        _begin(project, **arguments)


@pytest.mark.parametrize("staged", [False, True])
def test_committed_spec_rejects_uncommitted_edits(
    project: Path, committed_spec: str, staged: bool
) -> None:
    (project / SPEC_PATH).write_text(committed_spec + "Also expose OTHER.\n", encoding="utf-8")
    if staged:
        _git(project, "add", "--", SPEC_PATH)

    with pytest.raises(SpecContractError, match="uncommitted changes"):
        _begin(project, spec=None, spec_path=SPEC_PATH, target_files=None)


def test_oversized_submission_is_a_retryable_contract_failure(project: Path) -> None:
    run_id = str(_begin(project)["run_id"])
    oversized = generation_args(files=[{"path": TARGET_FILE, "content": "x" * 5_000_000}])

    first = cast(dict[str, Any], submit(str(project), run_id, oversized))

    assert "generation_contract" in first["prompt"]["generation_feedback"]
    assert not (project / TARGET_FILE).exists()
    second = cast(dict[str, Any], submit(str(project), run_id, generation_args()))
    assert second["state"]["status"] == RunStatus.VALIDATED.value
    assert second["state"]["generation_attempts"] == 2


def test_target_file_too_large_to_resubmit_fails_hydration(project: Path) -> None:
    (project / "pkg").mkdir()
    (project / TARGET_FILE).write_text("x" * (MAX_FILE_CHARS + 1), encoding="utf-8")

    result = cast(dict[str, Any], _begin(project))

    assert result["state"]["status"] == RunStatus.FAILED.value
    report = cast(dict[str, Any], get_run_report(str(project), str(result["run_id"])))
    assert report["failure_report"]["category"] == "hydration"
    assert "whole-file limit" in report["failure_report"]["diagnostics"]


def _schema_definition(schema: dict[str, Any], name: str) -> dict[str, Any]:
    reference = str(schema["properties"][name]["$ref"]).rsplit("/", 1)[-1]
    return cast(dict[str, Any], schema["$defs"][reference])


def test_mcp_tools_publish_typed_schemas() -> None:
    tools = {tool.name: tool for tool in asyncio.run(mcp_server.implementer.list_tools())}
    begin_schema = tools["begin_task"].inputSchema
    submit_schema = tools["submit"].inputSchema

    payload = _schema_definition(submit_schema, "files")
    assert _schema_definition(begin_schema, "tier")["enum"] == [tier.value for tier in Tier]
    assert _schema_definition(begin_schema, "target")["enum"] == [item.value for item in Target]
    assert set(begin_schema["required"]) == {"workspace", "tier", "target", "model"}
    assert set(payload["properties"]) == {
        "files",
        "documentation_metadata",
        "error_handling_mapping",
        "no_failure_paths",
    }
    assert payload["required"] == ["files", "documentation_metadata", "error_handling_mapping"]
    assert payload["additionalProperties"] is False


def test_mcp_submit_leaves_content_rules_to_the_graph(project: Path) -> None:
    run_id = str(_begin(project)["run_id"])
    arguments = {
        "workspace": str(project),
        "run_id": run_id,
        "files": generation_args(documentation_metadata="Args: Raises:"),
    }

    asyncio.run(mcp_server.implementer.call_tool("submit", arguments))

    report = cast(dict[str, Any], get_run_report(str(project), run_id))
    assert report["phase"] == RunPhase.PENDING.value
    assert "each followed by text" in report["prompt"]["generation_feedback"]
    assert not (project / TARGET_FILE).exists()


def test_mcp_submit_rejects_malformed_payloads_before_the_graph(project: Path) -> None:
    run_id = str(_begin(project)["run_id"])
    malformed = generation_args()
    del malformed["documentation_metadata"]
    arguments = {"workspace": str(project), "run_id": run_id, "files": malformed}

    with pytest.raises(ToolError, match="documentation_metadata"):
        asyncio.run(mcp_server.implementer.call_tool("submit", arguments))

    report = cast(dict[str, Any], get_run_report(str(project), run_id))
    assert report["prompt"]["generation_feedback"] is None


def test_scope_flags_go_rust_cpp_and_spec_files(project: Path) -> None:
    run_id = str(_begin(project)["run_id"])
    (project / "pkg_test.go").write_text(
        "package p\nfunc TestX(t *testing.T) { t.Skip() }\n", encoding="utf-8"
    )
    (project / "ui.spec.ts").write_text("test.skip('later', () => {})\n", encoding="utf-8")
    (project / "lib.rs").write_text("#[allow(dead_code)]\n#[ignore]\nfn f() {}\n", encoding="utf-8")
    (project / "engine.cpp").write_text("// NOLINT\nvoid t() { GTEST_SKIP(); }\n", encoding="utf-8")
    submit(str(project), run_id, generation_args())
    report = cast(dict[str, Any], finish_task(str(project), run_id))
    findings = {item["path"]: item["flags"] for item in report["scope_report"]["changes"]}
    assert findings["pkg_test.go"] == ["test_changed_outside_plan", "skip_added"]
    assert findings["ui.spec.ts"] == ["test_changed_outside_plan", "skip_added"]
    assert findings["lib.rs"] == ["suppression_added", "skip_added"]
    assert findings["engine.cpp"] == ["suppression_added", "skip_added"]


def test_failed_run_prunes_empty_untracked_directories(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_check(
        self: object, command: CommandSpec, workspace: Path, profile: ValidationProfile
    ) -> CommandResult:
        return CommandResult(command_name=command.name, exit_code=1)

    monkeypatch.setattr("sdd_engine.validation.DockerCommandRunner.run", fail_check)
    run_id = str(_begin(project)["run_id"])
    nested = project / "untracked_dir" / "sub" / "rogue.py"
    nested.parent.mkdir(parents=True)
    nested.write_text("x = 1\n", encoding="utf-8")
    for _ in range(3):
        submit(str(project), run_id, generation_args())
    report = cast(dict[str, Any], finish_task(str(project), run_id))
    assert report["scope_report"]["restored"] is True
    assert not (project / "untracked_dir").exists()
