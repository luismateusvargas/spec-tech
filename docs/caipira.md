# Caipira: shared project memory

[Caipira](https://github.com/luismateusvargas/caipira) is a separate, local-first MCP service used by Codex, Claude Code, and Antigravity. It stores observations and evidence-backed facts per workspace so an agent can pick up decisions made in another client. It is required for the cross-agent memory workflow in this package; the SDD templates and coding guides remain readable without it.

## Agent workflow

1. Before re-investigating prior work, search Caipira with focused terms. Use session timelines and observations only when a result needs more context.
2. Prefer settled facts for decisions. Trust an unflagged fact; if Caipira marks it `NEEDS REVIEW`, inspect the cited changed files before acting on it.
3. Record a durable decision, constraint, preference, gotcha, or work status when it becomes settled. Attach the files that support it as evidence. Update or supersede a fact when later evidence changes it.
4. Verify current code and behavior for a new edit. Memory preserves decisions and history; it does not replace reading affected code.

Use the same project root across clients so Caipira resolves them to the same workspace. Its database and runtime are local to each machine; sharing a Git repository alone does not transfer a machine's Caipira database.

## Installation dependency

Caipira is **not vendored** in spec-tech. Obtain a complete Caipira installation with its bundled Node 22 runtime and local embedding model. The checked-out source tree alone may not contain those runtime assets. Its `better-sqlite3` dependency is built for the bundled Node runtime; do not launch it with system Node 24.

From the complete Caipira directory, run its installer with the bundled Node 22 binary. On Linux, the expected command is:

```sh
CAIPIRA_ROOT=/path/to/caipira
"$CAIPIRA_ROOT/node22/node-v22.20.0-linux-x64/bin/node" "$CAIPIRA_ROOT/install.js" install
"$CAIPIRA_ROOT/node22/node-v22.20.0-linux-x64/bin/node" "$CAIPIRA_ROOT/install.js" doctor
```

On Windows, use the bundled `node22/node-v22.20.0-win-x64/node.exe` with `install.js`. Run the installer again after installing a new client; the current installer skips Codex when `~/.codex/config.toml` does not yet exist.

The installer registers the `caipira` MCP server and lifecycle hooks in these user-level locations:

| Client | MCP configuration | Hooks |
| --- | --- | --- |
| Claude Code | `~/.claude.json` | `~/.claude/settings.json` |
| Codex | `~/.codex/config.toml` | Same file |
| Antigravity | `~/.gemini/config/mcp_config.json` | `~/.gemini/config/hooks.json` |

Restart each client after installation. In each one, confirm the `caipira` MCP tools are available and perform a focused search in the same project. Run Caipira's `doctor` command to check its local dependencies and registrations. The installer edits user-level configuration and writes backups of files it changes; inspect those settings if you already have custom MCP servers or hooks.
