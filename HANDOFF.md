# HANDOFF.md — spec-tech SDD Environment

## Session: 2026-07-09 — Recipe-to-Navigation Enhancement

### Completed
Transformed SDD from recipe-thinking to navigation-thinking across 5 gaps:

1. **Challenge Mechanism (Gap 2)** — Guardian now returns CHALLENGE verdict alongside PASS/REJECT. Decision matrix with 6 concrete scenarios (SPEC_FACTUALLY_WRONG, SPEC_INCOMPLETE). Every CHALLENGE requires file:line evidence — no opinion-based challenges. Language shift: "Spec is Source of Truth" → "Spec is Current Contract."

2. **Anti-Lazy Guardrails (Gap 3)** — 6-point evidence checklist for spec changes. "Change spec to match code" explicitly blocked as resolution strategy. Guardian re-verify after spec update prevents circular resolution. Evidence must trace to root cause, not consequence.

3. **Spike Phase (Gap 1)** — New `spike` agent (yellow, sonnet). Phase 0 added to sdd-spec-start and sdd-implement. `uncertainty: high` markers trigger spike investigation before spec lock. Every entity/AC now has `uncertainty` and `rationale` fields. Template updated with `decisions:` section.

4. **Discovered Opportunities (Gap 4)** — Maestro now collects `discovered_opportunities` during planning (max 5). Phase 5 presents them to user with accept/deny/postpone. Accepted → tasks in next cycle. Denied/postponed → learning store. Template updated with `opportunities:` section.

5. **Learning Store (Gap 5)** — JSON-backed store at `~/.claude/hooks/learnings.json`. Schema defined in `learnings-schema.sql` (SQLite target). `learning-capture.cjs` (PostToolUse hook) auto-captures. `learning-inject.cjs` (UserPromptSubmit hook) injects relevant past context. `/sdd-learnings` command for query/export/manual entry. Settings.json updated with both hooks.

### Files Modified (7)
- `agents/guardian.md` — CHALLENGE verdict, decision matrix, language shift
- `agents/maestro.md` — discovered_opportunities collection + guidelines
- `skills/sdd-implement/SKILL.md` — Phase 0, CHALLENGE loop, anti-lazy gate, opportunities (Phase 1/5/9), language shift
- `commands/sdd-spec-start.md` — Phase 0 spike detection before lock
- `commands/sdd-spec-update.md` — Anti-lazy guardrails, evidence checklist, blocked resolution patterns
- `templates/spec.template.yaml` — uncertainty, decisions, rationale, opportunities sections
- `~/.claude/settings.json` — learning-capture + learning-inject hook registration

### Files Created (5)
- `agents/spike.md` — Spike execution agent
- `hooks/learning-capture.cjs` — PostToolUse learning capture hook
- `hooks/learning-inject.cjs` — UserPromptSubmit learning injection hook
- `hooks/learnings-schema.sql` — SQLite schema reference
- `commands/sdd-learnings.md` — Learning store query/export command

### Deployed to ~/.claude/
All 12 files deployed: agents (guardian, maestro, spike), hooks (learning-capture, learning-inject, learnings-schema), commands (sdd-spec-start, sdd-spec-update, sdd-learnings), skills (sdd-implement). Settings.json updated.

### Key Architecture Decisions
- **Implementation order**: Gap 2+3 first (foundation), then 1 (uses new language), then 5 (feeds from all), then 4 (closes loop).
- **JSON not SQLite**: better-sqlite3 not available in this environment. Used JSON file storage matching existing hook patterns. Schema.sql is migration target.
- **User gates**: Every CHALLENGE resolution and spec change requires user confirmation. AI cannot decide "spec was wrong."
- **Evidence over opinion**: "Code already does this" is never valid evidence. Evidence must trace to root cause from external project constraints.
- **Spike writes no permanent code**: Temporary prototypes only, cleaned up after reporting.
- **Guardian re-verify after spec change**: Prevents circular "spec changed so code passes" pattern.
- **Max 5 opportunities per cycle**: Prevents overwhelming user with optional work.

### Pending
- Operational testing on real project (full pipeline with CHALLENGE + spike + opportunities)
- Install better-sqlite3 for SQLite migration path
- Test learning-capture hook in a live session (verify learnings.json is created)
- Test learning-inject hook relevance scoring with real prompts
- Test `/sdd-learnings` command end-to-end

### Next Actions
1. Run full `/sdd-implement` pipeline on a test project to verify CHALLENGE flow
2. Test `/sdd-spec-start` with a new domain spec to verify Phase 0 spike detection
3. Test `/sdd-learnings list` after first CHALLENGE resolution
4. Push spec-tech changes to GitHub