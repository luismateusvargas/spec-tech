# spec-tech

`spec-tech` is a portable, cross-agent **Spec-Driven Development (SDD)** toolkit and **pointer-based LangGraph orchestration engine** (`sdd_engine`). It combines:

1. **Compact agent instructions and on-demand coding guides** (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `docs/coding/`) shared across coding clients.
2. **Twenty-three specialized skills** (`skills/`): twelve tiered SDD workflow skills (`orchestrate`, `plan`, `implement`, `review` across `simple`, `saas`, and `game`), shared templates (`skills/sdd-shared/`), and eleven language/framework/database engineering skills (`*-dev`).
3. **An agent-neutral SDD execution engine** ([`sdd_engine/`](sdd_engine/README.md)): a LangGraph + SQLite + MCP/CLI orchestration runtime that hydrates specs and engineering skills into bounded prompts, validates whole-file submissions against strict Pydantic contracts, executes native compiler/linter/test checks inside network-isolated Docker containers, and produces diff-based scope reports with automatic rollback on failure.
4. **Cross-agent durable memory** via **[Caipira](docs/caipira.md)** so decisions, constraints, and evidence-backed facts persist across sessions and coding clients.

---

## Repository layout

| Path | Purpose |
| --- | --- |
| [`AGENTS.md`](AGENTS.md) | Shared coding rules, verification requirements, skill-mirroring policy, and Caipira memory workflow |
| [`CLAUDE.md`](CLAUDE.md), [`GEMINI.md`](GEMINI.md) | Client entry files importing `AGENTS.md` for Claude Code, Gemini CLI, and Antigravity |
| [`docs/coding/`](docs/coding/README.md) | [Common coding guide](docs/coding/common.md) plus on-demand guides for [Python](docs/coding/python.md), [Node.js](docs/coding/nodejs.md), [TypeScript](docs/coding/typescript.md), [Go](docs/coding/go.md), [C#](docs/coding/csharp.md), [C++](docs/coding/cpp.md), [Rust](docs/coding/rust.md), and [Shell](docs/coding/shell.md) |
| [`docs/caipira.md`](docs/caipira.md) | Cross-agent memory workflow, runtime requirements, and client registration |
| [`docs/git-workflow-reference.md`](docs/git-workflow-reference.md), [`docs/versioning-best-practices.md`](docs/versioning-best-practices.md) | Reference guides for Git branching/worktrees and semantic versioning |
| `skills/sdd-{orchestrate,plan,implement,review}-{simple,saas,game}/` | Twelve active SDD workflow skills organized by stage and project tier |
| [`skills/sdd-shared/templates/`](skills/sdd-shared/templates/) | Shared questionnaires, project/constitution/domain YAML & Markdown templates, task spec templates, [engine protocol](skills/sdd-shared/templates/engine-protocol.md), [Git checkpoints](skills/sdd-shared/templates/git-checkpoints.md), [scope guide](skills/sdd-shared/templates/scope-guide.md), and [counter-plan template](skills/sdd-shared/templates/review.counter-plan.template.md) |
| `skills/*-dev/` | Eleven engineering skills injected by the SDD engine and used directly by coding agents |
| [`sdd_engine/`](sdd_engine/README.md) | Pointer-based LangGraph orchestration engine, SQLite store, Docker sandbox validator, MCP servers, and CLI |
| [`toolchains/`](toolchains/README.md) | Digest-pinned Dockerfiles (`python.Dockerfile`, `rust.Dockerfile`, `go.Dockerfile`) for offline container validation |
| [`tests/`](tests/) | Unit and real-container integration tests for contracts, artifacts, graph lifecycle, CLI, and Docker sandboxing |

---

## Skills catalog

### 1. SDD workflow skills (12 skills + `sdd-shared`)

Choose one tier for a project (`simple`, `saas`, or `game`) and run the relevant stage skill:

| Stage | Simple script, utility, or compact app | Hosted multi-user SaaS or service | Large or AAA game |Purpose |
| --- | --- | --- | --- | --- |
| **Orchestrate** | [`sdd-orchestrate-simple`](skills/sdd-orchestrate-simple/SKILL.md) | [`sdd-orchestrate-saas`](skills/sdd-orchestrate-saas/SKILL.md) | [`sdd-orchestrate-game`](skills/sdd-orchestrate-game/SKILL.md) | Bootstrap or refresh project, constitution, and domain definitions using the [orchestrator questionnaire](skills/sdd-shared/templates/orchestrator.questionnaire.md) |
| **Plan** | [`sdd-plan-simple`](skills/sdd-plan-simple/SKILL.md) | [`sdd-plan-saas`](skills/sdd-plan-saas/SKILL.md) | [`sdd-plan-game`](skills/sdd-plan-game/SKILL.md) | Split topics via the [scope guide](skills/sdd-shared/templates/scope-guide.md) into one bounded task spec per outcome with `Status: ready` and `Target files:` |
| **Implement** | [`sdd-implement-simple`](skills/sdd-implement-simple/SKILL.md) | [`sdd-implement-saas`](skills/sdd-implement-saas/SKILL.md) | [`sdd-implement-game`](skills/sdd-implement-game/SKILL.md) | Execute a ready spec with [local Git checkpoints](skills/sdd-shared/templates/git-checkpoints.md) and the [SDD engine protocol](skills/sdd-shared/templates/engine-protocol.md) |
| **Review** | [`sdd-review-simple`](skills/sdd-review-simple/SKILL.md) | [`sdd-review-saas`](skills/sdd-review-saas/SKILL.md) | [`sdd-review-game`](skills/sdd-review-game/SKILL.md) | Independently audit implementation commits and engine scope reports; emit a local `sdd/approved/*` tag or a [counter-plan](skills/sdd-shared/templates/review.counter-plan.template.md) |

### 2. Engineering (`*-dev`) skills (11 skills)

These skills provide strict rules for modularity, typing, ownership, data validation, error handling, and testing. Agents load them automatically when working in matching languages, and `sdd_engine` hydrates them into prompts based on the run's target ([`sdd_engine/targets.py`](sdd_engine/targets.py)):

| Skill | Scope | Engine targets using this skill |
| --- | --- | --- |
| [`python-dev`](skills/python-dev/SKILL.md) | Modular, strictly typed Python (`ruff`, `mypy --strict`, `pytest`, Pydantic v2, `Protocol` DI) | `python`, `sqlalchemy-alembic` |
| [`javascript-dev`](skills/javascript-dev/SKILL.md) | Browser and Node.js JavaScript (`.js`, `.mjs`, `.cjs`, `.jsx`) | `javascript`, `prisma-javascript`, `react-javascript`, `vue-javascript` |
| [`typescript-dev`](skills/typescript-dev/SKILL.md) | Strictly typed TypeScript (`.ts`, `.tsx`, `tsc --noEmit`) | `typescript`, `prisma-typescript`, `react-typescript`, `vue-typescript` |
| [`react-dev`](skills/react-dev/SKILL.md) | React component architecture, hooks, state, accessibility, and performance | `react-javascript`, `react-typescript` |
| [`vue-dev`](skills/vue-dev/SKILL.md) | Vue `.vue` single-file components, composables, and reactivity | `vue-javascript`, `vue-typescript` |
| [`rust-dev`](skills/rust-dev/SKILL.md) | Idiomatic Rust ownership, error types, `cargo check`, `clippy -D warnings`, and tests | `rust`, `diesel` |
| [`go-dev`](skills/go-dev/SKILL.md) | Go services, explicit error handling, concurrency lifetimes, `go vet`, and `go test` | `go` |
| [`cpp-dev`](skills/cpp-dev/SKILL.md) | Modern C++ modularity, RAII ownership, error boundaries, CMake, and CTest | `cpp`, `cpp-cv`, `cpp-aaa` |
| [`cpp-cv-dev`](skills/cpp-cv-dev/SKILL.md) | C++ computer vision, image/tensor layout, alignment, SIMD, and high-throughput pipelines | `cpp-cv` |
| [`cpp-aaa-dev`](skills/cpp-aaa-dev/SKILL.md) | C++ AAA game engines, deterministic simulation, ECS, cache locality, and frame budgets | `cpp-aaa` |
| [`database-dev`](skills/database-dev/SKILL.md) | SQL schemas, migrations, transactional safety, Prisma, SQLAlchemy/Alembic, and Diesel | `mysql`, `postgresql`, `prisma-javascript`, `prisma-typescript`, `sqlalchemy-alembic`, `diesel` |

---

## Pre-configured agents and client integration

`spec-tech` is designed so multiple agents can collaborate on the same repository—for example, one agent orchestrating or planning, a subagent implementing through `sdd_engine`, and another agent performing an independent review.

### Workstation shared skill directory

On this workstation, the local coding agents share `/home/htxzz77/Projects/skills/` through their global skill paths:

| Agent / Client | Project instructions | Project-local skill path | Global skill path (linked to `/home/htxzz77/Projects/skills`) | Caipira MCP & hooks config |
| --- | --- | --- | --- | --- |
| **OpenAI Codex** | `<project>/AGENTS.md` | `<project>/.agents/skills/` | `~/.agents/skills` | `~/.codex/config.toml` |
| **Claude Code** | `<project>/CLAUDE.md` (imports `AGENTS.md`) | `<project>/.claude/skills/` | `~/.claude/skills` | `~/.claude.json` & `~/.claude/settings.json` |
| **Antigravity IDE / 2.0** | `<project>/AGENTS.md` & `GEMINI.md` | `<project>/.agents/skills/` | `~/.gemini/config/skills` | `~/.gemini/config/mcp_config.json` & `hooks.json` |
| **Antigravity CLI (`agy`)** | `<project>/AGENTS.md` & `GEMINI.md` | `<project>/.agents/skills/` | `~/.gemini/antigravity-cli/skills` | `~/.gemini/config/mcp_config.json` & `hooks.json` |
| **Sota** (`~/Projects/sota`) | `<project>/AGENTS.md` | Worktree-isolated runner | Reads `/home/htxzz77/Projects/skills` | Connects via `sota_infra/src/mcp_client.rs` |

When editing any active skill or shared template under `skills/` in this repository, copy the change to `/home/htxzz77/Projects/skills/` and verify with `diff -ru` that both trees match.

### Agent roles in the SDD Engine

The SDD engine (`sdd_engine`) is **model- and agent-neutral**—it makes no LLM API calls and holds no model credentials:

- **Administrator (`spec-tech-engine-config`)**: Configures and inspects per-target container validation profiles (`configure_profile`, `get_profile`). Runs only when launched with `--admin`.
- **Planner (`sdd-plan-{simple,saas,game}`)**: Produces a bounded task spec with `Status: ready` and `Target files:`, commits the baseline checkpoint, and selects the implementer model.
- **Implementer (`spec-tech-engine` / `sdd-implement-{simple,saas,game}`)**: Calls `begin_task`, receives the hydrated `GenerationPrompt` (containing the spec, target `*-dev` skills, existing target files, and `submission_schema`), submits whole-file replacements with `submit`, repairs any contract or compiler/test failures (up to 3 attempts per round, 3 validation rounds, 9 total submissions), and finalizes with `finish_task` (or aborts with `cancel_task`).
- **Reviewer (`sdd-review-{simple,saas,game}`)**: Calls `get_run_report` to inspect `validation_report` and `scope_report` (which flags undeclared edits, test deletions/modifications, check-config changes, and added lint/type/test suppressions or skips) before tagging `sdd/approved/<task-slug>-<short-sha>` or issuing a counter-plan.

---

## Dependencies

### 1. Core workflow & memory dependencies

- **Git** (`>= 2.38` recommended): Required for worktree management, committed spec verification (`git ls-tree`, `git cat-file`), and private-index tree diffing/restoration in `sdd_engine`.
- **[Caipira](docs/caipira.md)** (external local-first MCP service):
  - Required for cross-agent memory (`search_facts`, `record_fact`, `update_fact`, `check_drift`, `timeline`).
  - Must be installed from a complete Caipira distribution that includes its **bundled Node.js 22.20.0 runtime** and local embedding model (do not run Caipira's `better-sqlite3` build under system Node 24).

### 2. SDD Engine (`spec-tech-sdd-engine`) dependencies

- **Python `>= 3.11`** and **[`uv`](https://docs.astral.sh/uv/)** (or `pip` / `venv`).
- **Runtime Python packages** (declared in [`pyproject.toml`](pyproject.toml)):
  - `langgraph >= 1.0, < 2.0`
  - `langgraph-checkpoint-sqlite >= 3.0, < 4.0`
  - `langchain-core >= 1.0, < 2.0`
  - `mcp >= 1.0, < 2.0` (FastMCP stdio server)
  - `pydantic >= 2.7, < 3.0`
  - `typing-extensions >= 4.12`
- **Development & verification packages**:
  - `pytest >= 8.3, < 10`
  - `ruff >= 0.11, < 1.0`
  - `mypy >= 1.15, < 2.0`
- **Docker** (for native validation in [`sdd_engine/validation.py`](sdd_engine/validation.py)):
  - **Rootless Docker** is strongly recommended (`DOCKER_HOST=unix://$XDG_RUNTIME_DIR/docker.sock`). Under rootless Docker, container `root` (`0:0`) maps directly to the host user UID/GID; on a rootful daemon, `DockerCommandRunner` automatically passes `--user <uid>:<gid>`.
  - Validation containers run with `--pull=never`, `--network=none`, `--read-only`, `--cap-drop=ALL`, `--security-opt=no-new-privileges`, and bounded PIDs/CPUs/memory/timeout against a disposable `.git`-free staged copy of the worktree. All toolchain images and project dependencies must therefore be present locally before a run starts.

---

## Installation and setup

### 1. Install the Python environment and SDD engine

From this repository root:

```sh
uv sync
```

Or install into a standard virtual environment:

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
```

### 2. Build the validation toolchain Docker images

Build the digest-pinned toolchain images in [`toolchains/`](toolchains/README.md) before configuring validation profiles:

```sh
docker build -f toolchains/python.Dockerfile -t spec-tech/python:3.12.12-r1 .
docker build -f toolchains/rust.Dockerfile -t spec-tech/rust:1.91.1-r1 .
docker build -f toolchains/go.Dockerfile -t spec-tech/go:1.26-r1 .
```

Configure a target profile in a project Git worktree using the administrator CLI (omitting `commands` populates the target's default checks from [`sdd_engine/targets.py`](sdd_engine/targets.py)):

```sh
uv run python -m sdd_engine.cli --admin configure_profile <<'EOF'
{
  "workspace": "/path/to/your-project",
  "target": "python",
  "profile": {
    "image": "spec-tech/python:3.12.12-r1"
  }
}
EOF
```

### 3. Register the MCP servers in your coding clients

Expose the **implementer** server (`python -m sdd_engine.mcp_server`) to coding agents. Keep the **administrator** server (`python -m sdd_engine.mcp_server --admin`) restricted to operator/admin sessions:

```json
{
  "mcpServers": {
    "spec-tech-engine": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/spec-tech",
        "run",
        "python",
        "-m",
        "sdd_engine.mcp_server"
      ]
    }
  }
}
```

### 4. Install Caipira for cross-agent memory

Install the coding clients first, then run Caipira's installer with its bundled Node 22 binary (see [`docs/caipira.md`](docs/caipira.md) for Windows and troubleshooting details):

```sh
CAIPIRA_ROOT=/path/to/caipira
"$CAIPIRA_ROOT/node22/node-v22.20.0-linux-x64/bin/node" "$CAIPIRA_ROOT/install.js" install
"$CAIPIRA_ROOT/node22/node-v22.20.0-linux-x64/bin/node" "$CAIPIRA_ROOT/install.js" doctor
```

### 5. Install instructions and skills into a target project

1. Copy `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, and `docs/coding/` into the target project root (or merge with existing instruction files).
2. If your clients do not already link to `/home/htxzz77/Projects/skills/`, copy the twelve SDD workflow skills, `sdd-shared`, and the eleven `*-dev` engineering skills into the project skill directories (`.agents/skills/` serves both Codex and Antigravity; `.claude/skills/` serves Claude Code):

```sh
SPEC_TECH=/path/to/spec-tech
TARGET=/path/to/your-project

for destination in "$TARGET/.agents/skills" "$TARGET/.claude/skills"; do
  mkdir -p "$destination"
  for phase in orchestrate plan implement review; do
    for tier in simple saas game; do
      cp -R "$SPEC_TECH/skills/sdd-$phase-$tier" "$destination/"
    done
  done
  for dev_skill in \
    python-dev javascript-dev typescript-dev react-dev vue-dev \
    rust-dev go-dev cpp-dev cpp-cv-dev cpp-aaa-dev database-dev; do
    cp -R "$SPEC_TECH/skills/$dev_skill" "$destination/"
  done
  cp -R "$SPEC_TECH/skills/sdd-shared" "$destination/"
done
```

---

## Verification and maintenance

Run the test suite, linter, formatter check, and strict type checker with `uv`:

```sh
uv run ruff check sdd_engine tests
uv run ruff format --check sdd_engine tests
uv run mypy sdd_engine tests
uv run pytest
```

When modifying any active skill or shared template under `skills/`, mirror the changes to `/home/htxzz77/Projects/skills/` and verify there is no drift:

```sh
diff -ru skills/sdd-shared /home/htxzz77/Projects/skills/sdd-shared
for d in sdd-{orchestrate,plan,implement,review}-{simple,saas,game} \
  python-dev javascript-dev typescript-dev react-dev vue-dev \
  rust-dev go-dev cpp-dev cpp-cv-dev cpp-aaa-dev database-dev; do
  diff -ru "skills/$d" "/home/htxzz77/Projects/skills/$d"
done
```

See [`sdd_engine/README.md`](sdd_engine/README.md) for engine architecture and observability details, [`skills/sdd-shared/templates/engine-protocol.md`](skills/sdd-shared/templates/engine-protocol.md) for the implementer MCP protocol, and [`docs/caipira.md`](docs/caipira.md) for cross-agent memory setup.
