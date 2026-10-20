---
name: cpp-dev
description: Use automatically for all C++ planning, implementation, review, and refactoring. Provides foundational rules for modularity, ownership, APIs, errors, data validation, tests, documentation, and quality checks.
---

# C++ development foundation

Use this skill for every task involving C++. For computer vision or AAA game runtime work, also apply the matching `cpp-cv-dev` or `cpp-aaa-dev` skill. Apply all foundational rules here to those tasks as well.

## Establish the project context

- Read repository instructions and the relevant C++ guide before editing. Check the configured C++ standard, compiler, build system, dependency policy, module layout, API contracts, callers, and tests.
- Use the configured language standard and toolchain. Do not silently raise the standard, add dependencies, change public contracts, or reformat unrelated code.
- Preserve behavior, data formats, and performance unless the request calls for a change. Keep work focused and explain meaningful tradeoffs.

## Design cohesive modules and APIs

- Organize code around cohesive components and clear dependency direction. Keep implementation details in source files, private headers, or `detail` namespaces; expose a deliberate, small interface from public headers or C++ modules.
- Keep headers self-contained and avoid leaking internal dependencies. Use wrapper or umbrella headers only when they create a clear public import surface.
- Before adding an abstraction, inspect existing modules and call sites. Consolidate repeated logic when occurrences have the same meaning and are expected to change together. Two or more genuine copies are candidates for extraction; similar-looking code with different responsibilities is not automatically duplication.
- Put shared behavior in the narrowest appropriate library or module. Use `utils` only for genuinely general behavior; keep domain logic with its domain. Avoid catch-all utility libraries, dependency cycles, global mutable state, and unnecessary macros.
- Prefer small cohesive functions, explicit data flow, and stable APIs. Do not split source files or inline code solely to change instruction-cache behavior; source layout alone does not establish runtime locality. Profile before layout-specific optimization.
- Services must not depend directly on other services. Keep service dependencies at infrastructure or domain boundaries and avoid abstractions that do not enable real substitution.
- Use small interfaces where runtime substitution is part of the design. Use templates or concepts where compile-time substitution is appropriate and supported by the configured standard. Return concrete types unless the public API needs an abstraction.

## Model ownership, data, and failures

- Make ownership explicit. Prefer automatic storage and RAII; use `std::unique_ptr` for sole dynamic ownership and `std::shared_ptr` only for genuinely shared ownership. Do not use raw owning pointers.
- Preserve const correctness. Use references and views only while the referenced storage remains alive. Avoid unnecessary copies without sacrificing clear ownership and simple APIs.
- Represent alternatives with `enum class` or tagged types. Use strong wrapper types for primitive values with distinct meanings. Validate at trust boundaries and use factory functions or constructors that cannot produce invalid objects silently.
- Use `std::optional<T>` for an absent value, not as a substitute for categorized failures. Use the project's established error model: exceptions, status types, or `Result<T, E>` such as `std::expected` when the configured C++ version supports it. Do not casually mix error models.
- Map known errors at API, database, filesystem, and framework boundaries. Preserve causes or error codes where callers need them, add useful context, and never silently discard failures. Avoid implicit conversions that obscure error or domain-type boundaries.
- Validate external input before it enters domain logic. Use parameterized database calls; do not build commands or queries with unsafe string interpolation. Keep credentials and sensitive data out of source, errors, and logs.
- For concurrent code, document synchronization and object lifetimes. Avoid unsynchronized shared mutable state and close or release resources on every path.

## Manage external APIs

- Encapsulate each external API integration in a focused client or adapter. Centralize endpoint configuration, authentication, timeouts, serialization, retry policy, pagination, and transport error translation.
- Validate request data before sending and validate response status and payload shape before using returned data. Convert transport DTOs into domain types at the boundary.
- Set finite timeouts and bound concurrency. Retry only safe, bounded operations; do not retry non-idempotent requests without an idempotency strategy.
- Keep transport details out of domain code and secrets out of client-visible data, error messages, and logs.

## Tests, documentation, and checks

- Keep tests in the same component or test target, using focused sidecar test files where the build system requires them. Structure tests as fixture/setup → actual → expected → assertion. Prefer comparing complete values when practical.
- Test behavior, invalid inputs, error paths, ownership and cleanup, and concurrency boundaries relevant to the change. Use the project's configured test framework without adding dependencies unnecessarily.
- Document every public API with `/** ... */` comments. Document parameters and return values with `@param` and `@returns`, and errors with `@throws` where applicable. Keep documentation concise and omit code examples.
- Build with the project's warnings enabled and treat compiler and configured tool warnings as errors. Run the relevant tests, formatter, linter, and static checks. Use debug builds for routine verification; reserve release builds for release or performance work. Use sanitizers or static analysis for low-level changes when available.
- Review the final diff for accidental public API changes, unrelated formatting, generated artifacts, secrets, and missing checks. Report checks that could not run.

