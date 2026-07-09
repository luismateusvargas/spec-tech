# PROJECT REFERENCE — <Your Project>

Describe your project stack here. Example structure for a multi-repo workspace:

| Project | Language | Role |
|---------|----------|------|
| `<backend>/` | Python 3.11, FastAPI | Backend API server |
| `<frontend>/` | Node.js 20, Express 5 | Web portal |
| `<service>/` | TypeScript | Supporting service |

**Port map:** Backend=8000, Frontend=3000, Service=8080, PG=5432

**Docs:** `docs/` — architecture, API reference, DB schema, deployment docs.
**Deployment:** Docker Compose on cloud VM, reverse proxy, container registry images.

---

## MCP Tools — madar (project-bound knowledge graph)

When you need codebase context — how something works, what breaks, where things are — USE THESE FIRST:
- `mcp__madar__retrieve` — general codebase search
- `mcp__madar__impact` — blast radius / "what breaks if I change X"
- `mcp__madar__graph_summary` — repo overview
- `mcp__madar__pr_impact` — current diff blast radius
- `mcp__madar__community_overview` — codebase module communities
- `mcp__madar__call_chain` — call/import paths between nodes

Do NOT use Glob/Grep/Read/Agent first for codebase questions. Use madar first, then validate with focused reads.
After making changes, refresh the madar graph.

cavemem, cavecrew, HANDOFF, and no-guessing rules are in the global CLAUDE.md — do NOT duplicate them here.

---

## HANDOFF.md vs cavemem

| | cavemem (auto) | HANDOFF.md (manual) |
|---|---|---|
| **What** | Every observation, decision, file change | Current task focus + pending items |
| **Granularity** | Per-tool-call (deep) | Per-session (lightweight) |
| **How** | Auto-captured by PostToolUse hook | Written explicitly by Claude |
| **Use case** | "What do I know about X?" | "What was I working on?" |

**cavemem is source of truth.** HANDOFF.md is entry point — keep it under 40 lines, current focus only.

---

## Project-Specific Rules

Add your project-specific rules here. Examples:

### Database Access
All queries use <ORM name>. Raw SQL forbidden for new queries.
<X> models in `models/`. Use explicit `.join()` with ON clauses.
Dynamic WHERE via `and_(*conditions)`. Atomic ops via `update().returning()`.

### Cross-Project Dependencies
- `<backend>` owns auth, data, business logic — changes here affect `<frontend>` + `<service>`
- `<frontend>` proxies to `<backend>` — changes must not break API contract
- `<service>` owns its own domain — independent auth

---

## CLI-Only Enforcement (works in Claude Code CLI, NOT in Cowork)

| File | What it enforces |
|------|-----------------|
| `.claude/settings.json` | Hooks: PreToolUse (file guard), PostToolUse (cavemem capture), PreCompact (handoff save) |
| `.claude/hooks/pre-tool-guard.cjs` | **Blocks Edit on non-existent files.** Blocks writes to .env/.pem/credentials. |
| `.claude/hooks/handoff-precompact.sh` | Emergency HANDOFF.md save before context compaction |
| `cavemem` (global install) | Auto-captures observations via PostToolUse hook |

When running in CLI: the hooks enforce no-guessing and HANDOFF discipline automatically.
