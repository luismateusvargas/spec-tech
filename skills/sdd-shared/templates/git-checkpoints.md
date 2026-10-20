# Local Git checkpoints for SDD implementation and review

Use the target project's Git repository and its branch, commit, and tag conventions. Run Git operations from that project root. Keep checkpoints and approval tags local; the project owner handles pushes and releases. Do not bump a release version, create a release tag, publish, merge, or push as part of this workflow.

## Before implementation

1. Confirm the repository root, current branch, `HEAD`, and `git status --short`. Follow the project's branch policy; create a local task branch before committing if required. Do not reset, clean, stash, overwrite, or discard existing work.
2. Inspect staged, unstaged, and untracked files. Exclude secrets, generated artifacts, and ignored files. If unrelated work is present, keep it out of the task commits; use an isolated worktree from `HEAD` when that preserves the intended starting state, or resolve ownership before including it. Never silently commit another person's changes.
3. Before the first implementation edit or calling the SDD engine (`begin_task`), make a baseline commit representing the exact project state the task will start from. Commit reviewed existing changes that belong to that state; if it is already clean, make an explicit empty checkpoint commit. Name the project and task in the message, for example `chore(<project>): checkpoint before <task-id>`. Record the baseline SHA. When using the SDD engine, keep `HEAD` at this baseline commit until `finish_task` completes so the engine can diff the starting tree and roll back failed runs safely.

## After implementation

1. Run the task's relevant checks (or complete the SDD engine `submit` and `finish_task` lifecycle), inspect the full diff and status against the baseline, and verify that no unrelated deletion, secret, or generated artifact is staged. Commit only the task's reviewed files, including authorized spec changes. If checks fail, say so in the commit message and summary; a failed implementation is not approved merely because it has a commit. If work stops before any implementation edit, report the baseline without inventing a completion commit.
2. Make a second commit with the project and task in its message, for example `feat(<project>): <task-id> <outcome>` or `wip(<project>): <task-id> failed checks`. Record both SHAs and the checks/results for review. Keep the baseline reachable; do not amend, squash, or rewrite these checkpoints before review.

For **every** commit in this workflow, write the complete message yourself. Never add a `Co-authored-by:` line or other co-author trailer in the subject or body, including from templates or automation. Inspect the final commit message after creation and correct any injected co-author line before continuing. Do not change repository-wide or global Git identity settings to achieve this.

## After independent review

Tag only when every applicable task criterion and required check is verified, no blocking finding remains, the reviewed completion commit is `HEAD`, and the worktree is clean. If a check cannot run or the implementation fails, report the limit or create the counter-plan; do not tag. Use the project's existing **review checkpoint** tag convention when it has one. Otherwise create a unique local annotated tag such as `sdd/approved/<task-slug>-<short-sha>` on the reviewed commit. Never move or replace an existing tag. Keep its annotation free of co-author trailers. Report the tag name and target SHA. This tag records review approval, not a release.
