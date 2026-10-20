"""Agent handoff, durable state, scope reporting, and failure restoration."""

from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
from conftest import TARGET_FILE, generation_args

from sdd_engine.artifacts import ArtifactError
from sdd_engine.errors import ProfileError, RunNotFoundError, WorkspaceMismatchError
from sdd_engine.models import CommandResult, GraphInput, RunPhase, RunStatus, Target
from sdd_engine.service import (
    begin_task,
    configure_profile,
    finish_task,
    get_run_report,
    submit,
)
from sdd_engine.store import ProjectStore, project_database
from sdd_engine.validation import CommandSpec, ValidationProfile, standard_commands


def _git(root: Path, *args: str) -> None:
    subprocess.run(("git", "-C", str(root), *args), check=True, capture_output=True)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a disposable Git worktree and a passing isolated check runner."""
    root = tmp_path / "project"
    root.mkdir()
    _git(root, "init", "-q")
    _git(
        root,
        "-c",
        "user.email=test@example.test",
        "-c",
        "user.name=Test",
        "commit",
        "--allow-empty",
        "-qm",
        "initial",
    )
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


def _begin(root: Path) -> dict[str, object]:
    return begin_task(
        str(root), "Expose VALUE = 1.", "simple", "python", [TARGET_FILE], "planned-model"
    )


def test_begin_pauses_and_persists_prompt(project: Path) -> None:
    result = _begin(project)
    prompt = result["prompt"]
    assert isinstance(prompt, dict)
    assert prompt["specification_text"] == "Expose VALUE = 1."
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
    _git(
        project,
        "-c",
        "user.email=test@example.test",
        "-c",
        "user.name=Test",
        "commit",
        "--allow-empty",
        "-qm",
        "moved",
    )
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


def test_begin_rejects_blocked_task_spec(project: Path) -> None:
    blocked_spec = "# Task\n\nStatus: blocked\n\n## Outcome\nWait for decision.\n"
    with pytest.raises(ValueError, match="Status: blocked"):
        begin_task(str(project), blocked_spec, "simple", "python", [TARGET_FILE], "planned-model")


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
