# Spec-Tech SDD engine

The engine runs the implementation phase of an SDD task. A planner chooses the implementer model and dispatches an agent on that model. The agent calls the engine over MCP. The engine makes no model calls and needs no model credentials. Implementer agents follow the [engine protocol](../skills/sdd-shared/templates/engine-protocol.md), which the `sdd-implement-*` skills link to; it covers when to use the engine, target selection, the submission contract, and how to handle each failure.

## Workflow

1. An administrator configures a validation profile for the target with `configure_profile`. A profile contains a pinned Docker image and fixed commands, including tests.
2. The implementer calls `begin_task(workspace, tier=, target=, model=, spec_path= | spec=, target_files=, context=)`. `spec_path` binds the run to a spec committed at `HEAD` whose worktree and index copies are unchanged, and the run records that path and blob; `spec` passes the text inline instead. The spec header, the text before its first `## ` heading, must contain exactly one `Status: ready` line, so draft, blocked, and unfilled template specs are refused. A header `Target files: a.py, b.py` line supplies `target_files` when it is omitted and must name the same paths when both are given. The engine records the model and a Git tree of the worktree, hydrates the spec and project skills, then returns a prompt from a LangGraph interrupt. The prompt carries `submission_schema` (the `GenerationOutput` JSON Schema) and `submission_semantics`.
3. The implementer sends a `GenerationOutput` object to `submit(workspace, run_id, files)`. It contains `files` (whole file contents, at most 1,000,000 characters each and 3,000,000 UTF-8 bytes together), `documentation_metadata` (with `# Arguments` and `# Errors`, `Args:` and `Raises:`, or `@param` and `@throws` sections, each followed by text), and `error_handling_mapping`. The mapping may be empty only when `no_failure_paths` is `true`. The MCP server publishes this schema and rejects malformed structure; content rule violations reach the graph. The engine writes approved paths and runs the configured checks in isolated Docker containers. A contract failure, including an oversized submission, returns a bounded repair prompt without writing files. A native check failure returns a repair prompt after the submitted files have been written. A terminal result returns the graph state.
4. The implementer calls `finish_task(workspace, run_id)`. The engine compares Git trees made with private temporary indexes and stores the scope report. On a failed run it restores all paths changed since the starting tree, unless HEAD moved. To abort a pending or terminal run, call `cancel_task(workspace, run_id)`; it records a failed outcome, attempts the same restoration, and frees the worktree for a new run. The review agent reads `get_run_report` and judges undeclared or flagged changes against the task spec.

The caller creates and merges worktrees. Use a dedicated worktree for a task. Each validation pass copies the worktree, without its `.git` entry, into a disposable directory under the system temporary directory (`TMPDIR`) and mounts only that copy, so containers cannot reach Git metadata, hooks, or the engine database, and their writes never reach the worktree. The commands of one pass share the copy. A temporary directory on the worktree's filesystem lets `cp --reflink=auto` share blocks instead of copying them. An implementer may submit only paths in `target_files`, and paths under `.git/` are refused. The scope report labels changed paths `declared` or `undeclared` and flags test deletion, test edits outside the plan, new skip or suppression markers, and validation configuration edits. Test paths include `conftest.py` files; check configuration covers Python, JavaScript, TypeScript, Rust, Go, and CMake tool settings, plus a root `pytest.py`, `_pytest/`, or `pluggy/` that would replace pytest under `python -m pytest`. Suppression markers include `noqa`, `type: ignore`, `pyright: ignore`, `pylint: disable`, `eslint-disable`, `@ts-ignore`, `@ts-expect-error`, `@ts-nocheck`, Rust `allow` and `expect` attributes, `nolint`, and `NOLINT`; skip markers include pytest `skip`, `skipif`, and `xfail`, `unittest` skips, Jest and Vitest `skip`, `todo`, and `x`-prefixed tests, Rust `#[ignore]`, Go `t.Skip`, and GTest `GTEST_SKIP` and `DISABLED_` names. Flags request review; they do not automatically fail the run.

## Storage and configuration

All run state, artifacts, original-file snapshots, validation profiles and their change history, and official LangGraph SQLite checkpoints are stored at `<git-common-dir>/spec-tech/engine.db`. Worktrees of one repository share this database. Configuration tools run through the separate administrator MCP server, so the implementer MCP server cannot change profiles. A run records the planned model name; the engine does not select it.

Start the implementer server with `python -m sdd_engine.mcp_server` and the administrator server with `python -m sdd_engine.mcp_server --admin`. Both use MCP stdio. The CLI accepts the same operations as JSON through standard input or `--input FILE`. Like the MCP servers, it runs `configure_profile` and `get_profile` only with `--admin`, and the task operations only without it:

```sh
python -m sdd_engine.cli --admin configure_profile --input profile.json
python -m sdd_engine.cli begin_task --input task.json
```

Configure a profile with the `ValidationProfile` schema: `image` (an image reference, optionally pinned by digest), `commands` (each with a `name` of letters, digits, `.`, `_`, or `-` up to 128 characters, and `argv`), and optional resource limits such as `memory_limit` (`4g`). `sdd_engine/targets.py` holds the one `TARGETS` registry that gives every target its engineering skills and standard checks. `standard_commands()` returns those checks, and `configure_profile` uses them when a profile omits `commands`. Ruff and mypy run with `python -P` so workspace modules cannot shadow them. Docker uses `--network=none`, `--pull=never`, a read-only container root, dropped capabilities, process and resource limits, bounded execution, and `--` before the image. Dependencies must already be available in the configured image or worktree. Rootless Docker is preferred: container root maps to the host user there, so the runner passes `--user` with the host UID and GID only when `docker info` reports a rootful daemon or a user is configured explicitly.

## Logging

The engine logs through the standard `logging` module under the `sdd_engine` logger and configures no handlers itself. Each event carries its fields as log record attributes for a structured formatter: graph nodes log `run_id`, `node`, `attempt` (the submission count), `status`, `failure_category`, and `duration_ms` when they finish; native checks log `target`, `command_name`, `exit_code`, `timed_out`, and `duration_ms`; the service logs when a run starts, is cancelled, or finishes, with its restoration result and counts of changed and flagged paths. Events never include spec text, file contents, command output, or error messages.

## Contracts and checks

Graph state carries references and counters, while specification text, source, diagnostics, and generated files live in SQLite artifacts or only in the current call. Strict Pydantic validation runs at the input, node, and output boundaries. Invalid submissions are stored as `FailureReport` artifacts and returned to the agent for repair. Validation infrastructure failures end the run without spending a code repair attempt.

Run the project checks with:

```sh
uv run pytest
uv run ruff check sdd_engine tests
uv run ruff format --check sdd_engine tests
uv run mypy sdd_engine tests
```

Docker integration tests skip if the daemon or their images are unavailable. The unit tests use a scripted command runner and require no model provider.
