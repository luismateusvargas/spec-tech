---
name: sdd-review-saas
description: Independently review a SaaS implementation against its task spec, constitution, contracts, and regression risks across services and data.
---

# Review a SaaS change

1. Identify the intended diff; read the Markdown task spec and its YAML project, constitution, and relevant domain definitions, plus linked contracts, affected services, callers, tests, and migrations. Retrieve relevant Caipira history when available; verify current implementation independently of the implementer's summary. Flag work that relied on an unresolved required field.
2. Map each acceptance criterion to code and a check. Inspect authorization and tenant isolation, API compatibility, data integrity, migration behavior, failure paths, and operational signals where affected. Trace changes across service boundaries rather than reading only modified lines.
3. Run relevant focused and integration checks, plus build or static checks that can expose this change's risks. Separate observed failures from untested rollout, production, or load behavior.
4. Report findings first by severity with path and line, trigger, impact, evidence, and correction. State criterion coverage, commands and results, and remaining release checks. If a criterion fails or a regression is confirmed, create a separate [counter-plan](../sdd-shared/templates/review.counter-plan.template.md) beside the original task spec, following the project's naming convention (otherwise `<task-stem>.counter-plan.md`). Tie every correction to a finding and its reproducing evidence; include only the smallest changes and checks needed to fix those failures, preserving contracts and data boundaries. Mark blockers explicitly and do not turn unverified behavior into a repair task. Report its path. If no findings are supported, say so with limits; edit code only if fixes were requested.
5. Check the baseline and completion SHAs, then follow the [project-local Git checkpoint workflow](../sdd-shared/templates/git-checkpoints.md). On fully verified approval, tag the reviewed completion commit locally and report its name and SHA. Leave failures or incomplete verification untagged.
