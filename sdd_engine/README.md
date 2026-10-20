# Spec-Tech SDD engine

The engine runs the implementation phase of an SDD task. A planner chooses the implementer model and dispatches an agent on that model. The agent calls the engine over MCP. The engine makes no model calls and needs no model credentials.

## Workflow

1. An administrator configures a validation profile for the target with `configure_profile`. A profile contains a pinned Docker image and fixed commands, including tests.
2. The implementer calls `begin_task(workspace, spec, tier, target, target_files, model, context)`. The engine records the model and a Git tree of the worktree, hydrates the spec and project skills, then returns a prompt from a LangGraph interrupt.
3. The implementer sends a `GenerationOutput` object to `submit(workspace, run_id, files)`. It contains `files` (whole file contents), `documentation_metadata` (with `# Arguments` and `# Errors`, `Args:` and `Raises:`, or `@param` and `@throws`/`@returns` sections), and a nonempty `error_handling_mapping`. The engine writes approved paths and runs the configured checks in isolated Docker containers. A contract or check failure returns a new prompt for a bounded repair attempt. A terminal result returns the graph state.
4. The implementer calls `finish_task(workspace, run_id)`. The engine compares Git trees made with private temporary indexes and stores the scope report. On a failed run it restores all paths changed since the starting tree, unless HEAD moved. The review agent reads `get_run_report` and judges undeclared or flagged changes against the task spec.

The caller creates and merges worktrees. Use a dedicated worktree for a task; validation executes code from that worktree. An implementer may submit only paths in `target_files`, and paths under `.git/` are refused. The scope report labels changed paths `declared` or `undeclared` and flags test deletion, test edits outside the plan, new skip or suppression markers, and validation configuration edits. Flags request review; they do not automatically fail the run.

## Storage and configuration

All run state, artifacts, original-file snapshots, validation profiles and their change history, and official LangGraph SQLite checkpoints are stored at `<git-common-dir>/spec-tech/engine.db`. Worktrees of one repository share this database. Configuration tools run through the separate administrator MCP server, so the implementer MCP server cannot change profiles. A run records the planned model name; the engine does not select it.

Start the implementer server with `python -m sdd_engine.mcp_server` and the administrator server with `python -m sdd_engine.mcp_server --admin`. Both use MCP stdio. The CLI accepts the same operations as JSON through standard input or `--input FILE`, for example:

```sh
python -m sdd_engine.cli configure_profile --input profile.json
python -m sdd_engine.cli begin_task --input task.json
```

Configure a profile with the `ValidationProfile` schema: `image`, `commands` (each with `name` and `argv`), and optional resource limits. `standard_commands()` provides check vectors for supported targets. Docker uses `--network=none`, `--pull=never`, a read-only container root, dropped capabilities, process and resource limits, and bounded execution. Dependencies must already be available in the configured image or worktree. Rootless Docker is preferred.

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
