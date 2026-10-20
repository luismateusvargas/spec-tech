---
name: sdd-plan-game
description: Plan a large or AAA game feature as one task spec covering player behavior, engine and content boundaries, platforms, and relevant verification.
---

# Plan a game feature

1. Read the topic, YAML constitution, project and relevant domain definitions, linked designs, affected code, assets, builds, and tests. Retrieve relevant Caipira history when available; verify current engine, platform, save, and network facts. Treat unresolved required fields as blockers for dependent decisions.
2. Apply the [scope guide](../sdd-shared/templates/scope-guide.md) to split a broad topic into bounded, independently verifiable slices before writing. Write player-facing behavior and failure cases separately from technical design in each spec. Include content ownership, platform, performance, save, multiplayer, and accessibility constraints only when the slice touches them; use measured budgets or mark them open.
3. Fill the shared [game task spec](../sdd-shared/templates/task.game.template.md) as one project file per slice. Identify verified systems and asset paths, dependencies, acceptance checks, and a practical target-device or build test matrix. List every file the slice writes in the header's `Target files:` line. Check version-sensitive engine and platform guidance in current primary sources. List the resulting specs and dependency order for a multi-spec request.
4. Flag decisions that block implementation or validation; set `Status: ready` only when none remain. Check the spec against the constitution and existing content contracts. Stop at the spec unless coding was also requested.
