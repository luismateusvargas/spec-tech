# spec-tech — SDD Environment Package

Portable Spec-Driven Development environment for Claude Code CLI.  
Deploy anywhere. One folder. AI Agents read this file to install.

---

## What This Is

A complete SDD (Spec-Driven Development) workflow system built on Claude Code CLI.  
**Specs before code. Tasks from specs. Guardian-gated implementation.**

| Component | Count | Purpose |
|-----------|-------|---------|
| Slash commands | 6 | `/sdd-spec-start`, `/sdd-spec-update`, `/sdd-spec-check`, `/sdd-spec-test`, `/sdd-git`, `/sdd-version` |
| Skills | 1 | `/sdd-implement` — full implementation pipeline |
| Agents | 3 | maestro (planner), guardian (spec-compliance verifier), scribe (documentation sync) |
| Global hooks | 17 | Prompt enforcement, security blocks, handoff, cavemem |
| Project hooks | 2 | File guard, project-level handoff |
| Templates | 2 | Spec file template, security constitution baseline |
| Reference docs | 2 | Versioning best practices, git workflow reference |
| MCP servers | 2 | cavemem (memory), graphify/madar (codebase knowledge graph) |
| CLAUDE.md | 2 | Global mandatory rules, project reference pattern |

---

## Directory Structure

```
spec-tech/
├── README.md                          # ← YOU ARE HERE
├── commands/                          # Slash commands → ~/.claude/commands/
│   ├── sdd-spec-start.md              #   Bootstrap specs for new project
│   ├── sdd-spec-update.md             #   Update specs + reconcile tasks
│   ├── sdd-spec-check.md              #   Brownfield audit (code→specs)
│   ├── sdd-spec-test.md               #   Adversarial test generation
│   ├── sdd-git.md                     #   Git branch/PR workflow
│   └── sdd-version.md                 #   Versioning control + tag management
├── skills/                            # Skills → ~/.claude/skills/
│   └── sdd-implement/
│       └── SKILL.md                   #   Implementation pipeline
├── agents/                            # Agent defs → ~/.claude/agents/
│   ├── maestro.md                     #   Task decomposition planner
│   ├── guardian.md                    #   Spec-compliance verifier
│   └── scribe.md                      #   Documentation sync agent
├── docs/                              # Reference documentation
│   ├── versioning-best-practices.md   #   Semver research + guidelines
│   └── git-workflow-reference.md      #   Merge vs rebase, branch strategies
├── hooks/                             # Global hooks → ~/.claude/hooks/
│   ├── block-attribution-commit.cjs   #   Block Co-Authored-By commits
│   ├── block-security-violations.cjs  #   Block writes to .env/secrets
│   ├── capture-cardinal-rules.cjs     #   Extract cardinal rules
│   ├── cardinal-rules.json            #   Cardinal rules state
│   ├── catch-command-errors.cjs       #   Detect command failures
│   ├── caveman-autocompress.js        #   Auto-compress context
│   ├── clarify-ambiguity.cjs          #   Detect ambiguous prompts
│   ├── command-corrections.json       #   Command correction state
│   ├── enforce-prompt-structure.cjs   #   Validate prompt format
│   ├── enforce-read-pagination.cjs    #   Block unpaginated reads
│   ├── handoff-precompact.sh          #   Emergency handoff save
│   ├── inject-handoff.cjs             #   HANDOFF protocol injection
│   ├── inject-known-corrections.cjs   #   Fix known command errors
│   ├── inject-sdd-guard.cjs           #   SDD guard injection
│   ├── redirect-bash-to-tools.cjs     #   Redirect bash to dedicated tools
│   ├── remind-spec-drift.cjs          #   Warn on spec-code drift
│   ├── stop-handoff.cjs               #   HANDOFF final save on stop
│   ├── project-pre-tool-guard.cjs     #   Project-level file guard
│   └── project-handoff-precompact.sh  #   Project-level handoff save
├── templates/                         # Spec templates → ~/.claude/commands/sdd-templates/
│   ├── security.constitution.base.yaml  # Global security baseline
│   └── spec.template.yaml             # Domain spec file template
├── settings/                          # Reference (read, don't copy blindly)
│   ├── global-settings.json           #   Global ~/.claude/settings.json
│   └── project-settings.json          #   Project .claude/settings.json
├── claude-md/                         # Reference patterns
│   ├── global-CLAUDE.md               #   Global ~/.claude/CLAUDE.md
│   └── project-CLAUDE.md              #   Project CLAUDE.md pattern
└── mcp/                               # (reserved for MCP reference)
```

