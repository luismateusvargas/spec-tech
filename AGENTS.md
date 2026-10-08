# Coding instructions

- Follow the user's request and the project's existing architecture, configuration, and conventions. Check the affected code and tests before editing; keep changes focused.
- Read [the common coding guide](docs/coding/common.md) when implementing or reviewing code. Read only the relevant language guide from [the coding guide index](docs/coding/README.md). For mixed-language changes, read each affected language guide.
- Use [Caipira](docs/caipira.md) for prior decisions and cross-agent memory: search before re-deriving relevant history, and record settled decisions or discoveries with file evidence. Treat a fact flagged for review as needing fresh verification.
- Treat the guides as defaults. Explicit project rules, configured formatters and linters, supported language versions, and local patterns take precedence. Do not reformat unrelated code to satisfy a guide.
- Verify changed behavior with the smallest meaningful tests and configured checks. Report what ran and any remaining limitations.
- Keep secrets and generated artifacts out of changes unless the task explicitly requires them.
