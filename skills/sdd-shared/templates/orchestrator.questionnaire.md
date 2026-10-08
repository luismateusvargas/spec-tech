# Orchestrator questionnaire

Use this as an interview, not a blank form to dump on the user. First inspect project files, linked plans, and relevant Caipira decisions. Carry forward settled user answers without asking again. Show proposed answers and their sources for confirmation only when the answer is still uncertain or contradicted. A user may answer `unknown` or `not applicable`. Investigate a verifiable unknown or propose a focused search; do not infer a policy or invent a value. Omit optional fields that do not apply. For a required unanswered YAML field, use `null`, add a specific `open_decisions` question, and mark that definition `blocked`. A simple Markdown project spec records the question as open.

## Reconcile decisions before writing

Inventory every in-scope decision and explicit open question in existing plans, specs, project memory, and this conversation. For each, distinguish **confirmed by the user**, **proposed**, **unresolved**, and **superseded**. A plan labeled planning-only can contain a later confirmed decision; check the decision history rather than inferring its status from the plan label. Record confirmed decisions in the relevant YAML field with an `evidence` item naming the user confirmation or memory reference. Keep the plan path separately as design context. Do not turn a proposed target into a claim about current code: name current and planned behavior explicitly.

Reconcile open questions from a linked plan only when they determine a durable project, constitution, or domain definition in the current scope. Leave implementation choices in the plan unless the user explicitly promotes them into a project definition. For an in-scope question, a confirmed answer becomes a sourced definition and an unanswered one remains in `open_decisions` with a field and owner. `draft` describes an unadopted file, while `blocked` means a required answer is missing. A confirmed decision can live in a draft file; implementation can still be planned.

## Shared questions

| Required | Question | YAML destination |
| --- | --- | --- |
| Yes | What is the project for, who uses it, and what is outside its boundary? | `project.purpose`, `project.users` or `project.player_experience`; `constitution.scope` |
| Yes | Which existing project rules must remain binding, and how are exceptions or revisions approved? | `constitution.rules`, `constitution.change_policy` |
| Yes | Which build, test, and review checks gate acceptance? | `constitution.quality_gates` |
| Yes | Which domains or systems are in scope, and where are their existing definitions? | `project.domains` |
| Optional | Which external standards or sources constrain a decision? | Relevant `evidence` or `rules` entry |

## SaaS questions

| Required | Question | YAML destination |
| --- | --- | --- |
| Yes | Which services and deployments exist, and who owns their boundaries? | `project.services`, `project.environments` |
| Yes | How are users identified and authorized? Is data tenant-scoped? | `project.identity`, `project.tenant_model` |
| Yes | Which data stores and major API/event contracts are in scope? | `project.data_stores`, `project.interfaces` |
| Yes, per domain | What observable behavior, including a meaningful failure case, must hold? | `domain.requirements` |
| Optional | What retention, migration, rollout, rollback, SLO, or compliance rules apply? | Project/domain fields or constitution rules when applicable |

## Game questions

| Required | Question | YAML destination |
| --- | --- | --- |
| Yes | What player experience and supported modes define this project? | `project.player_experience`, `project.modes` |
| Yes | Which engine/version, code boundaries, content pipeline, and builds are used? | `project.engine`, `project.systems`, `project.content_pipeline` |
| Yes | Which platforms are supported, and what are their release checks? | `project.platforms`, `project.release_checks` |
| Yes | What save/content compatibility policy applies? | `project.compatibility` |
| Yes, per domain | What observable gameplay or system behavior, including a meaningful failure case, must hold? | `domain.requirements` |
| Optional | What measured performance budgets, online rules, localization, accessibility, or live operations constraints apply? | Project/domain fields or constitution rules when applicable |

## Simple questions

Ask the user for purpose, boundaries, and enduring rules. Confirm observed runtime, entry points, dependencies, permissions, data handling, and run/check commands. Ask optional security or compatibility questions only when the project touches them. Keep the answer in the simple Markdown project spec.
