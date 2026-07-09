# /sdd-learnings — SDD Learning Store Query & Export

## Trigger
Manual only. User types `/sdd-learnings <command> [args]`.

## Purpose
Query, export, and manage the persistent cross-session learning store.
Captures spec errors, incomplete specs, architectural decisions, implementation insights,
and discovered opportunities — with evidence chains tracing back to root causes.

## Commands

### `/sdd-learnings list [category]`
List recent learnings. Optional filter by category:
- `spec_error` — Spec was factually wrong (from CHALLENGE SPEC_FACTUALLY_WRONG)
- `spec_incomplete` — Spec missed a concern (from CHALLENGE SPEC_INCOMPLETE)
- `implementation` — Implementation insights or patterns
- `discovery` — Discovered opportunities during implementation
- `decision` — Architectural decisions (from spec decisions section)
- `failure` — What was tried and failed

### `/sdd-learnings recent [days]`
Show learnings from the last N days (default: 7). Useful for pre-session context.

### `/sdd-learnings get <id>`
Show full details of a specific learning entry, including evidence chain, rationale, and tags.

### `/sdd-learnings export [--format md] [--category <cat>] [--since <date>]`
Export learnings to Markdown. Default: all categories, last 30 days.
Output goes to `learnings-report.md` in the project root.

Output format:
```markdown
# SDD Learning Report — <project>
## Generated: <date>

### Spec Errors Corrected (N)
- **SPEC_ERROR (2026-07-09)**: PostgreSQL → SQLite
  Evidence: package.json (sqlite3 dep), alembic/env.py (sqlite dialect)
  Root cause: Spec was generated from incorrect code analysis assumption
  Resolution: Updated spec to match project stack

### Specs Made Complete (N)
- **SPEC_INCOMPLETE (2026-07-08)**: Added timeout configuration
  Evidence: requests began timing out at 30s default, spec had no timeout
  Root cause: Timeout was never specified
  Resolution: Added 30s default to spec, pending config review

### Architectural Decisions (N)
- **DECISION (2026-07-07)**: JWT over session auth
  Rationale: Stateless auth for microservice architecture, no shared session store
  Alternatives considered: Redis sessions, opaque tokens
  Evidence: docs/architecture.md:45

### Deferred Opportunities (N)
- **OPPORTUNITY (2026-07-06)**: Rate limiting on /auth/refresh
  Context: Endpoint is un-rate-limited and called on every token refresh
  Resolution: Deferred to Sprint 3 — need capacity planning data first

### Implementation Insights (N)
- ...

### Failures (N)
- ...
```

### `/sdd-learnings add`
Manual entry. Prompts user for:
- Category (spec_error | spec_incomplete | implementation | discovery | decision | failure)
- Title (one-line summary)
- Description (what was learned)
- Evidence (file:line references — comma separated)
- Rationale (why it matters)
- Tags (comma separated)

### `/sdd-learnings stats`
Show summary statistics:
```
Learning Store Stats
=====================
Total entries: N
By category:
  spec_error:      N
  spec_incomplete: N
  implementation:  N
  discovery:       N
  decision:        N
  failure:         N
By resolution:
  accepted:      N
  deferred:      N
  rejected:      N
  experimental:  N
Date range: YYYY-MM-DD to YYYY-MM-DD
```

## Implementation

Read from `~/.claude/hooks/learnings.json`. Format each entry using the schema defined in `learnings-schema.sql`.

If `learnings.json` does not exist: "No learning store found. The learning-capture hook auto-creates it on first spec change or CHALLENGE resolution."

## Constraints
- This is a READ-ONLY command (except `add` which modifies learnings.json only)
- Never modifies spec files, source code, or configuration
- Export writes to the project root only — never outside the project
- Learning IDs are auto-generated (`LRN-<timestamp>-<random>`)

## Integration

The learning store is populated by:
- **learning-capture.cjs** — PostToolUse hook, auto-captures on Edit/Write
- **sdd-implement Phase 5** — Archives denied/postponed opportunities
- **sdd-implement Phase 3.5** — Captures CHALLENGE resolutions
- **Spike agent** — Reports findings as `source: spike` entries
- **`/sdd-learnings add`** — Manual entries
