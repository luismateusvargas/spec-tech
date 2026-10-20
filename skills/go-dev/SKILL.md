---
name: go-dev
description: Use automatically for all Go work, including planning, implementation, review, and refactoring in Go modules or mixed-language projects. Apply these rules to build modular, reliable APIs and services.
---

# Go development reference

Use this skill for every task involving Go. Apply all rules here to Go work.

## Establish the project context

- Read repository instructions and the relevant Go guide before editing. Check the Go version in `go.mod`, module layout, package dependencies, API contracts, configured tooling, callers, and nearby tests.
- Preserve existing behavior, public contracts, data formats, and performance unless the request calls for a change. Keep refactors scoped and explain meaningful tradeoffs.
- Use the configured toolchain and package commands. Format Go code with `gofmt`; use `goimports` when configured. Do not change module versions, dependencies, or generated files without a concrete need.

## Design cohesive packages and services

- Organize packages around cohesive responsibilities and clear dependency direction. Keep packages focused, avoid import cycles, and expose only identifiers that callers need.
- Use short, clear package names without stutter. Use Go naming conventions and keep initialisms consistent (`ID`, `URL`, `HTTP`). Keep implementation details unexported; put internal-only packages under `internal/` when that enforces the intended boundary.
- Before adding an abstraction, inspect existing packages and call sites. Consolidate repeated logic when occurrences have the same meaning and are expected to change together. Two or more genuine copies are candidates for extraction; similar-looking code with different responsibilities is not automatically duplication.
- Put shared behavior in the narrowest appropriate package. Use a `utils` package only for genuinely general behavior; keep domain-specific logic with its domain. Avoid catch-all packages, premature abstractions, and dependency cycles.
- Prefer small functions and clear data flow. Services must not depend directly on other services; they may depend on repositories or infrastructure through small interfaces.
- Define interfaces near the code that consumes them. Keep interfaces small and focused, accept interfaces where they decouple a real boundary, and return concrete types unless an interface is part of the API contract.
- Use generics for algorithms or data structures that genuinely operate across types. Do not use type parameters to abstract service dependencies or make a simple concrete API harder to follow.

## Manage APIs and data boundaries

- Encapsulate external API integrations in focused clients or adapters. Centralize base URL, authentication, headers, timeouts, retries, pagination, rate limiting, serialization, and transport error handling for each integration.
- Reuse configured HTTP clients and their connection pools. Keep transport details out of domain logic; map external request and response DTOs at the boundary and expose stable operations to callers.
- Use `context.Context` as the first parameter for request-scoped or cancelable work. Propagate deadlines and cancellation to HTTP, database, and subprocess operations. Never store a request context in a long-lived struct or pass `nil` as a context.
- Set finite timeouts for network work. Retry only bounded, safe-to-repeat operations; honor server retry guidance where applicable. Do not retry non-idempotent requests without an idempotency strategy.
- Treat HTTP responses, decoded JSON, user input, environment values, and database results as untrusted. Validate required fields, ranges, and state transitions before domain use. Use typed structs instead of passing generic maps through service layers.
- Check HTTP status codes before consuming a response as success. Bound response bodies when appropriate and close every response body. Use parameterized database calls and validate dynamic query inputs.
- Preserve distinctions between omitted, zero, and empty values where the contract requires them. Handle numeric precision, timestamps, time zones, encodings, and nil versus empty slices or maps deliberately.
- Keep credentials and sensitive data out of source, errors, and logs. Use structured logging with operation context; never log secrets or unredacted sensitive payloads.

## Model data and handle errors explicitly

- Use defined types and constants for domain values with restricted meanings. Validate parsed values at constructors or conversion boundaries so invalid state does not spread through the system.
- Return `error` for failures; do not use `panic` for routine or recoverable conditions. Check errors promptly and do not discard them with `_` unless the ignored result is deliberate and documented.
- Create focused domain errors with sentinel values or typed errors when callers need to distinguish failure cases. Wrap lower-level errors with useful context using `%w` when callers may use `errors.Is` or `errors.As`; avoid matching error strings.
- Translate known infrastructure or framework errors at the boundary where their meaning is clear. Preserve the cause and return stable application errors to upstream layers. Do not silently swallow failures or expose raw provider/database details through public service APIs.
- Pass values for small data where that makes ownership clear; use pointers when identity, mutation, or avoiding meaningful copies requires them. Be explicit about shared slice and map backing storage; do not rely on accidental aliasing.
- Acquire resources before deferring cleanup. Close files, response bodies, rows, and transactions on every path; handle cleanup errors when they can affect correctness.

## Concurrency and lifecycle

- Make goroutine ownership, cancellation, and shutdown explicit. Every goroutine must have a clear exit path; avoid unbounded goroutines, leaks, and work that outlives its request without an explicit owner.
- Protect shared mutable state with the narrowest appropriate synchronization. Use channels when they clarify ownership or communication; use a mutex or simpler mechanism when it is clearer.
- Bound worker pools and concurrent external requests. Do not hold locks across blocking I/O unless the invariant requires it.
- Add or update race-focused checks for changed concurrent behavior. Do not claim concurrency safety without considering shared maps, slices, pointers, and cancellation paths.

## Tests, documentation, and checks

- Keep tests beside the package implementation in Go `_test.go` files. Use the standard `testing` package and table-driven tests when cases share setup. Structure each test around fixture/setup → actual → expected → assertion; prefer reusable fixtures and complete value comparisons.
- Test public behavior, boundary validation, error wrapping, cancellation, resource cleanup, and concurrency paths as relevant. Avoid tests that only restate implementation details.
- Add Go doc comments for every exported package-level function, method, type, constant, and variable. Start the comment with the identifier's name and document behavior, arguments, return values, and errors in clear prose. Do not include usage examples in API comments.
- Run targeted tests and configured formatting, lint, vet, and build checks for Go changes. Run `go test ./...` for affected modules when practical and `go test -race` for changed concurrent code. Treat configured lint warnings as blocking and report checks that could not run.