---

## Prerequisites

| Requirement | Version | Check |
|-------------|---------|-------|
| Claude Code CLI | Latest | `claude --version` |
| Node.js | 20+ | `node --version` |
| Python | 3.11+ | `python --version` (for graphify/madar) |
| Git Bash | Any | Required on Windows for `$HOME` hook resolution |
| GitHub CLI | Latest | `gh --version` (for `/sdd-git pr` and PR workflow) |
| cavemem | Latest | `npm list -g cavemem` |
| graphify-mcp-server | Latest | `pipx list \| grep graphify` |

---

## Installation — Step by Step

### For AI Agents Reading This

Your job: deploy this environment into a user's Claude Code installation.  
Follow each step. Verify each step. Do NOT skip verifications.

---

### Step 1: Determine OS and Paths

```
OS: Windows → HOME = %USERPROFILE% (e.g., C:\Users\username)
OS: Linux   → HOME = /home/username
OS: macOS   → HOME = /Users/username
```

Claude Code config lives at `$HOME/.claude/`. All paths below use `$HOME` for portability.
**`$HOME` is critical.** Hardcoding paths like `C:\Users\username` breaks on other machines.  
Settings and hooks MUST use `$HOME` or the CLI's built-in variable expansion.

---

### Step 2: Install Prerequisites

#### Node.js (for cavemem + hooks)
```bash
# Verify
node --version  # must be 20+

# Install cavemem globally
npm install -g cavemem
```

#### Python + graphify-mcp-server (for madar knowledge graph)
```bash
# Verify Python
python --version  # must be 3.11+

# Install graphify
pipx install graphify-mcp-server
# or: pip install graphify-mcp-server
```

#### Git Bash (Windows only)
Required on Windows because hooks use `bash -c` for `$HOME` resolution.
```powershell
# Already installed with Git for Windows
# Verify: where.exe bash
```

---

### Step 3: Deploy Slash Commands

Copy all `.md` files from `commands/` to `$HOME/.claude/commands/`:

```
FROM: spec-tech/commands/sdd-*.md
TO:   $HOME/.claude/commands/sdd-*.md
```

These become available as `/sdd-spec-start`, `/sdd-spec-update`, `/sdd-spec-check`, `/sdd-spec-test`.

Verify:
```bash
ls $HOME/.claude/commands/sdd-*
```

---

### Step 4: Deploy Skills

Copy the `sdd-implement` skill:

```
FROM: spec-tech/skills/sdd-implement/
TO:   $HOME/.claude/skills/sdd-implement/
```

Verify:
```bash
cat $HOME/.claude/skills/sdd-implement/SKILL.md | head -5
```

---

### Step 5: Deploy Agent Definitions

```
FROM: spec-tech/agents/maestro.md
TO:   $HOME/.claude/agents/maestro.md

FROM: spec-tech/agents/guardian.md
TO:   $HOME/.claude/agents/guardian.md
```

These are referenced by `sdd-implement` via `Agent(maestro, ...)` and `Agent(guardian, ...)`.
The agent name is derived from the filename (maestro.md → agent type "maestro").

Verify:
```bash
ls $HOME/.claude/agents/
```

---

### Step 6: Deploy Templates

```
FROM: spec-tech/templates/security.constitution.base.yaml
TO:   $HOME/.claude/commands/sdd-templates/security.constitution.base.yaml

FROM: spec-tech/templates/spec.template.yaml
TO:   $HOME/.claude/commands/sdd-templates/spec.template.yaml
```

The security constitution is the GLOBAL baseline. All projects extend it.  
The spec template is used by `sdd-spec-start` to generate new spec files.

Verify:
```bash
ls $HOME/.claude/commands/sdd-templates/
```

---

### Step 7: Deploy Global Hooks

Copy ALL files from `spec-tech/hooks/` to `$HOME/.claude/hooks/`:

```
FROM: spec-tech/hooks/*.cjs, *.js, *.sh, *.json
TO:   $HOME/.claude/hooks/
```

**Exclude** `project-pre-tool-guard.cjs` and `project-handoff-precompact.sh` — those go in project `.claude/hooks/`, not global.

