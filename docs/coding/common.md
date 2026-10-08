# Common coding guide

## Before editing

- Identify the behavior to change, its callers, tests, and public contracts. Read the nearby code and configuration before choosing a pattern.
- Preserve existing interfaces and data formats unless the task requires changing them. When changing a contract, update its callers and documentation.
- Prefer the smallest clear solution. Avoid speculative abstractions, unrelated cleanup, and new dependencies without a concrete need.

## While coding

- Use descriptive names, small cohesive functions, and modules with a clear responsibility. Prefer explicit data flow over hidden state.
- Validate data at trust boundaries. Handle failures where their meaning is known; propagate or wrap errors with useful context. Never silently discard errors.
- Avoid embedding credentials, unsafe command construction, and sensitive data in logs. Use parameterized APIs for queries and commands.
- Make resource ownership clear: close files, streams, connections, locks, and transactions on every path.
- Add comments for intent, invariants, or non-obvious tradeoffs; keep names and code readable enough that line-by-line narration is unnecessary.

## Verification

- Add or update tests for meaningful behavior changes, especially boundaries and failure paths. Use the project's existing test style.
- Run targeted tests, formatters, linters, and type or build checks relevant to the edit. Fix failures caused by the change.
- Review the diff for accidental formatting churn, generated files, secrets, and changed public behavior. State any check you could not run.
