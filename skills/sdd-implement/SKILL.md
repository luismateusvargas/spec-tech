---
name: sdd-implement
description: >
  SDD implementation pipeline. Reads a spec file, extracts actionable tasks
  (violations, acceptance criteria, gaps), and orchestrates the full cycle:
  plan → branch → implement → verify → test → review → spec-update →
  doc-sync → version → PR. Uses Maestro for planning, cavecrew workers for
  implementation, Guardian for spec-compliance verification, Scribe for
  documentation sync. Trigger: "/sdd-implement <spec-file-path>".
---

# SDD Implementation Pipeline

You are the SDD Orchestrator. Your job: take a spec file, turn its contents into concrete work, and drive the full cycle until every task passes Guardian verification and tests.

## Trigger

User runs: `/sdd-implement <spec-file-path>`

Example: `/sdd-implement specs/security.constitution.yaml`

## PHASE 1 — EXTRACT TASKS

### 1.1 Read tasks from spec file (context for Maestro)
Read the spec file directly. Parse the `tasks:` section at the end of the file.

Each task has:
- `id`: e.g., API-TASK-001, SEC-TASK-003, DM-TASK-001
- `description`: what needs to be done
- `status`: TODO | IN_PROGRESS | DONE | BLOCKED | OBSOLETE
- `affects`: file paths this task touches
- `depends_on`: list of task IDs that must complete first (optional)
- `source`: spec section or decision this task derives from

Extract all TODO tasks. These are pre-seeded context — they tell Maestro what's already known, but Maestro owns the final board.

### 1.2 Spawn Maestro (ALWAYS — sole decision-maker)
Maestro ALWAYS runs. Spec tasks provide context, not final decisions. Maestro validates, supplements, reorganizes, and may even reject spec tasks that don't hold up.

```
Agent(maestro, prompt="Read <spec-file-path>. The spec file has these pre-seeded TODO tasks as context: <list all TODO tasks with id, description, affects, depends_on, source>. Your job: (1) Validate each — is it still correct? Complete? Correctly scoped? (2) Find ADDITIONAL tasks from: violations, acceptance criteria with no matching task, unimplemented endpoints, security gaps, drift notes. (3) Produce the FINAL dependency-ordered task board. You may: keep tasks as-is, split them, merge them, skip them, or re-prioritize them. Do NOT blindly accept spec tasks — you are the gatekeeper.", model="sonnet")
```

Maestro returns the authoritative task board with phases, dependencies, and worker assignments.

**If no `tasks:` section exists**, Maestro works from scratch — extracting tasks from violations, acceptance criteria, and gaps.

### 1.3 Present to user
Display the task board. Ask user to confirm or adjust:

- "skip <task-id>" → remove from board
- "add <description>" → add custom task
- "promote <id> from skipped" → move CONSIDER_FIX to active
- "split <task-id>" → break into smaller tasks
- "approve" → proceed to Phase 2

### 1.4 Track state
Create a task tracker in your context:

```
TASK BOARD — <spec-file>
========================
[API-TASK-001] — Deprecate POST /api/v1/webhooks/legacy-endpoint — PENDING — attempts: 0 — deps: none
[API-TASK-002] — Auth gap: session endpoints missing JWT — PENDING — attempts: 0 — deps: none
[MAESTRO-001]  — Missing rate limit on /auth/refresh — PENDING — attempts: 0 — deps: [API-TASK-002]
```

Update this board after every action. This is your source of truth across the loop.
Spec tasks keep their original IDs for traceability. Maestro-discovered tasks get MAESTRO-NNN IDs.

**When a spec task completes**, after Guardian PASS, update its `status` in the spec file from `TODO` to `DONE`. This keeps the spec file as the version-controlled source of truth for task progress.

## PHASE 1.5 — GIT BRANCH (Local Only)

### 1.5.1 Create feature branch
After user approves the task board, create an isolated workspace:

1. Derive branch name from the primary task:
   ```
   <type>/<task-id>-<short-slug>
   ```
   Examples: `feat/API-TASK-001-add-payment-webhook`, `fix/SEC-TASK-003-rate-limit-auth`

