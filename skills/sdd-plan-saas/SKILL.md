---
name: sdd-plan-saas
description: Plan a SaaS feature or bug across APIs, services, data, and operations as one reviewable task spec for a coding agent.
---

# Plan a SaaS change

1. Read the topic, YAML constitution, project and relevant domain definitions, affected code and tests. Retrieve relevant Caipira history when available; verify current interfaces and callers. Identify the user journey and impacted services, tenants, data, and operations. Treat unresolved required fields as blockers for dependent decisions.
2. Apply the [scope guide](../sdd-shared/templates/scope-guide.md) to split a broad topic into bounded, independently verifiable outcomes before writing. Separate observable requirements from design decisions in each spec. Include negative and authorization cases where relevant; preserve existing contracts unless a change is explicit. Check current primary sources for time-sensitive provider, framework, or security decisions.
3. Fill the shared [SaaS task spec](../sdd-shared/templates/task.saas.template.md) as one project file per outcome. Map each acceptance criterion to verification. State dependencies between specs; order cross-service work by dependency within each spec. Specify migration, compatibility, rollout, and rollback only when affected. Use verified paths and concrete interface decisions, and list every file the change writes in the header's `Target files:` line. List the resulting specs and dependency order for a multi-spec request.
4. Mark unresolved contract, policy, or data decisions as blockers; set `Status: ready` only when none remain. Check the spec against the constitution and existing behavior. Stop at the spec unless coding was also requested.
