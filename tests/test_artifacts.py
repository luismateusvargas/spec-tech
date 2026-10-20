"""Content-addressed storage integrity and workspace confinement."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from sdd_engine.artifacts import (
    ArtifactError,
    FileArtifactStore,
    WorkspaceBusyError,
    WorkspaceRegistry,
)
from sdd_engine.models import FailureReport


def test_store_round_trips_content_and_models(tmp_path: Path) -> None:
    store = FileArtifactStore(tmp_path)
    report = FailureReport(category="c", summary="s", diagnostics="d")

    reference = store.put_model(report)

    assert store.get_model(reference, FailureReport, 10_000) == report
    assert store.put_model(report) == reference


def test_store_rejects_tampered_content(tmp_path: Path) -> None:
    store = FileArtifactStore(tmp_path)
    reference = store.put(b"original", "text/plain")
    (tmp_path / reference.digest[:2] / reference.digest[2:]).write_bytes(b"tampered")

    with pytest.raises(ArtifactError, match="integrity"):
        store.get(reference, 1_000)


def test_store_enforces_hydration_limit(tmp_path: Path) -> None:
    store = FileArtifactStore(tmp_path)
    reference = store.put(b"x" * 100, "text/plain")

    with pytest.raises(ArtifactError, match="hydration limit"):
        store.get(reference, 99)


def test_workspace_writes_and_reads_inside_root(tmp_path: Path) -> None:
    registry = WorkspaceRegistry({"ws": tmp_path})

    registry.write_text("ws", "src/new.py", "print('hi')\n")

    assert registry.read_text("ws", "src/new.py", 1_000) == "print('hi')\n"
    assert registry.read_text("ws", "missing.py", 1_000) is None


@pytest.mark.parametrize("path", ["../escape.py", "/abs.py", "a\\b.py"])
def test_workspace_rejects_unsafe_paths(tmp_path: Path, path: str) -> None:
    registry = WorkspaceRegistry({"ws": tmp_path})

    with pytest.raises(ArtifactError):
        registry.write_text("ws", path, "x")


def test_workspace_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    registry = WorkspaceRegistry({"ws": root})

    with pytest.raises(ArtifactError, match="escaped"):
        registry.write_text("ws", "link/file.py", "x")
    assert not (outside / "file.py").exists()


def test_workspace_rejects_unknown_identifier(tmp_path: Path) -> None:
    with pytest.raises(ArtifactError, match="not configured"):
        WorkspaceRegistry({}).get("missing")


def mode_of(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_write_keeps_existing_mode_and_gives_new_files_0644(tmp_path: Path) -> None:
    registry = WorkspaceRegistry({"ws": tmp_path})
    (tmp_path / "run.sh").write_text("old", encoding="utf-8")
    (tmp_path / "run.sh").chmod(0o755)

    registry.write_text("ws", "run.sh", "new")
    registry.write_text("ws", "new.py", "x")

    assert mode_of(tmp_path / "run.sh") == 0o755
    assert mode_of(tmp_path / "new.py") == 0o644


def test_restore_puts_back_existing_content_and_mode(tmp_path: Path) -> None:
    registry = WorkspaceRegistry({"ws": tmp_path})
    (tmp_path / "run.sh").write_bytes(b"original\xff")
    (tmp_path / "run.sh").chmod(0o750)
    snapshot = registry.snapshot("ws", "run.sh", 1_000)
    registry.write_text("ws", "run.sh", "generated")
    (tmp_path / "run.sh").chmod(0o600)

    registry.restore("ws", "run.sh", snapshot.content, snapshot.mode, snapshot.created_directory)

    assert (tmp_path / "run.sh").read_bytes() == b"original\xff"
    assert mode_of(tmp_path / "run.sh") == 0o750


def test_restore_removes_a_new_file_and_the_directories_it_created(tmp_path: Path) -> None:
    registry = WorkspaceRegistry({"ws": tmp_path})
    (tmp_path / "src").mkdir()
    snapshot = registry.snapshot("ws", "src/new/deep/module.py", 1_000)
    registry.write_text("ws", "src/new/deep/module.py", "x")

    registry.restore("ws", "src/new/deep/module.py", None, None, snapshot.created_directory)

    assert snapshot.created_directory == "src/new"
    assert not (tmp_path / "src" / "new").exists()
    assert (tmp_path / "src").is_dir()


def test_restore_keeps_created_directories_that_gained_other_files(tmp_path: Path) -> None:
    registry = WorkspaceRegistry({"ws": tmp_path})
    snapshot = registry.snapshot("ws", "pkg/module.py", 1_000)
    registry.write_text("ws", "pkg/module.py", "x")
    (tmp_path / "pkg" / "other.py").write_text("kept", encoding="utf-8")

    registry.restore("ws", "pkg/module.py", None, None, snapshot.created_directory)

    assert not (tmp_path / "pkg" / "module.py").exists()
    assert (tmp_path / "pkg" / "other.py").read_text(encoding="utf-8") == "kept"


def test_snapshot_enforces_its_size_limit(tmp_path: Path) -> None:
    registry = WorkspaceRegistry({"ws": tmp_path})
    (tmp_path / "big.py").write_bytes(b"x" * 100)

    with pytest.raises(ArtifactError, match="snapshot limit"):
        registry.snapshot("ws", "big.py", 99)


def test_lock_rejects_a_second_run_on_the_same_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    registry = WorkspaceRegistry({"a": root, "alias": root}, lock_directory=tmp_path / "locks")

    with registry.lock("a"), pytest.raises(WorkspaceBusyError):
        with registry.lock("alias"):
            pass
    with registry.lock("alias"):
        pass


def test_lock_allows_runs_on_different_roots(tmp_path: Path) -> None:
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    registry = WorkspaceRegistry(
        {"one": tmp_path / "one", "two": tmp_path / "two"}, lock_directory=tmp_path / "locks"
    )

    with registry.lock("one"), registry.lock("two"):
        pass


def test_lock_rejects_an_unknown_workspace(tmp_path: Path) -> None:
    registry = WorkspaceRegistry({}, lock_directory=tmp_path / "locks")

    with pytest.raises(ArtifactError, match="not configured"), registry.lock("missing"):
        pass