Hooks are JavaScript/Node.js files executed by Claude Code at lifecycle points:
- `UserPromptSubmit` — fires before every prompt is processed
- `PreToolUse` — fires before tool execution (can block)
- `PostToolUse` — fires after tool execution (cavemem capture)
- `PreCompact` — fires before context compaction
- `SessionStart` / `SessionEnd` / `Stop` — lifecycle events

Verify:
```bash
ls $HOME/.claude/hooks/
```

---

### Step 8: Configure settings.json

This is the most critical step. The `settings.json` wires hooks to lifecycle events.

#### 8.1 Global settings (`$HOME/.claude/settings.json`)

Use `spec-tech/settings/global-settings.json` as reference. Key sections:

**Hooks section** — registers every hook at its lifecycle point. Uses `$HOME` in paths:
```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node \"$HOME/.claude/hooks/inject-handoff.cjs\""
          }
        ]
      }
    ]
  }
}
```

**Why `$HOME`:** Claude Code CLI resolves `$HOME` at runtime to the OS-appropriate home directory.  
On Windows, `bash -c` is used as wrapper because `$HOME` in bare `"command"` strings is resolved by bash, not by cmd.exe.  
On Linux/macOS, `$HOME` works natively. The `bash -c "node '$HOME/...'"` pattern works everywhere.

**MCP servers section** — configures cavemem and graphify/madar:
```json
{
  "mcpServers": {
    "cavemem": {
      "command": "node",
      "args": [
        "path/to/caveman-shrink/index.js",
        "node",
        "path/to/cavemem/dist/index.js",
        "mcp"
      ]
    },
    "graphify": {
      "command": "node",
      "args": [
        "path/to/caveman-shrink/index.js",
        "path/to/graphify-mcp-server"
      ]
    }
  }
}
```

**IMPORTANT:** The `caveman-shrink` wrapper paths depend on the caveman plugin installation.  
Check actual paths with:
```bash
# Find caveman-shrink
find $HOME/.claude/plugins -name "index.js" -path "*/caveman-shrink/*" 2>/dev/null

# Find cavemem
which cavemem || npm list -g cavemem

# Find graphify
which graphify-mcp-server || pipx list | grep graphify
```

**caveman-shrink** is a Node.js wrapper that spawns MCP servers via `node` with stdin/stdout transport.  
It comes from the caveman Claude Code plugin marketplace. If not installed:
```bash
# In Claude Code: /plugin install caveman
```

#### 8.2 Project settings (`<project>/.claude/settings.json`)

