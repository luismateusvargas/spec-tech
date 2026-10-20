Still open

- Low:
  - Hydration doesn't count everything toward its size limit (feedback text; existing target files now count).
  - An empty error_handling_mapping is accepted.

## Checkpoint (2026-10-20)

### Done
- Fix 1: strict-mode models accept JSON-shaped input (`JsonTuple`, `TargetValue`, `StatusValue` in `sdd_engine/models.py`); a real LLM run now validates.
- Fix 2: every expected failure ends in a stored `FailureReport` (`GenerationError`, `ValidationInfrastructureError`, split hydrate/generate/write phases in `sdd_engine/graph.py`).
- Items 3 and 4: `max_output_bytes` capped at 16,000; Docker exit codes 125/126/127, a missing `docker` binary, and a missing profile are infrastructure failures.
- Test suite in `tests/` (53 passing): `uv run pytest`, `uv run ruff check sdd_engine tests`, `uv run mypy sdd_engine tests`.
- `.gitignore` covers Python caches, `*.egg-info/`, `.venv/`.
- Nothing is committed yet.

### Environment
- Rootless Docker 29.9.1 is installed and working (`docker-rootless-extras` AUR user units, `systemctl --user enable --now docker.socket`). Seccomp, rootless, and cgroupns are listed in `docker info`; cgroup v2 with the systemd driver. A hello-world run with the full runner sandbox flags succeeded.
- `DOCKER_HOST=unix://$XDG_RUNTIME_DIR/docker.sock` is set in `~/.bashrc`. Restart agent sessions so they inherit it.
- Decision: rootless only. Never join the `docker` group or enable the rootful daemon.
- Pulled images: `busybox:1.37` (timeout test), `golang:1.26-alpine` (Go profile, item 6).

### Done: Docker batch (items 5-7)
- Item 7: the docker CLI gets a fixed `PATH` plus an allowlist of client variables (`DOCKER_CLIENT_ENVIRONMENT` in `sdd_engine/validation.py`). The optional `DockerCommandRunner(user=...)` is for rootful daemons only.
- Item 5: each container is named `sdd-<uuid>` and force-removed on timeout (best effort, 30 s bound).
- Item 6: `/tmp` is `rw,exec,nosuid,nodev` and `HOME=/tmp` is set in the container.
- `--pull=never` added.
- Also fixed: `--mount ...,rw` is rejected by Docker 29 ("invalid field 'rw'"), so every real run failed with exit 125. Bind mounts are writable by default, so the field was removed.
- Tests: 60 passing, including 4 `docker`-marked integration tests (timeout cleanup, host-user ownership, Go profile, missing image -> exit 125).

### Done: retry and state items 10, 11, 13
- Item 10: `GraphState.generation_failures` counts consecutive failed generations and resets after a successful one; `max_generation_attempts` now bounds each round (first generation or one repair). `generation_attempts` is a total count.
- Item 11: `GraphState.validation_feedback` keeps the last failed native check. `PromptHydrator.hydrate(state)` sends it as `validation_feedback` and a different, later `failure_report` as `generation_feedback`.
- Item 13: `CHECKPOINT_TYPES` and `checkpoint_serializer()` in `sdd_engine/graph.py`. `build_graph` calls `checkpointer.with_allowlist(...)`, which only takes effect on explicit or strict serializers; the default permissive one still warns, so deployments must pass `serde=checkpoint_serializer()`.
- Tests: 65 passing, also with `LANGGRAPH_STRICT_MSGPACK=true`.

