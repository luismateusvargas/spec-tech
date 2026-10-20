---
name: sdd-review-simple
description: Independently review a script, utility, or compact app change for task-spec coverage and plausible regressions. Use after simple-code implementation.
---

# Review simple code

1. Identify the intended diff, then read the task spec, project rules, changed files, and affected callers or tests. If the implementation used the SDD engine, call `get_run_report` and inspect its scope report, including undeclared paths and flags. Retrieve relevant Caipira history when available, but judge current code and behavior directly.
2. Check each acceptance criterion and existing behavior the change could disturb. Examine meaningful edge cases, permissions, external requests, and stored data if touched. Reproduce the reported bug and run focused checks or a practical manual scenario where possible.
3. Judge every scope finding against the spec and actual diff. Record necessary additions as spec gaps; treat unjustified changes as findings with a counter-plan to revert them. A flag asks for inspection and is not proof of a defect. Report findings first, ordered by severity. For each, give a path and line, triggering case, impact, evidence, and a concrete correction. Then state checks run, criteria covered, and anything unverified.
4. If a criterion fails or a regression is confirmed, create a separate [counter-plan](../sdd-shared/templates/review.counter-plan.template.md) beside the original task spec, following the project's naming convention (otherwise `<task-stem>.counter-plan.md`). Tie every correction to a finding and its reproducing evidence; include only the smallest changes and checks needed to fix those failures. Mark blockers explicitly and do not turn unverified behavior into a repair task. Report its path. If no findings are supported, say so with coverage limits. Do not claim the change is bug-free or edit code unless fixes were requested.
5. Check the baseline and completion SHAs, then follow the [project-local Git checkpoint workflow](../sdd-shared/templates/git-checkpoints.md). On fully verified approval, tag the reviewed completion commit locally and report its name and SHA. Leave failures or incomplete verification untagged.