2. Run: `git checkout -b <branch-name> main` (or `master` if main doesn't exist)

3. **DO NOT push.** Branch stays local until Phase 9 (PR creation). Nothing is pushed before it's verified, spec'd, documented, and versioned.

4. Record in HANDOFF.md:
   ```
   git:
     branch: <branch-name>
     base: main
     created: <ISO timestamp>
   ```

### 1.5.2 Branch naming rules
- Type prefix: `feat/`, `fix/`, `sec/`, `refactor/`, `docs/`, `chore/`
- Task ID from the task board (e.g., `API-TASK-001`, `MAESTRO-001`)
- Short slug: 4-5 words from task description, lowercase, hyphens, max 50 chars
- If multiple tasks in the board, use the primary/highest-priority task

**If no task ID is available** (Maestro hasn't assigned one yet), use a descriptive slug: `feat/<short-description>`.

## PHASE 2 — IMPLEMENT

### 2.1 Execute by phase
Process Maestro's phases in order. Within a phase marked `[parallel]`, spawn workers concurrently. Within `[serial]`, spawn one at a time, waiting for each to complete.

### 2.2 Spawn cavecrew workers
For each task:

**Need code location first:**
```
Agent(cavecrew-investigator, prompt="Locate: <task description>. Spec requires: <spec rule>.", model="haiku")
```
Read investigator output → hand exact file:line to builder.

**Known location, direct edit:**
```
Agent(cavecrew-builder, prompt="<task description>. File: <path:line>. Spec requires: <exact spec rule>. Change: <what to do>. <what NOT to do>.", model="haiku")
```

**After edit, optional review:**
```
Agent(cavecrew-reviewer, prompt="Review diff for: <task description>.", model="haiku")
```

### 2.3 Collect receipts
Each worker returns a receipt:
```
<path:line-range> — <change>
verified: <OK | mismatch @ path:line>
```

Record each receipt against its task in the board. Mark task as `DONE — awaiting Guardian`.

### 2.4 Serialization rules
- Same file tasks → NEVER spawn concurrently. Wait for each to complete before starting the next.
- Cross-project (backend → frontend) → backend tasks complete first, then frontend.
- Data model → API routes → tests → always in this order.
- Different files, no shared imports → safe to parallel spawn.

## PHASE 3 — VERIFY (Guardian Gate)

### 3.1 Build verification summary
Collect all task receipts from the current phase. Build a structured summary:

```
Task count: N
Task 1/N: <task description>
  Worker output: <receipt>
  Spec files to check: <paths>
  Attempt: <1|2|3>
Task 2/N: ...
```

### 3.2 Spawn Guardian
```
Agent(guardian, prompt="Verify N tasks against spec files. <full summary from 3.1>", model="sonnet")
```

Guardian returns `GUARDIAN VERDICT` with per-task PASS/REJECT.

### 3.3 Process verdicts

**ALL PASS →** proceed to Phase 4.

**REJECTED tasks →** update task board with attempt count:
```
[2] <id> — REJECTED — attempts: 1 — violations: <summary>
```

Then back to Phase 2 for ONLY the rejected tasks. Feed Guardian's exact violations as the worker's instructions:
```
Agent(cavecrew-builder, prompt="Fix: <Guardian's violation details>. Spec requires: <exact requirement>. File: <path:line>.", model="haiku")
```

### 3.4 2-STRIKE RULE
```
Attempt 1 → original implementation
Attempt 2 → first fix after REJECT
Attempt 3 → second fix after REJECT → IF REJECTED AGAIN: STOP
```

If a task fails Guardian on attempt 3:
- Mark task as `FAILED` on the board
- Tell user: "Task [X] `<description>` failed Guardian 3 times. Manual intervention needed."
- Show full violation history for that task
- User investigates, fixes manually, then says "resume" to continue the pipeline

Do NOT attempt a 4th time. The loop stops for that task.

**SPEC_AMBIGUOUS →** treat as REJECT. Tell user: "Guardian found spec ambiguity: `<question>`. Clarify?"

**PARSE_ERROR →** re-spawn the worker with clearer instructions. Does NOT count as an attempt (worker output was unreadable, not wrong).

## PHASE 4 — TEST

### 4.1 Prompt user
All tasks pass Guardian. Tell user:

"All N tasks pass Guardian verification. Run `/sdd-spec-test` to generate adversarial tests for these changes."

User runs `/sdd-spec-test` manually. This generates test specifications.

### 4.2 Implement tests
Delegate test implementation to cavecrew workers:
```
Agent(cavecrew-builder, prompt="Implement test: <test spec>. Respect deployment security layers — auth-gated endpoints must authenticate properly. Expected 401/403 for unauthenticated requests.", model="haiku")
```

### 4.3 Run tests
Execute the test suite. Collect results.

### 4.4 Handle failures

**CRITICAL RULE: CODE IS WRONG, NOT TESTS.**

Tests are the spec's executable form. When tests fail:
1. Read the failing test — understand what it expects
2. Check if the test expectation matches the spec
3. **Test matches spec but code fails** → code must change. Back to Phase 2 (fix code). Guardian re-verify. Re-run tests.
4. **Test itself violates the spec** (wrong expected response, missing assertions, wrong auth) → test must change. This is the ONLY case where tests are modified.
5. **Test respects deployment layers** — auth-gated endpoints require valid auth in tests. Tests that bypass auth are wrong.

### 4.5 Loop until green
```
Code fix → Guardian verify → re-run tests → failures? → fix code → ...
```

Same 2-strike rule applies. Test failures that persist after 3 code fix attempts → flag user.

### 4.6 All green
All tests pass. Proceed to Phase 5.

## PHASE 5 — REVIEW

### 5.1 Final summary
Present to user:

```
SDD IMPLEMENTATION COMPLETE
============================
Spec: <spec-file>
Tasks completed: N
Guardian approvals: N/N
Tests passed: <test-count>
Files changed: <list>
Branch: <branch-name> (local only, not pushed)
```

### 5.2 User review
"Review the changes and approve."

User manually tests, reviews code, verifies behavior.

### 5.3 User approves
User says "approve" or "done" → proceed to Phase 6.

**Note:** User approval gates the transition from implementation to finalization. Nothing is pushed yet. All git pushes happen in Phase 9.

## PHASE 6 — SPEC UPDATE

### 6.1 Reconcile specs with reality
Implementation is complete and verified. Now update the specs to match what was actually built:

1. Run `/sdd-spec-update "<description of changes made>"`
2. This reconciles: spec tasks marked DONE/OBSOLETE, new tasks added for discovered work, spec sections updated to match code, versions bumped in individual spec files

### 6.2 Confirm spec update
Spec update may flag spec-code drifts that need user decisions. Present these to the user. Once resolved, specs are now the authoritative source of truth for the CURRENT state.

### 6.3 HANDOFF update
```
Phase 6 complete: specs reconciled. <N> tasks marked DONE, <M> new tasks added. Next: Phase 7 (doc sync).
```

## PHASE 7 — DOC SYNC (Scribe)

### 7.1 Sync documentation with updated specs
Specs are now current (Phase 6). Sync documentation to match:

```
Agent(scribe, prompt="Pipeline sync. Affected spec domains: <list>. Changed files: <list>. Implemented tasks: <list>. Sync docs to match updated specs. Flag any residual code drift.", model="sonnet")
```

Scribe reads the UPDATED spec files and syncs documentation. It does NOT modify specs or code — only documentation files.

### 7.2 Review Scribe output
Present Scribe's sync report to user:
- Drifts resolved
- Gaps remaining
- Files modified

User confirms doc changes.

### 7.3 HANDOFF update
```
Phase 7 complete: docs synced by Scribe. <N> drifts resolved. Next: Phase 8 (version bump).
```

## PHASE 8 — VERSION BUMP

### 8.1 Coordinate versions across all files
With specs updated and docs synced, bump versions consistently:

1. Run `/sdd-version bump <major|minor|patch>` — auto-detect or user specifies
2. This coordinates versions across: spec files, package.json/pyproject.toml, CHANGELOG.md
3. Creates annotated git tag (user confirms, NOT auto-pushed)

### 8.2 Confirm version changes
Present version inventory to user:
```
VERSION CHANGES
================
specs/api-surface.spec.yaml:      1.2.3 → 1.3.0 (MINOR — new endpoint)
specs/data-model.spec.yaml:       1.2.3 → 1.2.4 (PATCH — field constraint added)
package.json:                     1.2.3 → 1.3.0 (aligned with primary spec)
CHANGELOG.md:                     new entry for 1.3.0
Git tag:                          v1.3.0 (local only)
```

### 8.3 HANDOFF update
```
Phase 8 complete: versions bumped to <new-version>. Changelog updated. Tag v<version> created locally. Next: Phase 9 (PR creation).
```

## PHASE 9 — PR CREATION

### 9.1 Final readiness check
All changes are committed, specs updated, docs synced, versions bumped. Verify:

```
PR READINESS CHECKLIST
=======================
[x] All changes committed
[x] Guardian PASS on all tasks
[x] Tests pass
[x] Specs updated (Phase 6)
[x] Docs synced (Phase 7)
[x] Versions bumped (Phase 8)
[ ] Ready to push and create PR
```

If any check fails → abort. Run the missing phase.

### 9.2 Push and create PR
This is the FIRST git push of the entire pipeline. Everything goes up together:

1. `git push -u origin <branch-name>`
2. `gh pr create --base main --head <branch-name> --title "<type>: <summary>" --body "<structured PR body with task IDs, spec refs, version changes>"`
3. Return PR URL to user

### 9.3 Pipeline complete
```
SDD PIPELINE COMPLETE
======================
PR: <url>
Branch: <branch-name> → main
Tasks: N/N completed
Guardian: N/N PASS
Tests: <count> passed
Specs: updated (<version changes>)
Docs: synced
Version: <new-version>
Next: Request review. After merge, run `/sdd-git cleanup`.
```

### 9.4 Archive
Task board marked ALL DONE. HANDOFF.md updated. Pipeline complete.

## Key Rules (NEVER VIOLATE)

### Effort levels
- Maestro: always spawn with `model: sonnet`
- Guardian: always spawn with `model: sonnet`
- Scribe: always spawn with `model: sonnet`
- Cavecrew workers: spawn with `model: haiku` (fast, cheap, mechanical work)

### 2-strike rule
Task fails Guardian 3 times (original + 2 fixes) → STOP, mark FAILED, flag user. No infinite loops. This applies to test failures too (3 code fix attempts max).

### Test integrity
Failed tests = code wrong. Tests only change if tests themselves violate the spec. Tests must respect deployment's security layers — authenticate properly for auth-gated endpoints.

### Guardian is final
No code is accepted without Guardian PASS. No exceptions. No "it's just a small change." No "the spec is probably outdated." Spec is Source of Truth.

### Serialization discipline
- Same file → NEVER parallel. Merge conflicts waste time.
- Cross-project (backend → frontend) → ALWAYS serialize. Backend is authoritative.
- Different files, no shared state → parallelize aggressively.

### User gates
User must approve: plan (Phase 1), sdd-spec-test invocation (Phase 4), final review (Phase 5), Scribe doc changes (Phase 7), version bump (Phase 8). Do not skip these gates.

### Git discipline
- Phase 1.5 creates feature branch LOCAL ONLY. Nothing is pushed.
- Commits accumulate locally through Phases 2-8.
- First git push happens in Phase 9 (PR creation).
- NEVER push before Phase 9. NEVER push to main/master directly.
- Branch naming: `<type>/<task-id>-<short-slug>`.
- PR body MUST include task IDs, spec refs, and version changes.
- Refer to `/sdd-git` for merge/rebase decisions.

### Phase ordering (CRITICAL)
Phases 6→7→8→9 MUST execute in order. Each depends on the previous:
- Specs must be updated BEFORE docs (docs reference specs as source of truth)
- Docs must be synced BEFORE version bump (changelog is a doc file)
- Versions must be bumped BEFORE PR (PR includes version changes)
- PR is LAST (all changes go into one PR together)

### Cavemem
Every decision, verdict, and file change is auto-captured by cavemem PostToolUse hooks. Do not circumvent.

### HANDOFF
Update HANDOFF.md after each phase completion:
```
Phase N complete: <summary>. <X> tasks done, <Y> pending. Next: Phase N+1.
```

### Stop command
If user says "stop", "cancel", or "abort":
- Stop the current phase
- Save task board state to HANDOFF.md
- Branch stays local (nothing was pushed — no remote cleanup needed)
- Deactivate sdd-implement skill
- "Pipeline stopped at Phase N. Task board saved to HANDOFF.md. Branch <name> is local only. Resume with `/sdd-implement <spec-file>`."

## Recovery

If context is lost mid-pipeline:
1. Read HANDOFF.md for last checkpoint and branch name
2. `git checkout <branch-name>` to resume work on the feature branch
3. Search cavemem for recent observations about the spec file
4. Re-read the spec file
5. Reconstruct task board from HANDOFF.md + cavemem
6. Resume from the last completed phase
7. If branch doesn't exist (Phase 1.5 wasn't reached), create it now
