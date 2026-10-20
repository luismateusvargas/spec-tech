# Spec-Tech LangGraph engine

This package provides a Python `StateGraph` router with isolated target subgraphs for JavaScript, TypeScript, Python, Rust, Go, C++, React, Vue, Prisma, SQLAlchemy/Alembic, Diesel, MySQL, and PostgreSQL work. Generated source is treated as data and is persisted outside the graph state.

## Role in the SDD workflow

The engine runs only the implement phase. The calling agent (Codex, Claude Code, Antigravity, or Sota) plans the task spec with the user using `sdd-plan-<tier>` and passes it as `specification`. The engine writes the approved files and runs native checks, including the tests. A different agent then reviews the result with `sdd-review-<tier>`, which needs tools the engine does not have: reading callers, running ad hoc checks, writing a counter-plan, and tagging commits.

`GraphInput.tier` (`simple`, `saas`, or `game`) is required. It selects the `sdd-implement-<tier>` skill, which is loaded alongside the target's `*-dev` guides. The calling agent sets it from the project's orchestrate YAML or the plan; the engine does not read project YAML. The skills' git checkpoint and memory steps belong to the calling agent, and the generation prompt says so.

## State and boundaries

`GraphInput` validates the public request. `GraphState` contains only run metadata, approved workspace-relative target paths, content-addressed artifact references, counters, and status. Specification text, skill files, existing source, generated code, and compiler diagnostics are hydrated by the node that needs them, then kept local to that call.

LangGraph currently validates Pydantic graph state on its initial input, but does not validate every subsequent update or the final output. The engine therefore validates each node input, node-specific result, merged state update, route decision, and final graph output explicitly with strict Pydantic models.

Strict mode rejects scalar coercion such as `"10"` for an integer and any unknown field. Tuple fields and the `Target` / `RunStatus` enums also accept their JSON shapes (arrays and enum values) because API payloads, LangChain output parsers, and checkpoint round trips produce them; the items inside those containers remain strict.

Code generation has an exact `GenerationOutput` contract: `files`, a list of whole files (`path` and `content`; 1 to 128 unique approved paths), `documentation_metadata` with `# Arguments` and `# Errors` sections and no code fences, and an explicit `error_handling_mapping`. A contract failure is stored as a diagnostic pointer and routed back to generation within a bounded retry count. It cannot reach native validation.

One model call returns every file it creates or changes, so related files stay consistent; files it omits stay as they are. The prompt's `existing_files` holds the current content of every approved target file that exists: the originals on the first attempt, and the previous generation during a repair. Include test files in `target_files` when the spec calls for tests.

The two retry limits are independent. `max_generation_attempts` bounds consecutive failed generations within one round, which is either the first generation or one repair after failed checks; `generation_failures` resets after every successful generation, and `generation_attempts` counts all of them. `max_validation_attempts` bounds native check runs. The latest failed check is kept in `validation_feedback`, apart from `failure_report`, so a repair prompt carries the compiler diagnostics as `validation_feedback` and, after a contract failure during that repair, the contract error as `generation_feedback`.

## Topology

```text
START -> target router -> isolated target subgraph
                           generate -> [contract valid?]
                              invalid -> bounded refinement -> generate
                              valid -> native validation -> [checks pass?]
                                                        pass -> END
                                                        fail -> bounded repair -> generate
```

A run that ends as `failed` after writing files passes through a `rollback` node before `END`.

Every target subgraph uses the same strict boundary wrappers and different runtime-loaded skill references and native validation profile. Add a Postgres-backed LangGraph checkpointer in deployed environments for durable resumability; the engine accepts the checkpointer as an injected dependency. Use one isolated worktree per run and a shared content-addressed artifact store with retention and access controls.

## Native validation

`DockerCommandRunner` executes fixed argument vectors using `shell=False` inside a disposable container with no network, a read-only container root, dropped capabilities, no-new-privileges, PID, memory, CPU, and timeout limits. Only the configured task worktree is mounted writable. Do not use a shared developer checkout as an execution workspace.

