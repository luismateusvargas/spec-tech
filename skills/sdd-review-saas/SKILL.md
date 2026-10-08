---
name: sdd-review-saas
description: Independently review a SaaS implementation against its task spec, constitution, contracts, and regression risks across services and data.
---

# Review a SaaS change

1. Identify the intended diff; read the Markdown task spec and its YAML project, constitution, and relevant domain definitions, plus linked contracts, affected services, callers, tests, and migrations. Retrieve relevant Caipira history when available; verify current implementation independently of the implementer's summary. Flag work that relied on an unresolved required field.
2. Map each acceptance criterion to code and a check. Inspect authorization and tenant isolation, API compatibility, data integrity, migration behavior, failure paths, and operational signals where affected. Trace changes across service boundaries rather than reading only modified lines.
3. Run relevant focused and integration checks, plus build or static checks that can expose this change's risks. Separate observed failures from untested rollout, production, or load behavior.
4. Report findings first by severity with path and line, trigger, impact, evidence, and correction. State criterion coverage, commands and results, and remaining release checks. If no findings are supported, say so with limits; edit code only if fixes were requested.
