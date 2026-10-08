---
name: sdd-implement-simple
description: Implement a bounded task spec in a script, utility, or compact app and verify its behavior. Use for simple code without a service or game pipeline.
---

# Implement simple code

1. Read the task spec, project rules, and affected code. Retrieve relevant Caipira history when available; verify current file facts. Resolve a blocked spec or material contradiction before editing.
2. Make the smallest coherent change for the acceptance criteria, preserving existing behavior outside the stated scope. Check permissions, external requests, and stored data if touched.
3. Run the relevant existing checks and exercise each criterion. For a bug, reproduce the original failure before and after the fix when feasible. Add a focused regression test when it will catch a credible future break; a manual scenario is valid when automation has no useful setup.
4. Record changed paths, spec deviations, checks and results, and any unverified behavior in the work summary or project memory. Claim only results observed directly.