Use `spec-tech/settings/project-settings.json` as reference. Project settings ADD to global settings:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "name": "madar",
        "hooks": [
          {
            "type": "command",
            "command": "node .claude/madar-user-prompt-submit.cjs"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "name": "file-guard",
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "node .claude/hooks/pre-tool-guard.cjs"
          }
        ]
      }
    ]
  }
}
```

Project hooks use **relative paths** (`.claude/hooks/...`) — resolved from project root.  
Global hooks use **absolute paths** (`$HOME/.claude/hooks/...`).

---

### Step 9: Deploy CLAUDE.md Files

#### 9.1 Global CLAUDE.md (`$HOME/.claude/CLAUDE.md`)

The global CLAUDE.md applies to ALL projects. Contains:
- **Caveman Memory System** — mandatory cavemem usage
- **Cavecrew delegation** — use subagents for complex work
- **HANDOFF protocol** — session continuity
- **No guessing** — verify before acting
- **Scope discipline** — stay in project boundaries

```
FROM: spec-tech/claude-md/global-CLAUDE.md
TO:   $HOME/.claude/CLAUDE.md
```

#### 9.2 Project CLAUDE.md (`<project>/CLAUDE.md`)

Each project gets its own CLAUDE.md with:
- Project reference (language, framework, stack)
- MCP tool usage instructions
- cavemem + madar integration
- HANDOFF protocol (project-level)
- No-guessing enforcement
- Project-specific rules (e.g., "SQLAlchemy ORM only")

Use `spec-tech/claude-md/project-CLAUDE.md` as a pattern. Adapt to each project's stack.

Key pattern — use MCP tools FIRST, filesystem tools second:
```markdown
## MCP Tool Usage
For codebase questions: use `mcp__graphify-madar__*` tools FIRST.
For memory: use `mcp__cavemem__*` tools.
Do NOT use Glob/Grep/Bash/Read before MCP tools.
```

---

### Step 10: Project-Level Hook Files

Each project needs these files in its `.claude/` directory:

```
<project>/.claude/
├── settings.json           # Project hooks config
├── hooks/
│   ├── pre-tool-guard.cjs  # Blocks writes to .env, secrets, non-existent files
│   └── handoff-precompact.sh  # Emergency handoff before compaction
└── madar-user-prompt-submit.cjs  # Madar context injection (if using madar)
```

The `pre-tool-guard.cjs` enforces:
- No writes to `.env`, `.pem`, `credentials.*`, `*.key`, `*.pfx`
- No edits on files that don't exist (prevents hallucinated paths)
- Hook must be created per project (paths are project-specific)

---

## MCP Protocol Reference

### cavemem — Cross-Session Memory

**Purpose:** Persistent memory that survives context compaction and session restarts.  
**When:** Before every code change (search), after every tool use (auto-capture).

**Tools:**
| Tool | Purpose |
|------|---------|
| `mcp__cavemem__search` | Search memory by query. Use BEFORE any code change. |
| `mcp__cavemem__get_observations` | Retrieve full observation bodies by ID. |
| `mcp__cavemem__list_sessions` | Recent sessions in reverse chronological order. |
| `mcp__cavemem__timeline` | Chronological observation IDs for a session. |

**Architecture:**
- PostToolUse hook auto-captures observations after Edit/Write/Bash
- Observations stored as timestamped entries with session grouping
- Search returns scored snippets; `get_observations` returns full text
- SessionStart/Stop/End hooks manage session lifecycle

**Pattern:**
```
1. mcp__cavemem__search("auth middleware token validation") → find existing knowledge
2. mcp__cavemem__get_observations([id1, id2]) → get full context
3. [make code change]
4. PostToolUse hook auto-captures the change
```

### graphify / madar — Codebase Knowledge Graph

**Purpose:** Structural codebase understanding — what calls what, blast radius, community detection.  
**When:** Before reading files for codebase questions. Use INSTEAD of Grep/Glob for understanding.

**Tools:**
| Tool | Purpose |
|------|---------|
| `mcp__madar__retrieve` | Natural-language codebase search |
| `mcp__madar__impact` | Blast radius — what breaks if I change X |
| `mcp__madar__graph_summary` | Compact repo overview |
| `mcp__madar__community_overview` | Module communities and top nodes |
| `mcp__madar__call_chain` | Call/import paths between two nodes |
| `mcp__madar__pr_impact` | Current git diff blast radius |

**Architecture:**
- Analyzes codebase into a graph of nodes (functions, classes, files) and edges (calls, imports)
- Community detection groups related code into modules
- `retrieve` uses embeddings for semantic search + graph traversal
- Project hook `madar-user-prompt-submit.cjs` injects madar context into prompts

**Pattern:**
```
1. mcp__madar__graph_summary → repo overview
2. mcp__madar__retrieve("how does auth middleware validate tokens") → find relevant code
3. mcp__madar__impact("verifyToken") → what depends on this function
4. [make change with confidence]
```

### MCP Transport

Both MCP servers use **stdio transport** via the `caveman-shrink` Node.js wrapper:
```
Claude Code → spawns node → caveman-shrink/index.js → spawns MCP server → communicates via stdin/stdout JSON-RPC
```

The wrapper handles process lifecycle (spawn, restart on crash, kill on session end).

---

## Hooks Reference

### Lifecycle Hook Points

| Hook Point | Fires | Use Case |
|------------|-------|----------|
| `UserPromptSubmit` | Before prompt reaches Claude | Inject context, validate structure, HANDOFF reminder |
| `PreToolUse` | Before tool execution | Block dangerous operations, redirect to better tools |
| `PostToolUse` | After tool execution | Capture observations (cavemem), detect errors, warn on drift |
| `PreCompact` | Before context compaction | Emergency HANDOFF save |
| `SessionStart` | Session begins | Initialize cavemem session |
| `Stop` | User stops generation | Final HANDOFF save |
| `SessionEnd` | Session ends | Close cavemem session |

### Hook Matchers

Hooks can filter by tool name:
```json
{
  "matcher": "Edit|Write|MultiEdit",
  "hooks": [...]
}
```
Supported matchers: tool names separated by `|`. If no matcher, hook fires on ALL events at that point.

### Hook Execution

- Hooks are spawned as subprocesses
- `"type": "command"` runs a shell command
- Hook receives event data via stdin (JSON)
- Hook stdout is injected into the context (UserPromptSubmit) or logged
- Non-zero exit codes from PreToolUse hooks BLOCK the tool
- Timeout: ~10 seconds per hook

---

## The SDD Workflow

```
NEW PROJECT                    EXISTING PROJECT (no specs)
    │                                │
    ▼                                ▼
