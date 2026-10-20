"""Per-project SQLite persistence for engine configuration and run artifacts."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from sdd_engine.artifacts import BaseArtifactStore, _verify_bytes
from sdd_engine.errors import ArtifactError, ArtifactIntegrityError, ProfileError, RunNotFoundError
from sdd_engine.models import (
    ArtifactRef,
    GraphInput,
    GraphState,
    RunPhase,
    RunStatus,
    Target,
)
from sdd_engine.validation import ValidationProfile

_JSON_OBJECT = TypeAdapter(dict[str, object])
_SUBMITTED_PATHS = TypeAdapter(tuple[str, ...])


@dataclass(frozen=True)
class StoredProfile:
    """A validated profile and its persisted version identity."""

    target: Target
    profile: ValidationProfile
    revision: int
    digest: str


@dataclass(frozen=True)
class RunRecord:
    """One typed run row from the shared project database."""

    run_id: str
    workspace: Path
    model: str
    request: GraphInput
    head: str
    start_tree: str
    phase: RunPhase
    profile_revision: int
    profile_digest: str
    spec_path: str | None
    spec_blob: str | None
    outcome: RunStatus | None
    state: GraphState | None
    prompt: dict[str, object] | None
    submitted: tuple[str, ...]
    scope_report: dict[str, object] | None


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


class ProjectStore(BaseArtifactStore):
    """Keep one project's profiles, runs, checkpoints, snapshots, and artifacts together."""

    def __init__(self, database: Path) -> None:
        """Open or migrate a project database at the given path."""
        self.database = database
        self.database.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self.connect() as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version > 3:
                raise ArtifactError(f"unsupported engine database schema version {version}")
            if version == 3:
                return
            if version == 0:
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
                    profile_revision INTEGER NOT NULL DEFAULT 1 CHECK(profile_revision > 0),
                    profile_digest TEXT NOT NULL DEFAULT '',
                    spec_path TEXT,
                    spec_blob TEXT,
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
            else:
                columns = {
                    str(row["name"])
                    for row in connection.execute("PRAGMA table_info(runs)").fetchall()
                }
                additions = {
                    "profile_revision": (
                        "ALTER TABLE runs ADD COLUMN profile_revision INTEGER NOT NULL DEFAULT 1"
                    ),
                    "profile_digest": (
                        "ALTER TABLE runs ADD COLUMN profile_digest TEXT NOT NULL DEFAULT ''"
                    ),
                    "spec_path": "ALTER TABLE runs ADD COLUMN spec_path TEXT",
                    "spec_blob": "ALTER TABLE runs ADD COLUMN spec_blob TEXT",
                }
                for name, statement in additions.items():
                    if name not in columns:
                        connection.execute(statement)
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS runs_active_workspace "
                "ON runs(workspace) WHERE phase != 'finished'"
            )
            connection.execute("PRAGMA user_version=3")

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
        return self.get_profile_record(target).profile

    def get_profile_record(self, target: Target) -> StoredProfile:
        """Load a profile with its revision and SHA-256 content identity."""
        with self.connect() as connection:
            row = connection.execute(
                "SELECT body, revision FROM profiles WHERE target = ?", (target.value,)
            ).fetchone()
        if row is None:
            raise ProfileError(f"validation profile for {target.value} is not configured")
        try:
            profile = ValidationProfile.model_validate_json(row["body"])
        except ValidationError as error:
            raise ProfileError(f"validation profile for {target.value} is invalid") from error
        return StoredProfile(target, profile, int(row["revision"]), profile.digest())

    def put(self, content: bytes, media_type: str) -> ArtifactRef:
        """Persist immutable bytes by SHA-256 digest."""
        digest = hashlib.sha256(content).hexdigest()
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO artifacts(digest, media_type, content) VALUES (?, ?, ?)",
                (digest, media_type, content),
            )
        return ArtifactRef(digest=digest, byte_length=len(content), media_type=media_type)

    def get(self, reference: ArtifactRef, max_bytes: int) -> bytes:
        """Load bounded content after validating its pointer and digest."""
        if reference.byte_length > max_bytes:
            raise ArtifactError("artifact exceeds its hydration limit")
        with self.connect() as connection:
            row = connection.execute(
                "SELECT content FROM artifacts WHERE digest = ? AND media_type = ?",
                (reference.digest, reference.media_type),
            ).fetchone()
        if row is None:
            raise ArtifactError("artifact does not exist")
        content = bytes(row["content"])
        return _verify_bytes(content, reference)

    def insert_run(
        self,
        run_id: str,
        workspace: Path,
        model: str,
        request: GraphInput,
        head: str,
        tree: str,
        profile_revision: int,
        profile_digest: str,
        spec_path: str | None = None,
        spec_blob: str | None = None,
    ) -> None:
        """Record the start of an immutable run identity."""
        try:
            with self.connect() as connection:
                connection.execute(
                    "INSERT INTO runs(run_id, workspace, model, request, head, start_tree, phase, "
                    "profile_revision, profile_digest, spec_path, spec_blob) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        str(workspace),
                        model,
                        request.model_dump_json(),
                        head,
                        tree,
                        RunPhase.PENDING.value,
                        profile_revision,
                        profile_digest,
                        spec_path,
                        spec_blob,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise ArtifactError("workspace already has an unfinished engine run") from error

    def run(self, run_id: str) -> RunRecord:
        """Return a validated run record, rejecting unknown identifiers."""
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise RunNotFoundError(f"run {run_id!r} does not exist")
        try:
            return RunRecord(
                run_id=str(row["run_id"]),
                workspace=Path(str(row["workspace"])),
                model=str(row["model"]),
                request=GraphInput.model_validate_json(str(row["request"])),
                head=str(row["head"]),
                start_tree=str(row["start_tree"]),
                phase=RunPhase(row["phase"]),
                profile_revision=int(row["profile_revision"]),
                profile_digest=str(row["profile_digest"]),
                spec_path=None if row["spec_path"] is None else str(row["spec_path"]),
                spec_blob=None if row["spec_blob"] is None else str(row["spec_blob"]),
                outcome=None if row["outcome"] is None else RunStatus(row["outcome"]),
                state=(
                    None
                    if row["state"] is None
                    else GraphState.model_validate_json(str(row["state"]))
                ),
                prompt=None if row["prompt"] is None else _JSON_OBJECT.validate_json(row["prompt"]),
                submitted=_SUBMITTED_PATHS.validate_json(row["submitted"]),
                scope_report=(
                    None
                    if row["scope_report"] is None
                    else _JSON_OBJECT.validate_json(row["scope_report"])
                ),
            )
        except (ValidationError, ValueError, TypeError) as error:
            raise ArtifactIntegrityError(f"stored run {run_id!r} has an invalid record") from error

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
