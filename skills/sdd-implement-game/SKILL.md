---
name: sdd-implement-game
description: Implement a large or AAA game task spec across engine code and content, then verify affected platforms and gameplay behavior.
---

# Implement a game feature

1. Read the Markdown task spec and its YAML project, constitution, and relevant domain definitions, plus linked designs, affected code, assets, builds, and tests. Retrieve relevant Caipira history when available; verify engine, platform, save, and network assumptions. Resolve required-field blockers before dependent edits.
2. Follow the [project-local Git checkpoint workflow](../sdd-shared/templates/git-checkpoints.md): commit the reviewed starting state before the first implementation edit or SDD engine `begin_task` call, then implement a coherent playable slice in dependency order. When using the SDD engine, follow the [engine protocol](../sdd-shared/templates/engine-protocol.md) with `tier: "game"`, keeping `HEAD` at the baseline commit until `finish_task` returns. Preserve asset references, content ownership, save compatibility, and replicated behavior where affected. Keep code and content changes within the stated feature boundary.
3. Check each acceptance criterion through the available automated, editor, in-game, build, and target-device paths. Measure performance against stated budgets when the feature touches them. Record any platform or device checks that cannot run; do not claim they passed.
4. Follow the checkpoint workflow to inspect and commit the completed implementation after checks (and after `finish_task` when using the SDD engine). Record both commit SHAs, changed systems and assets, spec deviations, checks and results, and unverified release risks in the work summary or project memory. Update the spec for authorized design changes; do not silently lower budgets or remove criteria.
