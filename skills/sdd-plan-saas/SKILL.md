---
name: sdd-plan-saas
description: Plan a SaaS feature or bug across APIs, services, data, and operations as one reviewable task spec for a coding agent.
---

# Plan a SaaS change

1. Read the topic, YAML constitution, project and relevant domain definitions, affected code and tests. Retrieve relevant Caipira history when available; verify current interfaces and callers. Identify the user journey and impacted services, tenants, data, and operations. Treat unresolved required fields as blockers for dependent decisions.
2. Scope one independently verifiable outcome. Separate observable requirements from design decisions. Include negative and authorization cases where relevant; preserve existing contracts unless a change is explicit. Check current primary sources for time-sensitive provider, framework, or security decisions.
3. Fill the shared [SaaS task spec](../sdd-shared/templates/task.saas.template.md) as one project file. Map each acceptance criterion to verification. Order cross-service work by dependency; specify migration, compatibility, rollout, and rollback only when affected. Use verified paths and concrete interface decisions.
4. Mark unresolved contract, policy, or data decisions as blockers. Check the spec against the constitution and existing behavior. Stop at the spec unless coding was also requested.
