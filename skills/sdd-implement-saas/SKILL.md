---
name: sdd-implement-saas
description: Implement a SaaS task spec across services, APIs, and data while preserving contracts and verifying affected behavior. Use for hosted multi-user software.
---

# Implement a SaaS change

1. Read the Markdown task spec and its YAML project, constitution, and relevant domain definitions, plus linked contracts, affected code and tests. Retrieve relevant Caipira history when available; verify current interfaces, callers, and deployment assumptions. Resolve required-field blockers or material plan drift before dependent edits.
2. Follow the [project-local Git checkpoint workflow](../sdd-shared/templates/git-checkpoints.md): commit the reviewed starting state before the first implementation edit or SDD engine `begin_task` call, then implement in dependency order with project conventions. When using the SDD engine, follow the [engine protocol](../sdd-shared/templates/engine-protocol.md) with `tier: "saas"`, keeping `HEAD` at the baseline commit until `finish_task` returns. Preserve authorization, tenant boundaries, existing API behavior, and data integrity where affected. Treat migrations and compatibility with deployed clients as explicit work when the spec calls for them.
3. Map each acceptance criterion to a check. Run focused tests and relevant integration, build, and static checks; exercise failure and access-control paths where affected. Verify migration and rollback behavior when changed. Do not infer a production rollout from local test success.
4. Follow the checkpoint workflow to inspect and commit the completed implementation after checks (and after `finish_task` when using the SDD engine). Record both commit SHAs, changed paths, contract or spec decisions, commands and results, and remaining release checks in the work summary or project memory. Update the spec when an authorized design change makes it inaccurate; do not silently relax acceptance criteria.