/sdd-spec-start               /sdd-spec-check
  "project description"         (audits codebase)
    │                                │
    ▼                                ▼
Specs LOCKED                  Specs generated (draft)
    │                                │
    └──────────┬────────────────────┘
               │
               ▼
         CODE EXISTS?
               │
         ┌─────┴─────┐
         │ YES       │ NO
         ▼           ▼
   /sdd-spec-test    Write implementation code
         │              │
         ▼              ▼
   Tests generated   /sdd-spec-test
         │
         ▼
   /sdd-implement <spec-file>
         │
         ├── Phase 1:   Maestro extracts tasks
         ├── Phase 1.5: /sdd-git branch (local only, no push)
         ├── Phase 2:   Cavecrew workers implement tasks
         ├── Phase 3:   Guardian verifies spec compliance (PASS/REJECT)
         ├── Phase 4:   Tests run (code wrong, not tests)
         ├── Phase 5:   User review → approves
         ├── Phase 6:   /sdd-spec-update (reconcile specs)
         ├── Phase 7:   Scribe agent (sync docs with updated specs)
         ├── Phase 8:   /sdd-version (coordinated bumps + changelog + tag)
         └── Phase 9:   /sdd-git pr (push branch + create PR)
               │
               ▼
         PR MERGED → LOOP
```

---

## Why $HOME — Portability Design

### The Problem
Hardcoded paths like `C:\Users\username\.claude\hooks\foo.cjs` break on:
- Different machines (different usernames)
- Different OSes (Windows `C:\Users\...` vs Linux `/home/...` vs macOS `/Users/...`)
- Different Claude Code installations

### The Solution
Use `$HOME` in all hook commands within settings.json:

```json
{
  "command": "bash -c \"node '$HOME/.claude/hooks/inject-handoff.cjs'\""
}
```

### How It Works
1. Claude Code CLI reads settings.json
2. When spawning hook process, CLI resolves `$HOME` to the OS home directory
3. On Windows: `$HOME` = `C:\Users\username` (Git Bash) or `%USERPROFILE%`
4. On Linux: `$HOME` = `/home/username`
5. On macOS: `$HOME` = `/Users/username`

### bash -c Wrapper (Cross-Platform)
On Windows, `$HOME` is a bash concept — cmd.exe doesn't resolve it.  
The `bash -c "..."` wrapper ensures bash resolves `$HOME` before node sees the path.  
On Linux/macOS, `bash -c` is a no-op (bash is the default shell anyway).

### cavemem Path Exception
cavemem uses full paths to `node.exe` on Windows because:
- cavemem is installed globally via npm
- Its hook runner needs to find the exact `node.exe` + `index.js` combination
- On Linux/macOS, `"command": "cavemem"` would work (PATH resolution)

For cross-platform cavemem config, use:
```json
{
  "command": "node",
  "args": [
    "path/to/caveman-shrink/index.js",
    "node",
    "path/to/cavemem/dist/index.js",
    "mcp"
  ]
}
```

---

## Project vs Global Configuration

### Global (`$HOME/.claude/`)
| File | Scope | Purpose |
|------|-------|---------|
| `CLAUDE.md` | All projects | Mandatory rules (cavemem, HANDOFF, no guessing) |
| `settings.json` | All projects | Hooks, MCP servers, permissions, theme |
| `commands/` | All projects | Slash commands available everywhere |
| `skills/` | All projects | Skills available everywhere |
| `agents/` | All projects | Agent definitions available everywhere |
| `hooks/` | All projects | Global hook implementations |

### Project (`<project>/.claude/`)
| File | Scope | Purpose |
|------|-------|---------|
| `CLAUDE.md` | One project | Project reference, stack, MCP usage, rules |
| `settings.json` | One project | Project-specific hooks (ADDITIVE to global) |
| `hooks/` | One project | Project hook implementations |
| `madar-user-prompt-submit.cjs` | One project | Madar knowledge graph injection |

### Precedence
1. Project `CLAUDE.md` extends global `CLAUDE.md`
2. Project `settings.json` hooks ADD to global hooks (both run)
3. Project rules in CLAUDE.md refine global rules for project context

---

## Verification Checklist

After deployment, verify each component:

- [ ] **Commands:** `/sdd-spec-start`, `/sdd-spec-update`, `/sdd-spec-check`, `/sdd-spec-test`, `/sdd-git`, `/sdd-version` appear in help
- [ ] **Skills:** `/sdd-implement` appears in help
- [ ] **Agents:** `maestro`, `guardian`, and `scribe` appear in available agent types
- [ ] **Templates:** `~/.claude/commands/sdd-templates/` has both YAML files
- [ ] **cavemem:** `mcp__cavemem__search` returns results
- [ ] **madar:** `mcp__madar__graph_summary` returns repo overview (in a project with madar initialized)
- [ ] **Hooks:** No hook errors on session start (check Claude Code logs)
- [ ] **HANDOFF:** `HANDOFF.md` created/updated on session start
- [ ] **PreToolUse guard:** Attempting to write to `.env` is blocked
- [ ] **Caveman style:** Responses use caveman mode (no articles, no filler)

---

## Updating spec-tech

When SDD components change:

1. Update the files in this directory
2. Update this README if the architecture changes
3. Commit to git (user handles this manually)
4. Re-deploy using this README's instructions

### What to update when:

| Change | Files to update |
|--------|----------------|
| New slash command | `commands/` + README component table |
| Modified command behavior | `commands/<file>.md` |
| New hook | `hooks/` + `settings/global-settings.json` + README hook reference |
| New MCP server | `mcp/` + settings reference + README MCP section |
| New agent type | `agents/` + README component table |
| New reference doc | `docs/` + README directory structure |
| Template changes | `templates/` |

---

## Known Dependencies

| Component | Depends On | For |
|-----------|-----------|-----|
| sdd-spec-start | Templates, security constitution | Generating spec files |
| sdd-spec-update | Existing spec files | Reconciling specs with code |
| sdd-spec-check | security constitution, codebase | Auditing existing project |
| sdd-spec-test | LOCKED specs, source code | Generating adversarial tests |
| sdd-implement | maestro, guardian, scribe, sdd-git, sdd-version | Full implementation pipeline |
| sdd-git | gh CLI, spec task IDs | Branch/PR workflow |
| sdd-version | sdd-spec-update, git | Coordinated version bumps + tags |
| maestro | Spec file content | Task decomposition |
| guardian | Spec file content, worker output | PASS/REJECT verification |
| scribe | Updated specs, code, docs | Documentation sync |
| cavemem | caveman plugin, Node.js | Cross-session memory |
| madar/graphify | Python, graphify-mcp-server | Codebase knowledge graph |
| All hooks | Node.js, Git Bash (Windows) | Lifecycle enforcement |

---

## Quick Start — New Project

```bash
# 1. Deploy spec-tech (follow Steps 1-10 above)

