# Scope a task spec by risk

Every task spec needs an outcome, scope boundary, observable acceptance criteria, a workable plan, and verification. Add detail when the cost of a wrong decision grows; project size alone is not the gate.

| Situation | Add to the core spec |
| --- | --- |
| Small local script or one-file utility | Target site or input versions, permissions/data touched, one success and failure scenario, a manual or automated check. |
| Multi-user service or SaaS | API and data contracts, authorization and privacy, migrations, backward compatibility, failure handling, operational checks, rollout and rollback where affected. |
| Large game or cross-system product | System ownership and interfaces, target platforms and hardware budgets, save/content compatibility, performance and memory limits, build/assets pipeline, multiplayer behavior if applicable, QA matrix and release gates. |

For any tier, add the relevant items when triggered by risk: external dependencies, accessibility, localization, licensing, compliance, abuse cases, observability, or incident recovery. Omit unrelated fields rather than filling them with invented detail. Use the project's existing standards and tools.

## Split broad requests before writing task specs

List the requested outcomes and their affected components. Give each independently implementable and verifiable outcome its own task spec, with explicit dependencies and an acceptance check. Separate backend behavior, frontend behavior, and user interface work when each can be completed and checked on its own. For example, backend logging, frontend logging, and a browser menu for viewing logs are three specs; omit the frontend logging spec when that component does not exist. Do not create a spec for a nonexistent component or split tightly coupled changes that cannot produce a useful verified result separately.

Keep each spec small enough for one implementation pass: a bounded set of paths and one primary outcome. If the target paths, criteria, or verification span unrelated subsystems, split again. Present the spec set and dependency order so no requested outcome disappears. Do not hide later work as an unchecked step inside a large first spec.
