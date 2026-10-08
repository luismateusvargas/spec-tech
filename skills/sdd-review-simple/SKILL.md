---
name: sdd-review-simple
description: Independently review a script, utility, or compact app change for task-spec coverage and plausible regressions. Use after simple-code implementation.
---

# Review simple code

1. Identify the intended diff, then read the task spec, project rules, changed files, and affected callers or tests. Retrieve relevant Caipira history when available, but judge current code and behavior directly.
2. Check each acceptance criterion and existing behavior the change could disturb. Examine meaningful edge cases, permissions, external requests, and stored data if touched. Reproduce the reported bug and run focused checks or a practical manual scenario where possible.
3. Report findings first, ordered by severity. For each, give a path and line, triggering case, impact, evidence, and a concrete correction. Then state checks run, criteria covered, and anything unverified.
4. If no findings are supported, say so with coverage limits. Do not claim the change is bug-free or edit code unless fixes were requested.
