---
name: sdd-orchestrate-game
description: Bootstrap or refresh YAML project, constitution, and domain definitions for a large or AAA game.
---

# Orchestrate a game project

1. Read the [questionnaire](../sdd-shared/templates/orchestrator.questionnaire.md), then inspect the root, instructions, existing definitions and plans, engine and version, code modules, content pipeline, target platforms, builds, saves, tests, and network model. Consult Caipira for prior user decisions. Preserve established decisions and verify repository facts.
2. Reconcile in-scope decisions and open questions from plans, memory, and the current conversation before interviewing the user. Carry forward confirmed answers with their provenance; distinguish chosen target behavior from current implementation. Ask the user only for decisions still open. If neither the user nor evidence resolves a field, propose a focused search where it could establish the fact. Never guess budgets or supported platforms. Omit inapplicable optional fields. Keep unresolved required fields as `null` with a matching `open_decisions` entry and `status: blocked`.
3. Create or refresh full YAML files using the [constitution](../sdd-shared/templates/constitution.template.yaml), [game project](../sdd-shared/templates/project.game.template.yaml), and [game domain](../sdd-shared/templates/domain.game.template.yaml) templates. Create domain files only for real gameplay or engine/content boundaries; preserve existing YAML domains and reconcile any older Markdown domain spec into YAML without leaving two active sources of truth. Link designs rather than copying them. Keep project-wide rules in the constitution, system boundaries in the project definition, and observable contracts in domain specs. Version changed definitions; do not silently override a prior rule.
4. Verify engine and platform guidance in current primary sources when version-sensitive. Record URLs and access dates. Include save/content compatibility, multiplayer, live operations, localization, and accessibility only where applicable.
5. Validate YAML syntax, required fields, references, and consistency across definitions. Report file paths, adopted decisions, and unresolved questions. Ask for remaining answers before dependent planning when a required decision is blocked.