Images must already be pulled: `--pull=never` makes a missing image fail fast with exit 125. `/tmp` is an executable tmpfs and `HOME=/tmp`, so toolchain caches such as Go's build cache are writable. Each container gets a unique `sdd-<uuid>` name, and a timed-out container is force-removed, because killing the docker client alone leaves it running. The docker CLI receives a fixed `PATH` plus the host's `DOCKER_HOST`, `DOCKER_CONTEXT`, `DOCKER_CONFIG`, `DOCKER_CERT_PATH`, `DOCKER_TLS_VERIFY`, `XDG_RUNTIME_DIR`, and `HOME`, and nothing else. Prefer rootless Docker, where container root maps to the invoking host user and worktree files stay owned by that user. Pass `DockerCommandRunner(user="uid:gid")` only for a rootful daemon; under rootless it would map to an unrelated subordinate UID.

Configure pinned toolchain images and profiles in deployment code. `standard_commands()` supplies these common checks. Each profile ends with the project's tests, so `validated` means the static checks and the test suite passed:

| Target | Native commands |
| --- | --- |
| Rust / Diesel | `cargo check`; `cargo clippy -- -D warnings`; `cargo test` |
| Python / SQLAlchemy and Alembic | `python -m ruff check .`; `python -m mypy --strict .`; `python -m pytest -q` |
| TypeScript / React / Vue | `node_modules/.bin/tsc --noEmit`; `prisma validate` when a conventional Prisma schema is present; `npm test` |
| JavaScript / React / Vue | `node_modules/.bin/eslint . --max-warnings=0`; `npm test` |
| Go | `go vet ./...`; `go test ./...` |
| C++ / CV / AAA | `cmake --build build --parallel`; `ctest --test-dir build --output-on-failure --no-tests=error` |

A missing test suite fails the run for pytest (exit 5), `npm test` (no `test` script, or the failing placeholder `npm init` writes), and ctest (`--no-tests=error`). `cargo test` and `go test` pass an empty suite, so for Rust and Go the task spec must require tests and the reviewer must check for them. `npm test` runs whatever runner the project's `package.json` configures.

Building and testing executes code from the workspace: test files, `build.rs`, ESLint configuration, and anything in `node_modules/.bin`. The Docker sandbox is the security boundary for that code, so never run validation outside `DockerCommandRunner` or loosen its isolation.

Database migration checks for MySQL and PostgreSQL must be supplied as explicit profiles against disposable databases. SQLAlchemy/Alembic migration execution also requires a configured disposable database. Do not give a validator container production database credentials. Cache trusted dependencies and toolchains in the pinned images because the default validator network is disabled.

The specialist subgraph's validation node calls `NativeValidator.validate()`. Each command result is captured as a `CommandResult`; a nonzero exit or timeout makes the report fail, stores bounded diagnostics as an artifact, and routes the next graph step back to generation. For example, an injected runner can exercise that route without starting Docker:

```python
from pathlib import Path

from sdd_engine.models import CommandResult, Target
from sdd_engine.validation import (
    CommandSpec,
    NativeValidator,
    ValidationProfile,
    standard_commands,
)


class MockCommandRunner:
    def run(
        self, command: CommandSpec, workspace: Path, profile: ValidationProfile
    ) -> CommandResult:
        # Return exit_code=1 to exercise the repair route.
        return CommandResult(
            command_name=command.name,
            exit_code=0,
            stdout="mock check passed",
        )


workspace = Path("/isolated/task-worktree")
profile = ValidationProfile(
    image="python:3.12-slim",
    commands=standard_commands(Target.PYTHON, workspace),
)
validator = NativeValidator({Target.PYTHON: profile}, MockCommandRunner())
report = validator.validate(Target.PYTHON, workspace)
assert report.passed
```

Use `DockerCommandRunner` in the engine dependencies for real checks. A Python profile invokes Ruff and strict mypy; a Rust profile invokes `cargo check` and Clippy with warnings denied. The conditional edge reads the validated status after the report is stored, so failed checks send their diagnostics back to the generation prompt rather than marking the run validated.

A runner raises `ValidationInfrastructureError` when checks cannot run at all: Docker is missing, `docker run` exits with 125, 126, or 127, or the target has no profile. That ends the run as `failed` without spending a repair attempt, because changing the generated code cannot fix the toolchain.

## Failure handling

Every expected failure ends in a stored `FailureReport` referenced by `failure_report`, never an exception from `invoke`:

