---
name: sdd-orchestrate-saas
description: Bootstrap or refresh YAML project, constitution, and domain definitions for a hosted multi-user SaaS or service.
---

# Orchestrate a SaaS project

1. Read the [questionnaire](../sdd-shared/templates/orchestrator.questionnaire.md), then inspect the project root, instructions, existing definitions and plans, services, APIs, data stores, identity, CI, migrations, tests, and deployment. Consult Caipira for prior user decisions. Preserve established decisions and verify repository facts.
2. Reconcile in-scope decisions and open questions from plans, memory, and the current conversation before interviewing the user. Carry forward confirmed answers with their provenance; distinguish chosen target behavior from current implementation. Ask the user only for decisions still open. If neither the user nor evidence resolves a field, propose a focused search where it could establish the fact. Never guess. Omit inapplicable optional fields. Keep unresolved required fields as `null` with a matching `open_decisions` entry and `status: blocked`; never label such a definition ready.
3. Create or refresh full YAML files using the [constitution](../sdd-shared/templates/constitution.template.yaml), [SaaS project](../sdd-shared/templates/project.saas.template.yaml), and [SaaS domain](../sdd-shared/templates/domain.saas.template.yaml) templates. Create domain files only for real bounded domains; preserve existing YAML domains and reconcile any older Markdown domain spec into YAML without leaving two active sources of truth. Keep project-wide rules in the constitution, system boundaries in the project definition, and observable contracts in domain specs. Version changed definitions; do not silently override a prior rule.
4. Consult relevant items in the [security baseline](../sdd-shared/templates/security.constitution.base.yaml) only when applicable; verify its versions and blanket rules. Check current primary sources when security, framework, or provider behavior affects a decision. Record URLs and access dates.
5. Validate YAML syntax, required fields, references, and consistency across definitions. Report file paths, adopted decisions, and unresolved questions. Ask for remaining answers before dependent planning when a required decision is blocked.
