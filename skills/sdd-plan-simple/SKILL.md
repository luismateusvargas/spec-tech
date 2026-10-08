---
name: sdd-plan-simple
description: Plan one bounded change in a script, utility, or compact app as a short task spec for a coding agent. Use for simple code without a service or game pipeline.
---

# Plan simple code

1. Read the user's topic, project rules, relevant code and checks. Retrieve relevant Caipira history when available, then verify current file facts. For a bug, capture the observable failure and expected behavior.
2. Keep one intent and a clear scope boundary. State success and a meaningful failure or edge case in observable terms; place implementation choices in a separate plan section. Check current primary documentation only for version-sensitive claims.
3. Fill the shared [simple task spec](../sdd-shared/templates/task.simple.template.md) as one project file. Name verified target paths, the smallest workable change, and a check for each acceptance criterion. Add permissions, data, or compatibility constraints when this change touches them.
4. Mark unresolved decisions instead of guessing. Check the spec against the user's request and project rules; leave it in draft or blocked status if a decision prevents implementation. Stop at the spec unless coding was also requested.