# 2. Create project directory
mkdir my-project && cd my-project

# 3. Initialize Claude Code project
claude .

# 4. Create project CLAUDE.md from pattern
cp spec-tech/claude-md/project-CLAUDE.md ./CLAUDE.md
# Edit to match your stack

# 5. Create project .claude/
mkdir -p .claude/hooks

# 6. Create project settings.json
cp spec-tech/settings/project-settings.json .claude/settings.json

# 7. Copy project hooks
cp spec-tech/hooks/project-pre-tool-guard.cjs .claude/hooks/pre-tool-guard.cjs
cp spec-tech/hooks/project-handoff-precompact.sh .claude/hooks/handoff-precompact.sh

# 8. Initialize madar (if using)
# Run in Claude Code: madar init

# 9. Start SDD
# Run: /sdd-spec-start "<your project description>"
```

---

## Quick Start — Existing Project (Brownfield)

```bash
# 1. Deploy spec-tech (follow Steps 1-10 above)

# 2. cd into existing project
cd existing-project

# 3. Ensure CLAUDE.md exists (create from project-CLAUDE.md pattern if missing)

# 4. Add project .claude/ settings and hooks (same as Steps 5-7 above)

# 5. Initialize madar on existing codebase
# Run in Claude Code: madar init

# 6. Audit and generate specs
# Run: /sdd-spec-check
# This reverse-engineers specs from code, flags security violations,
# generates spec files with status: draft

# 7. Review generated specs, fix CRITICAL violations, lock specs

# 8. Run /sdd-spec-test to generate adversarial test suite

# 9. Run /sdd-implement <spec-file> for spec-driven development
```
