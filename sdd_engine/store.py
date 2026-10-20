"""Per-project SQLite persistence for engine configuration and run artifacts."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TypeVar

from pydantic import ValidationError

from sdd_engine.artifacts import ArtifactError
from sdd_engine.models import ArtifactRef, StrictModel, Target
from sdd_engine.validation import ValidationProfile

ModelT = TypeVar("ModelT", bound=StrictModel)


def project_database(workspace: Path) -> Path:
    """Locate the shared Git directory of a worktree and its private engine database."""
    root = workspace.expanduser().resolve(strict=True)
    result = subprocess.run(
        ("git", "rev-parse", "--path-format=absolute", "--git-common-dir"),
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ArtifactError("workspace must be inside a Git repository")
    top_level = subprocess.run(
        ("git", "rev-parse", "--show-toplevel"),
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if top_level.returncode != 0 or Path(top_level.stdout.strip()).resolve() != root:
        raise ArtifactError("workspace must be the Git worktree root")
    git_dir = Path(result.stdout.strip()).resolve(strict=True)
    database = git_dir / "spec-tech" / "engine.db"
    database.parent.mkdir(mode=0o700, exist_ok=True)
    return database


class ProjectStore:
    """Keep one project's profiles, runs, checkpoints, snapshots, and artifacts together."""

    def __init__(self, database: Path) -> None:
        """Open or migrate a project database at the given path."""
        self.database = database
        self.database.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self.connect() as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version > 2:
                raise ArtifactError(f"unsupported engine database schema version {version}")
            if version == 2:
                return
            if version == 1:
                connection.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS runs_active_workspace "
                    "ON runs(workspace) WHERE phase != 'finished'"
                )
                connection.execute("PRAGMA user_version=2")
                return
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;
                CREATE TABLE IF NOT EXISTS profiles (
                    target TEXT PRIMARY KEY,
                    body TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK(revision > 0)
                );
                CREATE TABLE IF NOT EXISTS profile_history (
                    target TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    body TEXT NOT NULL,
                    changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(target, revision)
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    workspace TEXT NOT NULL,
                    model TEXT NOT NULL,
                    request TEXT NOT NULL,
                    head TEXT NOT NULL,
                    start_tree TEXT NOT NULL,
                    phase TEXT NOT NULL CHECK(phase IN ('pending', 'terminal', 'finished')),
                    outcome TEXT,
                    state TEXT,
                    prompt TEXT,
                    submitted TEXT NOT NULL DEFAULT '[]',
                    scope_report TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS snapshots (
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    path TEXT NOT NULL,
                    original TEXT NOT NULL,
                    PRIMARY KEY(run_id, path)
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    digest TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    content BLOB NOT NULL,
                    PRIMARY KEY(digest, media_type)
                );
                """
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS runs_active_workspace "
                "ON runs(workspace) WHERE phase != 'finished'"
            )
            connection.execute("PRAGMA user_version=2")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a transaction-scoped connection and close it on every path."""
        connection = sqlite3.connect(self.database, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def set_profile(self, target: Target, profile: ValidationProfile) -> int:
        """Create a reviewed profile revision through the configuration boundary."""
        body = profile.model_dump_json()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT revision FROM profiles WHERE target = ?", (target.value,)
            ).fetchone()
            revision = 1 if row is None else int(row["revision"]) + 1
            connection.execute(
                "INSERT INTO profile_history(target, revision, body) VALUES (?, ?, ?)",
                (target.value, revision, body),
            )
            connection.execute(
                "INSERT INTO profiles(target, body, revision) VALUES (?, ?, ?) "
                "ON CONFLICT(target) DO UPDATE SET body=excluded.body, revision=excluded.revision",
                (target.value, body, revision),
            )
        return revision

    def get_profile(self, target: Target) -> ValidationProfile:
        """Load a configured validation profile for a target."""
        with self.connect() as connection:
            row = connection.execute(
                "SELECT body FROM profiles WHERE target = ?", (target.value,)
            ).fetchone()
        if row is None:
            raise ArtifactError(f"validation profile for {target.value} is not configured")
        return ValidationProfile.model_validate_json(row["body"])

    def put(self, content: bytes, media_type: str) -> ArtifactRef:
        """Persist immutable bytes by SHA-256 digest."""
        import hashlib

        digest = hashlib.sha256(content).hexdigest()
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO artifacts(digest, media_type, content) VALUES (?, ?, ?)",
                (digest, media_type, content),
            )
        return ArtifactRef(digest=digest, byte_length=len(content), media_type=media_type)

    def get(self, reference: ArtifactRef, max_bytes: int) -> bytes:
        """Load bounded content after validating its pointer and digest."""
        import hashlib

        if reference.byte_length > max_bytes:
            raise ArtifactError("artifact exceeds its hydration limit")
        with self.connect() as connection:
            row = connection.execute(
                "SELECT media_type, content FROM artifacts WHERE digest = ? AND media_type = ?",
                (reference.digest, reference.media_type),
            ).fetchone()
        if row is None:
            raise ArtifactError("artifact does not exist")
        content = bytes(row["content"])
        if (
            len(content) != reference.byte_length
            or row["media_type"] != reference.media_type
            or hashlib.sha256(content).hexdigest() != reference.digest
        ):
            raise ArtifactError("artifact integrity check failed")
        return content

    def put_model(self, model: StrictModel) -> ArtifactRef:
        """Store a validated model as JSON."""
        return self.put(model.model_dump_json().encode("utf-8"), "application/json")

    def get_text(self, reference: ArtifactRef, max_bytes: int) -> str:
        """Return verified UTF-8 text."""
        try:
            return self.get(reference, max_bytes).decode("utf-8")
        except UnicodeDecodeError as error:
            raise ArtifactError("artifact is not UTF-8") from error

    def get_model(self, reference: ArtifactRef, model_type: type[ModelT], max_bytes: int) -> ModelT:
        """Load a verified strict JSON model."""
        try:
            return model_type.model_validate_json(self.get(reference, max_bytes))
        except ValidationError as error:
            raise ArtifactError("artifact has an invalid model contract") from error

    def insert_run(
        self, run_id: str, workspace: Path, model: str, request: StrictModel, head: str, tree: str
    ) -> None:
        """Record the start of an immutable run identity."""
        try:
            with self.connect() as connection:
                connection.execute(
                    "INSERT INTO runs(run_id, workspace, model, request, head, start_tree, phase) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'pending')",
                    (run_id, str(workspace), model, request.model_dump_json(), head, tree),
                )
        except sqlite3.IntegrityError as error:
            raise ArtifactError("workspace already has an unfinished engine run") from error

    def run(self, run_id: str) -> dict[str, object]:
        """Return a run row, rejecting unknown identifiers."""
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise ArtifactError(f"run {run_id!r} does not exist")
        return dict(row)

    def update_run(self, run_id: str, **values: str | None) -> None:
        """Persist a whitelisted run state update."""
        allowed = {"phase", "outcome", "state", "prompt", "submitted", "scope_report"}
        if not values or not set(values) <= allowed:
            raise ValueError("unsupported run update")
        assignments = ", ".join(f"{key} = ?" for key in values)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE runs SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE run_id = ?",
                (*values.values(), run_id),
            )

    def save_snapshots(self, run_id: str, originals: list[dict[str, object]]) -> None:
        """Retain each pre-write snapshot in the same project database."""
        with self.connect() as connection:
            connection.executemany(
                "INSERT OR IGNORE INTO snapshots(run_id, path, original) VALUES (?, ?, ?)",
                ((run_id, str(item["path"]), json.dumps(item)) for item in originals),
            )