### Done: items 14 and 15 (2026-10-20)
- Decision: the calling agent (Codex, Claude Code, Antigravity, Sota at `~/Projects/sota`) owns worktree isolation and merging. The engine never creates worktrees or merges.
- Item 14: `OriginalFile` snapshots (content artifact, mode, created directory) are taken before the first write of each file; a `rollback` node restores them when a run ends `failed` and sets `workspace_restored`. `WorkspaceRegistry.snapshot` / `restore`. Writes now keep the file's mode (new files `0644`; they used to be `0600` from `mkstemp`).
- Item 15: `WorkspaceRegistry.lock` (`flock`, lock files outside the worktree); `SddEngine.invoke` holds it for the run and returns `workspace_busy` / `workspace_lock` failures.
- Tests: 79 passing, also with `LANGGRAPH_STRICT_MSGPACK=true`.

### Done: items 8, 9, 12 (2026-10-20)
- Decisions (user): the engine runs only the implement phase (the agent plans, another agent reviews with `sdd-review-<tier>`); an explicit required `GraphInput.tier`; one call returns many whole files; `validated` requires tests to pass, with the Docker sandbox as the security boundary.
- Item 8: `Tier` enum; the hydrator loads `sdd-implement-<tier>` plus the `*-dev` guides; the system prompt hands git checkpoints, memory, and review back to the agent.
- Item 9: `GenerationOutput.files: tuple[WorkspaceFile]`; every file is snapshotted and written; the prompt's `existing_files` shows the current target files (the first attempt used to see none).
- Item 12: every standard profile ends with tests (pytest, `npm test`, `cargo test`, `go test`, ctest `--no-tests=error`). Known gap: `cargo test` and `go test` pass an empty suite.
- Also: shared `SafeRelativePath` / `TargetFiles` types (removes the duplicated path validator and bounds `GraphState.target_files` items); `read_text` OSErrors become `hydration` failures.
- Tests: 98 passing, also with `LANGGRAPH_STRICT_MSGPACK=true`. Not yet run in real containers: the Python, Node, Rust, and C++ profiles (no images pulled).

### Next: agent-neutral engine (designed 2026-10-20, not started)
Decisions (user):
- The engine never calls a model. The planner agent picks the implementer model during planning (for example Opus plans and dispatches a Sonnet 5.5 high-reasoning subagent). That subagent drives the engine and its checks run in the Docker sandbox built today. The planned model is recorded with the run.
- Every agent (Claude Code, Codex, Antigravity, Sota) uses one MCP entry point. Sota already has an MCP client (`sota_infra/src/mcp_client.rs`).
- One SQLite database per project holds all configuration and runtime state, at `<repo>/.git/spec-tech/engine.db` (shared by all worktrees, never committed).
- Out-of-scope changes are discovered and reported, not blocked. The review agent judges each one as necessary (spec gap) or a shortcut (finding plus a counter-plan revert).

Build order:
1. SQLite store: configuration (validation profiles) with a change-history table, runs, LangGraph checkpoints (official SQLite saver), and original-file snapshots. Configuration can change only through separate config tools or commands, never through the implementer's tools. Refuse target paths under `.git/`.
2. Graph pauses for the agent with LangGraph `interrupt()`: `begin_task` returns the hydrated prompt and `submit(files)` resumes generation. Remove the engine-side model call.
3. MCP server: `begin_task(workspace, spec, tier, target, target_files, model, context)`, `submit`, `finish_task`, `get_run_report`, plus separate configuration tools. A small CLI wraps the same functions.
4. Scope check: record a git tree of the worktree at begin and at finish, built with a temporary index so untracked and uncommitted files are included and the agent's index is untouched, then diff the two. Labels: declared, undeclared (outside `submit` or outside `target_files`), flagged (test files deleted or changed outside the plan; new skip/ignore markers; new suppressions such as noqa, type: ignore, eslint-disable; check-config edits). Store the scope report in SQLite. Broader rollback: on failure, restore every path changed since the starting tree, refusing if HEAD moved during the task.
5. Update `sdd-review-*` skills to consume the scope report; mirror the change to `/home/htxzz77/Projects/skills` per AGENTS.md.

### After that
- Pinned toolchain images (Dockerfiles with dependencies baked in for `--network=none`). Toolchain priority is still to be chosen; suggested Python, Rust, Go.
