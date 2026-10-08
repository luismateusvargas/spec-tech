---
name: sdd-review-game
description: Independently review a large or AAA game feature against its task spec and regression risks in gameplay, content, builds, and target platforms.
---

# Review a game feature

1. Identify the intended diff; read the Markdown task spec and its YAML project, constitution, and relevant domain definitions, plus linked designs, changed code and assets, affected systems, and tests. Retrieve relevant Caipira history when available; verify current engine and platform facts independently. Flag work that relied on an unresolved required field.
2. Map each acceptance criterion to implementation and evidence. Inspect gameplay state, asset references, save or content compatibility, replication, accessibility, and frame or memory budgets where affected. Follow integration paths beyond changed files.
3. Run relevant automated, editor, build or cook, and in-game checks. Use target devices and measurements when available; distinguish them from editor-only or simulated results. Record platform and visual checks that could not run.
4. Report findings first by severity with code or asset location, triggering scenario, impact, evidence, and correction. State criterion and platform coverage plus remaining risks. If no findings are supported, say so with limits; edit code only if fixes were requested.
