# /sdd-git — SDD Git Workflow & PR Management

## Trigger
Manual only. User MUST type `/sdd-git <action>` where action is:
- `branch` — Create feature branch from task ID (early in pipeline, LOCAL ONLY)
- `pr` — Create pull request (LAST step, after specs + docs + versions)
- `status` — Show current branch, commits ahead/behind, uncommitted changes
- `cleanup` — Delete merged feature branch locally and remotely

## Purpose
Manage git workflow in the SDD context. Two distinct phases called at DIFFERENT points in the pipeline:

1. **Branch creation (Phase A)** — Before implementation. Creates isolated workspace. NEVER pushes.
2. **PR creation (Phase B)** — After EVERYTHING is done. Pushes branch and opens PR with all changes.

The SDD rule: nothing is pushed before it's verified, spec'd, documented, and versioned.

## Pre-Conditions
- Git repository initialized (`git rev-parse --git-dir` succeeds)
- `gh` CLI installed and authenticated (`gh auth status` exits 0) — only required for `pr` action
- For `branch`: task ID or description available (from spec file or HANDOFF.md)
- For `pr`: all changes committed, specs updated, docs synced, versions bumped

---

## Phase A: Branch Creation (`/sdd-git branch`)

### When
Called at Phase 1.5 of sdd-implement — after Maestro extracts tasks, before Cavecrew implements.

### Behavior

#### A.1 Detect base branch
```bash
# Prefer main, fall back to master
git branch --list main && BASE="main" || BASE="master"
```

#### A.2 Derive branch name from task context
Read the primary task ID and description from the task board or HANDOFF.md. Format:

```
<type>/<task-id>-<short-slug>
```

| Type | When |
|------|------|
| `feat/` | New feature, endpoint, entity from spec |
| `fix/` | Bug fix from spec violation |
| `sec/` | Security rule enforcement |
| `refactor/` | Code restructuring, no behavior change |
| `docs/` | Spec update only, no code change |
| `chore/` | Tooling, config, dependencies |

**Slug rules:**
- Lowercase, hyphens not underscores
- Max 4-5 words from task description
- Strip articles (a, an, the)
- 50 chars max for the slug portion

**Examples:**
```
feat/API-TASK-001-add-payment-webhook
fix/SEC-TASK-003-rate-limit-auth
sec/MAESTRO-001-sanitize-user-input
refactor/DM-TASK-002-split-name-fields
```

#### A.3 Create branch (LOCAL ONLY)
```bash
git checkout -b <branch-name> <base-branch>
```

**DO NOT push at this stage.** Branch is local until PR creation (Phase B).

#### A.4 Record in HANDOFF.md
```
git:
  branch: feat/API-TASK-001-add-payment-webhook
  base: main
  created: 2026-07-09
```

### Output

```
SDD GIT — Branch Created
=========================
Branch: feat/API-TASK-001-add-payment-webhook
Base: main
Status: LOCAL ONLY (not pushed)
Next: Implement tasks. Nothing is pushed until Phase 9.
```

---

## Phase B: PR Creation (`/sdd-git pr`)

### When
Called at Phase 9 of sdd-implement — the LAST step. After:
- Phase 6: `/sdd-spec-update` reconciled specs
- Phase 7: Scribe synced documentation
- Phase 8: `/sdd-version` coordinated version bumps

### Pre-Flight Checks
Before creating PR, verify ALL of these:

```
PR READINESS CHECKLIST
=======================
[ ] All changes committed (git status --porcelain is empty)
[ ] /sdd-spec-update completed (specs reconciled)
[ ] Scribe completed (docs synced with updated specs)
[ ] /sdd-version completed (versions bumped + changelog updated)
[ ] Guardian passed all tasks (Phase 3 all PASS)
[ ] Tests pass (Phase 4 all green)
[ ] User approved review (Phase 5 complete)
```

If ANY check fails → abort. "PR blocked: <check> not complete. Run the missing phase first."

### Behavior

#### B.1 Push branch
```bash
git push -u origin <branch-name>
```

First git push of the entire pipeline. Everything goes up together.

#### B.2 Build PR body
Gather context from the task board, HANDOFF.md, and spec files:

```markdown
## Summary
<One-paragraph description of what this PR does>

## Tasks Completed
- <TASK-ID>: <description> (spec: <spec-file>)
- <TASK-ID>: <description> (spec: <spec-file>)

## Spec Files Affected
- specs/<file>.yaml (v<old> → v<new> — <bump-type>)
- specs/<file>.yaml (v<old> → v<new> — <bump-type>)

## Breaking Changes
- <None / list with migration notes>

## Checklist
- [x] Guardian verification passed (N/N tasks)
- [x] Tests pass (<count> tests)
- [x] Specs updated via /sdd-spec-update
- [x] Docs synced via Scribe
- [x] Versions bumped via /sdd-version
- [x] No security regressions

## Related Specs
- <link to spec file sections>
```

#### B.3 Create PR
```bash
gh pr create \
  --base <base-branch> \
  --head <branch-name> \
  --title "<type>: <summary>" \
  --body "<PR body from B.2>"
```

#### B.4 Output PR URL
```
SDD GIT — PR Created
=====================
PR: <url>
Branch: feat/API-TASK-001-add-payment-webhook → main
Next: Request review. After merge, run `/sdd-git cleanup`.
```

