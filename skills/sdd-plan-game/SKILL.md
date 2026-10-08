---
name: sdd-plan-game
description: Plan a large or AAA game feature as one task spec covering player behavior, engine and content boundaries, platforms, and relevant verification.
---

# Plan a game feature

1. Read the topic, YAML constitution, project and relevant domain definitions, linked designs, affected code, assets, builds, and tests. Retrieve relevant Caipira history when available; verify current engine, platform, save, and network facts. Treat unresolved required fields as blockers for dependent decisions.
2. Scope a playable, independently verifiable slice. Write player-facing behavior and failure cases separately from technical design. Include content ownership, platform, performance, save, multiplayer, and accessibility constraints only when the feature touches them; use measured budgets or mark them open.
3. Fill the shared [game task spec](../sdd-shared/templates/task.game.template.md) as one project file. Identify verified systems and asset paths, dependencies, acceptance checks, and a practical target-device or build test matrix. Check version-sensitive engine and platform guidance in current primary sources.
4. Flag decisions that block implementation or validation. Check the spec against the constitution and existing content contracts. Stop at the spec unless coding was also requested.
