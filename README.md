# spec-tech

A portable, cross-agent spec-driven development (SDD) toolkit. It contains short project instructions, coding references loaded when relevant, and a four-stage SDD workflow for simple code, SaaS, and games. Codex, Claude Code, and Google Antigravity can use the same project definitions and task specs.

**Cross-agent memory requires [Caipira](docs/caipira.md), installed separately on each machine.** Caipira keeps prior decisions and work history available across those clients; this repository contains no memory database or Caipira runtime.

## What is in this repository

| Path | Purpose |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Shared coding and memory behavior |
| [CLAUDE.md](CLAUDE.md), [GEMINI.md](GEMINI.md) | Small client entry files that refer to `AGENTS.md` |
| [docs/coding/](docs/coding/README.md) | Common guide and on-demand guides for Python, Node.js, TypeScript, Go, C#, C++, Rust, and Shell |
| `skills/sdd-{orchestrate,plan,implement,review}-{simple,saas,game}/` | Twelve active workflow skills |
| [skills/sdd-shared/templates/](skills/sdd-shared/templates/) | Questionnaires, project and domain definitions, task specs, and security baseline |
| [docs/caipira.md](docs/caipira.md) | Caipira usage, installation dependency, and client configuration |
| [docs/git-workflow-reference.md](docs/git-workflow-reference.md), [docs/versioning-best-practices.md](docs/versioning-best-practices.md) | Additional references when Git or versioning decisions arise |

The older `skills/sdd-implement/` and top-level `templates/` remain in the tree for existing users. New installations should use the twelve tiered skills and their `sdd-shared` sibling directory. The temporary `.reference-repos/` benchmark checkouts are development material, not part of the package.

## Set up a project

1. Obtain this repository and choose the target project root.
2. Install [Caipira](docs/caipira.md) on each machine that will use cross-agent memory. Install the coding clients first, then run Caipira's installer so it can register all of them.
3. Copy the three root instruction files and `docs/coding/` into the target project, keeping the same relative layout. If the project already has an `AGENTS.md`, `CLAUDE.md`, or `GEMINI.md`, merge the instructions instead of overwriting its own rules. The root files in this repository are ready to use when working on spec-tech itself.
4. Install the active skills into the project skill locations shown below. Keep `sdd-shared/` beside the twelve skill folders because their relative links use it.
5. Restart each client, check that the skills are listed, and confirm a focused Caipira search works in the target project.

For macOS/Linux, this copies the skill suite to the two project locations used by the three clients. Set the paths to your actual checkout and target project before running it:

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
  cp -R "$SPEC_TECH/skills/sdd-shared" "$destination/"
done
```

On Windows, copy the same thirteen directories with Explorer or PowerShell, preserving each directory's `SKILL.md` and the `sdd-shared/templates/` files. Install only the destination for the clients you use.

### Client configuration

| Client | Project instructions | Project skills | Caipira registration |
| --- | --- | --- | --- |
| Codex | `<project>/AGENTS.md` | `<project>/.agents/skills/` | `~/.codex/config.toml` |
| Claude Code | `<project>/CLAUDE.md` imports `AGENTS.md` | `<project>/.claude/skills/` | `~/.claude.json` and `~/.claude/settings.json` |
| Antigravity IDE / Antigravity 2.0 | `<project>/AGENTS.md` and `GEMINI.md` | `<project>/.agents/skills/` | `~/.gemini/config/mcp_config.json` and `hooks.json` |
| Antigravity CLI | `<project>/AGENTS.md` and `GEMINI.md` | `<project>/.agents/skills/` | Same Caipira configuration when supported by the installed client |

`GEMINI.md` also imports `AGENTS.md` for Gemini CLI. The project skill path for Codex and Antigravity is shared, so one copy serves both. Claude Code uses its own project skill path. For global installation instead, use the client-specific user skill directories in their current documentation; project installation keeps the package reviewable with the target repository.

Client documentation: [Codex skills](https://learn.chatgpt.com/docs/build-skills), [Claude Code skills](https://code.claude.com/docs/en/skills), [Claude Code instructions](https://code.claude.com/docs/en/memory), [Antigravity skills](https://antigravity.google/docs/skills), and [Antigravity rules](https://antigravity.google/docs/rules/).

## Use the SDD workflow

Choose one tier for the project, then use the relevant stage. A stage is a skill, not a permanent persona; agents load its instructions and templates when the work calls for them.

| Stage | Simple script or compact app | Hosted SaaS or service | Large or AAA game |
| --- | --- | --- | --- |
| Establish durable project context | `sdd-orchestrate-simple` | `sdd-orchestrate-saas` | `sdd-orchestrate-game` |
| Plan one change | `sdd-plan-simple` | `sdd-plan-saas` | `sdd-plan-game` |
| Implement a task spec | `sdd-implement-simple` | `sdd-implement-saas` | `sdd-implement-game` |
| Independently review | `sdd-review-simple` | `sdd-review-saas` | `sdd-review-game` |

For example, in a SaaS project: “Use `sdd-orchestrate-saas` to establish the project, constitution, and domain definitions,” then “Use `sdd-plan-saas` to plan billing retries,” “Use `sdd-implement-saas` for that task spec,” and “Use `sdd-review-saas` to check the implementation.” Invoke a skill by name where the client supports it, or ask the agent to use that skill explicitly.

The orchestrator asks only for unresolved durable decisions. It writes a simple Markdown project definition for small code, or YAML project, constitution, and relevant domain definitions for SaaS and games. Unknown required YAML fields remain explicit and block adoption. Planning creates **one task spec per bounded change**; implementation and review work from that spec. Caipira carries decisions and prior work between clients, so a separate session handoff file is unnecessary.

The coding guides in `docs/coding/` are defaults. Project configuration, supported versions, local conventions, and the user's instructions take priority. Agents should read only the guide for code they touch. The security baseline is a reference to adapt and verify against current provider and framework behavior, not a blanket rule to paste into every project.

## Maintain the package

- Edit active skills in `skills/` and their shared files in `skills/sdd-shared/templates/`; install the changed directories again in projects that use copies.
- Keep `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` short. Put language details in `docs/coding/` and workflow details in skills.
- When project decisions change, update the project definition or task spec and record the settled decision in Caipira with file evidence.
- Keep Caipira data outside Git. Do not commit local memory databases, model files, client settings, or temporary reference checkouts to this package.

## Verification

After setup, check that each installed skill folder has a `SKILL.md`, `sdd-shared/templates/` is present beside it, and the client lists the chosen skill. Confirm the root instructions load in each client. Run Caipira `doctor`, then search for the same test term from each client while working in the same project root. A search in one client should find facts recorded in another after they are committed to Caipira.

See [Caipira setup and behavior](docs/caipira.md) for the runtime dependency and per-client configuration files.