### Constraints (PR creation)
- NEVER create PR before Phase 6-8 are complete. No exceptions.
- NEVER push to main/master directly. Always through PR.
- NEVER force push without explicit user confirmation and reason.
- PR title uses conventional commit format: `feat:`, `fix:`, `sec:`, `refactor:`, `docs:`, `chore:`.
- PR body MUST include task IDs and spec file references for traceability.

---

## Merge/Rebase Decision Matrix

Embedded reference. Consult this before any merge or rebase operation.

### When to MERGE (`git merge`)

| Scenario | Command | Why |
|----------|---------|-----|
| Bringing main into feature branch to resolve conflicts | `git merge main` (on feature branch) | Preserves complete history. Safe for branches others might depend on. |
| Merging PR to main (via GitHub UI) | "Merge pull request" button | Creates merge commit. Full history preserved. Use for multi-commit features. |
| Shared/public branches | `git merge` | NEVER rebase a branch others are working on. Rewriting shared history causes duplicate commits and lost work. |

### When to REBASE (`git rebase`)

| Scenario | Command | Why |
|----------|---------|-----|
| Updating feature branch with latest main (clean history) | `git rebase main` (on feature branch) | Linear history. No merge commits. Only on PRIVATE branches. |
| Cleaning WIP commits before PR | `git rebase -i HEAD~N` | Squash, reorder, reword commits. One clean commit per logical change. |
| Before PR when main has advanced | `git rebase main` then `git push --force-with-lease` | Linear history. Force push ONLY on your feature branch, ONLY after confirming no one else is using it. |

### When to SQUASH MERGE (recommended for SDD)

| Scenario | Why |
|----------|-----|
| Most SDD task PRs | One task = one clean commit on main. Task ID in commit message. Easy to revert. Easy to trace. |
| Small fixes, typo corrections | Don't clutter main history with "fix typo" commits. |

**SDD recommendation:** Squash-merge PRs unless the feature has distinct, independently-reviewable logical steps that should remain separate in main history.

### When to REBASE INTERACTIVE (`git rebase -i`)

Use before PR creation to clean up WIP commits:

```bash
# Squash last 5 commits into 1
git rebase -i HEAD~5
# Mark commits 2-5 as "squash" or "fixup"
# Rewrite commit message to reference task ID
```

### Golden Rules

1. **NEVER rebase shared branches.** If you've pushed and someone else might have pulled, merge instead.
2. **NEVER force push to main/master.** Ever. For any reason.
3. **ALWAYS `--force-with-lease` not `--force`.** Safer — fails if remote has commits you don't have locally.
4. **When in doubt, merge.** Merge is always safe. Rebase requires understanding of the implications.
5. **Squash-merge is the SDD default.** Clean main history. One task = one commit.

### Conflict Resolution

```
MERGE CONFLICT → resolve in merge commit. All conflicts resolved at once. One commit.
REBASE CONFLICT → resolve per commit being replayed. Conflicts N times for N commits.
                   If >3 commits have conflicts, abort rebase and merge instead:
                   git rebase --abort && git merge main
```

---

## Cleanup (`/sdd-git cleanup`)

### When
After PR is merged. User confirms: "PR #<number> merged. Clean up branch."

### Behavior
```bash
git checkout <base-branch>
git pull
git branch -d <feature-branch>           # Delete local
git push origin --delete <feature-branch> # Delete remote (if pushed)
```

### Output
```
SDD GIT — Cleanup Complete
===========================
Deleted: feat/API-TASK-001-add-payment-webhook (local + remote)
Current branch: main
Status: Clean
```

## Status (`/sdd-git status`)

Quick overview of git state:

```
SDD GIT — Status
=================
Branch: feat/API-TASK-001-add-payment-webhook
Base: main
Ahead: +3 commits (not pushed)
Behind main: 0 commits
Uncommitted: 2 files (src/payments.ts, specs/api-surface.spec.yaml)
Last commit: "API-TASK-001: implement payment webhook handler" (2 min ago)
PR: Not created
Pipeline phase: Phase 3 (Guardian verification complete)
```

## Output Format (all actions)

Every sdd-git action outputs this block:

```
SDD GIT — <Action Complete>
============================
<action-specific fields>
Next: <what to do next>
```

## Constraints

### Absolute
- NEVER push to main/master directly. Always through a feature branch + PR.
- NEVER force push without user confirmation.
- NEVER create PR before Phase 6-8 are complete (specs, docs, versions must be updated).
- Branch creation (Phase A) is LOCAL ONLY. First git push happens in Phase B (PR creation).
- ALWAYS check `gh auth status` before PR creation. Fail gracefully if not authenticated.
- ALWAYS record branch name in HANDOFF.md for pipeline recovery.

### Edge cases
- **No tasks available for branch naming**: Ask user for a short description. Use `feat/<slug>` without task ID.
- **gh CLI not installed**: "gh CLI not found. Install from https://cli.github.com. Without gh, PR must be created manually on GitHub."
- **Branch already exists**: "Branch <name> already exists. Switch to it? [y/N]"
- **Uncommitted changes at PR time**: "Uncommitted changes found. Commit them before creating PR." Show `git status`.
- **Main has advanced significantly**: Suggest `git rebase main` before PR to resolve conflicts early.
- **Not in a git repo**: "No git repository found. Initialize with `git init` first."

### Integration with sdd-implement
- Phase 1.5 calls `/sdd-git branch` (local only, no push).
- Phase 9 calls `/sdd-git pr` (first push + PR creation).
- Between Phase 1.5 and Phase 9: local commits accumulate. No pushes.
- If pipeline is abandoned, branch stays local. No cleanup needed on remote.
