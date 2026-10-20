---
name: javascript-dev
description: Use automatically for JavaScript work in browser, Node.js, or mixed-language projects, including planning, implementation, review, and refactoring of .js, .mjs, .cjs, and .jsx files. Apply these rules to build modular, reliable APIs and data flows.
---

# JavaScript development reference

Use this skill for JavaScript files and JavaScript runtime behavior. For TypeScript source files, use the separate `typescript-dev` skill. Apply all rules here to JavaScript work.

## Establish the runtime and project context

- Read repository instructions and relevant language guides before editing. Check supported browser or Node.js versions, ESM or CommonJS configuration, package manager, dependencies, API contracts, module layout, callers, and nearby tests.
- Use the project's runtime and configured tools. Do not mix module systems, package managers, lockfiles, or browser and Node.js APIs without a concrete reason.
- Preserve behavior, public contracts, data formats, and performance unless the request calls for a change. Keep refactors scoped and explain meaningful tradeoffs.

## Design cohesive modules and services

- Organize modules around cohesive responsibilities. Keep implementation details private and expose a deliberate, small public API.
- Before adding an abstraction, inspect existing modules and call sites. Consolidate repeated logic when occurrences have the same meaning and are expected to change together. Two or more genuine copies are candidates for extraction; similar-looking code with different responsibilities is not automatically duplication.
- Put shared behavior in the narrowest appropriate module. Use a `utils` module only for genuinely general behavior; keep domain-specific logic with its domain. Avoid catch-all utilities, circular dependencies, and hidden mutable globals.
- Prefer small functions, explicit data flow, and clear dependency direction. Use classes when state or a stable interface needs an object; prefer functions for stateless behavior.
- Services must not depend directly on other services. Inject infrastructure through narrow, documented structural interfaces, and make resource ownership and dependency lifetimes explicit.
- Keep constructors simple and free of hidden I/O, network access, or runtime type checks. Use shared state only when its concurrency behavior is clear.

## Manage APIs and data boundaries

- Encapsulate each external API integration in a focused client or adapter. Centralize base URL, authentication, headers, timeouts, retries, pagination, rate limiting, serialization, and transport error handling for that API.
- Keep transport details out of domain logic. Map request and response DTOs at the boundary and expose stable operations to callers.
- Treat network responses, user input, environment variables, storage, and parsed JSON as untrusted. Validate required fields and ranges before domain use; do not assume a successful HTTP status means a valid payload.
- Use the project's runtime schema validator when available. Otherwise, write small parsing and narrowing functions. Do not cast or trust the result of `JSON.parse` without validation.
- Set finite timeouts for network and subprocess work. Retry only bounded, safe-to-repeat operations; honor cancellation and `Retry-After` where applicable. Do not retry non-idempotent requests without an idempotency strategy.
- Keep secrets out of source, client-visible code, errors, and logs. Use parameterized database APIs and argument arrays for subprocesses; avoid shell interpolation and `eval`.
- Normalize data at boundaries. Preserve distinctions between missing, `null`, and invalid values; handle dates, numeric precision, encodings, and time zones explicitly when the domain depends on them.
- Avoid mutating shared request, response, or domain objects implicitly. Use explicit transformation functions and document intentional mutation.

## Handle failures predictably

- Throw `Error` instances, not strings or arbitrary values. Define focused error classes for domain and boundary failures, with stable names or codes and safe messages.
- Catch only errors that the current layer can recover from or translate. At API, database, filesystem, and framework boundaries, map known failures into stable application errors and preserve the original cause where supported.
- Do not expose raw framework, database, or provider errors through public service APIs. Do not silently discard errors, broadly catch `unknown` failures, or catch only to rethrow unchanged.
- Await or explicitly handle every promise. Attach useful context when propagating failures; do not leave rejected promises unhandled.
- Keep secrets and sensitive payloads out of error messages and logs. Use structured logs with request or operation context where available.

## Tests, documentation, and checks

- Keep focused unit tests in the same source file as the implementation. If the test runner does not discover colocated tests by default, configure it to do so. Use the project's test runner and write tests in fixture/setup → actual → expected → assertion order.
- Prefer assertions on complete objects or schemas over checking fields one by one. Keep fixtures generic and reusable, and test success, validation failures, asynchronous errors, cancellation, and resource cleanup.
- Add concise JSDoc to every public module API, function, class, and method. Document parameter and return types with `@param` and `@returns`; describe expected failures where applicable. Define reusable structured shapes with `@typedef`. Do not include usage examples in API doc comments.
- Use `const` by default, `let` only when reassignment is needed, and do not use `var` in new code. Use context managers or `try`/`finally` cleanup patterns for streams, timers, listeners, locks, and other resources.
- Run relevant tests, the configured formatter, and linter for JavaScript changes. Treat warnings as blocking. For projects that use TypeScript tooling to check JavaScript, keep `checkJs` and strict checking enabled rather than weakening them to pass.
- In asynchronous code, use `async`/`await` where it clarifies flow, avoid blocking server request paths, bound concurrency, and make cancellation and cleanup explicit.

