---
name: sdd-implement
description: >
  SDD implementation pipeline. Reads a spec file, extracts actionable tasks
  (violations, acceptance criteria, gaps), and orchestrates the full cycle:
  plan → delegate → verify → fix → test → review. Uses Maestro for planning,
  cavecrew workers for implementation, and Guardian for spec-compliance
  verification. Trigger: "/sdd-implement <spec-file-path>".
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
```

### 5.2 User review
"Review the changes and approve."

User manually tests, reviews code, verifies behavior.

### 5.3 User approves
User says "approve" or "done" → run `/sdd-spec-update` to update specs as Source of Truth.

### 5.4 Archive
Task board marked ALL DONE. HANDOFF.md updated. Pipeline complete.

## Key Rules (NEVER VIOLATE)

### Effort levels
- Maestro: always spawn with `model: sonnet`
- Guardian: always spawn with `model: sonnet`
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
User must approve: plan (Phase 1), sdd-spec-test invocation (Phase 4), final review (Phase 5). Do not skip these gates.

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
- Deactivate sdd-implement skill
- "Pipeline stopped at Phase N. Task board saved to HANDOFF.md. Resume with `/sdd-implement <spec-file>`."

## Recovery

If context is lost mid-pipeline:
1. Read HANDOFF.md for last checkpoint
2. Search cavemem for recent observations about the spec file
3. Re-read the spec file
4. Reconstruct task board from HANDOFF.md + cavemem
5. Resume from the last completed phase
