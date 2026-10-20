---
name: typescript-dev
description: Use automatically for TypeScript work in browser, Node.js, or mixed-language projects, including planning, implementation, review, and refactoring of .ts and .tsx files. Apply these rules to build modular, typed APIs and validated data flows.
---

# TypeScript development reference

Use this skill for TypeScript source files and TypeScript-specific contracts. For plain JavaScript files and runtime behavior, use the separate `javascript-dev` skill. Apply all rules here to TypeScript work.

## Establish the runtime and project context

- Read repository instructions and relevant language guides before editing. Check the supported TypeScript and browser or Node.js versions, `tsconfig`, module system, package manager, API contracts, module layout, callers, and nearby tests.
- Keep strict compiler settings enabled. Use the configured runtime and tools; do not mix module systems, package managers, lockfiles, or browser and Node.js APIs without a concrete reason.
- Preserve behavior, public contracts, data formats, and performance unless the request calls for a change. Keep refactors scoped and explain meaningful tradeoffs.

## Design cohesive modules and services

- Organize modules around cohesive responsibilities. Keep implementation details private and export a deliberate, small public API with stable types.
- Before adding an abstraction, inspect existing modules and call sites. Consolidate repeated logic when occurrences have the same meaning and are expected to change together. Two or more genuine copies are candidates for extraction; similar-looking code with different responsibilities is not automatically duplication.
- Put shared behavior in the narrowest appropriate module. Use a `utils` module only for genuinely general behavior; keep domain-specific logic with its domain. Avoid catch-all utilities, circular dependencies, and hidden mutable globals.
- Prefer small functions, explicit data flow, and clear dependency direction. Use classes when state or a stable interface needs an object; prefer functions for stateless behavior.
- Services must not depend directly on other services. Define narrow infrastructure contracts with interfaces or structural types, inject dependencies explicitly, and make resource ownership and lifetimes clear.
- Keep each service to at most one generic infrastructure type parameter. Compose multiple infrastructure capabilities into a focused interface instead of adding a type parameter for each dependency.
- Keep constructors simple and free of hidden I/O, network access, and unnecessary generic constraints. Keep type bounds on the smallest functions that need them.

## Model types and validate data

- Use strict types throughout public APIs and nontrivial internal logic. Avoid `any`, non-null assertions, and broad casts. Use `unknown` at trust boundaries and narrow it through validation.
- Model alternatives and state transitions with discriminated unions, literal types, and enums. Use branded or wrapper types for primitive values with distinct meanings where they prevent real mistakes.
- Preserve nullability and optionality accurately. Do not use optional fields, nullable fields, or boolean flags to represent states that should be an explicit union.
- Remember that TypeScript types are erased at runtime. Validate network responses, user input, environment variables, storage, and parsed JSON with the project's runtime schema validator. If none is available, write a small parser that accepts `unknown` and returns a validated type. Never cast parsed JSON directly to an interface.
- Use typed request and response DTOs for APIs, then validate response payloads at runtime before passing them to domain code. Map transport DTOs into domain types at the boundary.
- Avoid mutating shared data implicitly. Use explicit transformations and immutable update patterns where practical; document intentional mutation.
- Prefer small generic helpers that remove real duplication. Avoid elaborate conditional or mapped type machinery that obscures runtime values or makes diagnostics difficult.

## Manage APIs and asynchronous work

- Encapsulate each external API integration in a focused client or adapter. Centralize base URL, authentication, headers, timeouts, retries, pagination, rate limiting, serialization, and transport error handling for that API.
- Keep transport details out of domain logic. Expose stable operations and typed contracts to callers; keep API version changes at the adapter boundary.
- Set finite timeouts for network and subprocess work. Retry only bounded, safe-to-repeat operations; honor cancellation and `Retry-After` where applicable. Do not retry non-idempotent requests without an idempotency strategy.
- Make promise rejection and cancellation explicit. Await or handle every promise, propagate failures with useful context, bound concurrency, and clean up listeners, timers, streams, and request resources.
- Keep secrets out of source, client-visible code, errors, and logs. Use parameterized database APIs and argument arrays for subprocesses; avoid shell interpolation and `eval`.

## Handle failures predictably

- Throw `Error` instances, not strings or arbitrary values. Define focused error classes or discriminated error results for domain, validation, and boundary failures, with stable names or codes and safe messages.
- Catch only errors the current layer can recover from or translate. At API, database, filesystem, and framework boundaries, map known failures into stable application errors and preserve the original cause where supported.
- Do not expose raw framework, database, or provider errors through public service APIs. Do not silently discard errors, broadly catch `unknown` failures, or catch only to rethrow unchanged.
- Keep error types truthful to runtime behavior. Do not claim a function cannot fail when it can reject or throw; document expected failures at public boundaries.
- Keep secrets and sensitive payloads out of errors and logs. Use structured logs with request or operation context where available.

## Tests, documentation, and checks

- Keep focused unit tests in the same source file as the implementation. If the test runner does not discover colocated tests by default, configure it to do so. Use the project's test runner and write tests in fixture/setup → actual → expected → assertion order.
- Prefer assertions on complete typed objects or schemas over checking fields one by one. Keep fixtures generic and reusable, and test success, runtime validation failures, asynchronous errors, cancellation, and resource cleanup.
- Add concise TSDoc to every exported module API, function, class, method, and public type. Document parameters, return values, and errors where applicable. Do not include usage examples in API doc comments.
- Use `import type` for imports used only as types when supported by the project's module configuration. Preserve inference for local values and annotate public boundaries and complex returns where it clarifies the contract.
- Run relevant tests, `tsc --noEmit` or the configured type check, formatter, and linter for TypeScript changes. Treat compiler errors, warnings, and lint violations as blocking. Never weaken strictness or hide errors with casts to make checks pass.
- Use context managers or `try`/`finally` cleanup patterns for streams, timers, listeners, locks, and other resources. In server paths, avoid blocking work and make request cancellation explicit.