| Category | Cause | Outcome |
| --- | --- | --- |
| `hydration` | Specification, context, skill, or prior feedback is missing or over its limit | `failed`; inputs do not change between attempts |
| `generation_contract` | Output breaks `GenerationOutput` or names an unapproved file | Retried within `max_generation_attempts` |
| `generation_error` | The model or provider raised `GenerationError` | Retried within `max_generation_attempts` |
| `workspace_write` | The generated file could not be written | `failed` |
| `artifact_contract` | The stored generation or workspace is unavailable or outside approved paths | `failed` |
| `validation_infrastructure` | Native checks could not run | `failed` |
| `native_validation` | A check failed or timed out | Repaired within `max_validation_attempts` |
| `workspace_busy` | Another run holds the workspace lock | `failed` before the graph runs |
| `workspace_lock` | The workspace is not configured or its lock file cannot be opened | `failed` before the graph runs |
| `rollback` | A failed run's workspace changes could not be fully restored | `failed`; diagnostics name the original failure report |

## Workspaces, rollback, and concurrency

The calling agent (Codex, Claude Code, Antigravity, or Sota) owns worktree isolation: it creates a worktree for each task, runs the engine on it, and merges the result. The engine never creates worktrees or merges branches. It guarantees two things about the worktree it is given:

- **One run at a time.** `SddEngine.invoke` holds an exclusive `flock` on the workspace root for the whole run. Lock files live outside every worktree, in `WorkspaceRegistry(lock_directory=...)` (default: a per-user directory under the system temporary directory). Identifiers that map to the same root share a lock. A second run fails at once as `workspace_busy`; runs on different worktrees proceed in parallel. The kernel releases the lock if the process dies. The lock does not stop the agent itself from editing the worktree during a run.
- **Failed runs leave no changes.** Before the run first writes a file, the engine stores its original content and mode in the artifact store, or records that it did not exist, as an `OriginalFile` in `original_files`. When the run ends as `failed`, a `rollback` node restores those files, deletes files it created, and removes directories it created once they are empty again; `workspace_restored` is then true. A validated run keeps its changes, and `original_files` stays available to undo them later. Files larger than 16 MB are not overwritten.

Writes keep an existing file's mode; new files get `0644`.

`StructuredCodeGenerator` translates provider exceptions into `GenerationError`; a custom `CodeGenerator` must do the same. Unexpected programming errors still propagate.

## Tests

```sh
uv run pytest
uv run ruff check sdd_engine tests
uv run mypy sdd_engine tests
```

The suite drives the compiled graph through the production `StructuredCodeGenerator` with a scripted tool-calling chat model and a scripted command runner, so it needs neither a model provider nor Docker.

Tests marked `docker` run real containers and skip themselves when the daemon or a pinned image (`busybox:1.37`, `golang:1.26-alpine`) is unavailable. Run only those with `uv run pytest -m docker`, or exclude them with `-m "not docker"`.

## Wiring an application

The embedding service supplies four application-specific dependencies: a `FileArtifactStore` or external `ArtifactStore`, a `WorkspaceRegistry` mapping opaque IDs to the worktrees the calling agent created, a `PromptHydrator` rooted at the project containing `skills/`, and a configured `StructuredCodeGenerator` / `NativeValidator`. Select pinned images and commands in `ValidationProfile` objects; never accept commands or image names from graph state or LLM output. For durable execution, pass a persistent LangGraph checkpointer to `build_engine`, constructed with `serde=checkpoint_serializer()`. That serializer allows only LangGraph's safe types and the engine's `CHECKPOINT_TYPES`. `build_graph` also adds those types to a checkpointer whose serializer already has an explicit or strict-mode (`LANGGRAPH_STRICT_MSGPACK=true`) allowlist. With LangGraph's default permissive serializer, every checkpoint read logs a warning that these types will be blocked in a future version.

The public model can be constructed from an API payload after storing the specification and selected context files:

```python
request = GraphInput(
    run_id="run-2026-001",
    workspace_id="task-worktree-001",
    target=Target.RUST,
    tier=Tier.SAAS,
    specification=specification_ref,
    target_files=("src/lib.rs", "tests/repository.rs"),
    target_entities=("crate::storage::Repository",),
)
final_state = engine.invoke(request)
```

Do not place document contents, entire repositories, model prompts, credentials, or raw compiler output in `GraphState`. Store those as bounded artifacts and pass only their references.
