# Git Workflow Reference — SDD Environment

Reference for merge vs rebase, branch strategies, and git best practices in the SDD context. Consult this before any non-trivial git operation.

---

## Branch Strategy

### Trunk-Based with Feature Branches

```
main ─────────────────────────────────────────────────────
  │
  ├── feat/API-TASK-001-payment-webhook ──┬── PR (squash) ──┤
  │                                       │
  ├── fix/SEC-TASK-003-rate-limit ────────┬── PR (squash) ──┤
  │                                       │
  └── refactor/DM-TASK-002-split-fields ──┬── PR (squash) ──┘
```

**Rules:**
- `main` is always deployable. Never commit directly to main.
- Feature branches are short-lived. Merge within days, not weeks.
- One task = one branch = one PR = one squash commit on main.
- Delete feature branches after merge.

### Branch Naming Convention

```
<type>/<task-id>-<short-slug>

Types:
  feat/      New feature, endpoint, entity
  fix/       Bug fix, patch
  sec/       Security enforcement
  refactor/  Code restructuring (no behavior change)
  docs/      Documentation only
  chore/     Tooling, config, dependencies
  version/   Version bump coordination (rare)
```

---

## Merge vs Rebase

### Decision Flowchart

```
Need to integrate changes?
  │
  ├── Is this a private branch (only you)?
  │     ├── YES → REBASE (clean history)
  │     └── NO → MERGE (don't rewrite shared history)
  │
  ├── Is this merging a PR to main?
  │     └── YES → SQUASH MERGE (SDD default)
  │
  └── Are there >3 conflicting commits?
        └── YES → MERGE (resolve once, not N times)
```

### MERGE — `git merge`

**Creates a merge commit.** Preserves complete history including the point where branches diverged.

```
Before:                    After merge:
A---B---C main             A---B---C-------M main
     \                         \         /
      D---E feature             D---E---F
```

**Use when:**
- Bringing main into a shared feature branch
- Branch has been pushed and others might be using it
- You want to preserve the full historical record
- Resolving complex conflicts (resolve all at once)

**Commands:**
```bash
# Update feature branch with latest main
git checkout feature
git merge main

# If conflicts: resolve, then
git add .
git commit -m "merge: integrate main into feature"
```

**Pros:** Safe, preserves history, never loses commits.
**Cons:** Merge commits clutter history. Non-linear history harder to follow.

### REBASE — `git rebase`

**Replays commits on top of another branch.** Rewrites commit history. Linear, clean.

```
Before:                    After rebase:
A---B---C main             A---B---C main
     \                              \
      D---E feature                  D'---E' feature
```

**Use when:**
- Updating a PRIVATE feature branch with latest main
- Cleaning up WIP commits before creating PR
- Branch has NOT been pushed, or you're the only one using it

**Commands:**
```bash
# Update feature branch with latest main
git checkout feature
git rebase main

# If conflicts: resolve each commit, then
git add .
git rebase --continue
# OR abort entirely:
git rebase --abort
```

**Pros:** Linear history, no merge commits, cleaner git log.
**Cons:** Rewrites history (dangerous on shared branches). Conflicts must be resolved per-commit.

**GOLDEN RULE: NEVER rebase a branch others are working on.**

### SQUASH MERGE — GitHub "Squash and merge"

**Combines all PR commits into one commit on main.** The SDD default.

```
Before:                    After squash:
A---B---C main             A---B---C---S main
     \                              (S = D+E+F squashed)
      D---E---F feature
```

**Use when:**
- Merging most SDD task PRs (one task = one commit)
- PR has WIP commits that shouldn't pollute main history
- You want a clean, revertible commit per feature

**Commands:**
```bash
# Via GitHub UI: select "Squash and merge" in PR
# Via CLI:
gh pr merge <number> --squash
```

**Pros:** Clean main history. Easy to revert. One commit per feature.
**Cons:** Loses granular commit history on main. Not suitable for multi-feature PRs.

### INTERACTIVE REBASE — `git rebase -i`

**Manually edit commit history.** Squash, reorder, reword, or drop commits.

**Use when:**
- Cleaning up WIP commits before PR
- Combining "fix typo" + "actually fix" + "final fix" into one coherent commit
- Reordering commits for logical grouping

```bash
# Edit last 5 commits
git rebase -i HEAD~5

# Commands in editor:
# pick   = keep as-is
# reword = change commit message
# squash = combine with previous commit (keep both messages)
# fixup  = combine with previous commit (discard message)
# drop   = remove commit entirely
```

---

## Conflict Resolution

### Merge Conflicts

Conflicts happen when two branches change the same lines differently.

```bash
git merge main
# CONFLICT in src/payments.ts
```

**Resolution:**
1. Open conflicted file. Find conflict markers:
   ```
   <<<<<<< HEAD
   const port = 3000
   =======
   const port = 8080
   >>>>>>> main
   ```
2. Choose correct version (or combine both).
3. Remove conflict markers.
4. `git add <file>` then `git commit`.

**SDD rule:** If spec says port 3000, keep HEAD. If spec says 8080, keep main. Spec is authority.

### Rebase Conflicts

Same process, but repeated per commit being replayed.

```bash
git rebase main
# CONFLICT in commit 1/3
# Resolve → git add → git rebase --continue
# CONFLICT in commit 2/3
# Resolve → git add → git rebase --continue
```

**If >3 commits have conflicts:** Abort and merge instead.
```bash
git rebase --abort
git merge main
```

---

## Force Push

### `--force-with-lease` (safer)

```bash
git push --force-with-lease origin feature
```

Fails if remote has commits you don't have locally. Protects against overwriting others' work.

### `--force` (dangerous)

```bash
git push --force origin feature  # AVOID
```

Blindly overwrites remote. Can destroy others' commits.

**SDD rule:** NEVER `--force`. Use `--force-with-lease` only on your own feature branch, only after confirming no one else is using it.

---

## Common Workflows

### Start New SDD Task
```bash
git checkout main
git pull
git checkout -b feat/API-TASK-001-add-webhook main
# ... implement, commit locally ...
# ... Guardian verify, tests pass ...
# ... spec-update, scribe, version-bump ...
git push -u origin feat/API-TASK-001-add-webhook
gh pr create --base main --head feat/API-TASK-001-add-webhook
```

### Update Feature Branch from Main
```bash
git checkout feat/API-TASK-001-add-webhook
git fetch origin
git rebase origin/main
# OR if branch is shared:
git merge origin/main
```

### Clean WIP Commits Before PR
```bash
git log --oneline  # See what you have
git rebase -i HEAD~5  # Squash last 5 into 1
# Rewrite final commit message referencing task ID
```

### After PR Merged
```bash
git checkout main
git pull
git branch -d feat/API-TASK-001-add-webhook
git push origin --delete feat/API-TASK-001-add-webhook  # optional
```

---

## Anti-Patterns

| Anti-Pattern | Why Bad | Correct |
|-------------|---------|---------|
| Committing directly to main | No review, no isolation, can't revert easily | Feature branch + PR |
| `git push --force` on main | Destroys others' commits, breaks everyone's clone | Never do this |
| Rebasing a shared branch | Duplicate commits, lost work, confused teammates | Merge instead |
| "Mega-PR" with 20+ commits across 5 features | Impossible to review, hard to revert | One PR per task |
| Force-pushing to "fix" a PR after review started | Review comments lose context | Add new commits, squash at merge |
| Not pulling before starting new work | Divergent history, big merge conflicts later | `git pull` first |
| Vague commit messages | Can't understand history, can't trace to tasks | Task ID in every commit |
| Keeping stale branches | Clutter, confusion about what's active | Delete after merge |
