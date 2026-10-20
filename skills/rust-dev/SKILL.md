---
name: rust-dev
description: Use automatically for tasks that plan, implement, review, or refactor Rust code, including Rust crates in a mixed-language project. Apply the repository's conventions while improving modularity, type safety, and maintainability.
---

# Rust development reference

Use this skill whenever the task involves Rust. It is a reference for planning, implementation, review, and refactoring. Apply all rules in this skill to Rust work.

## Establish local rules first

- Read the repository's `AGENTS.md` and relevant Rust guide before editing. Check crate manifests, toolchain, lint configuration, module layout, callers, and nearby tests. Use project configuration to select supported versions and exact check commands; the rules in this skill remain mandatory.
- Preserve behavior, public contracts, data formats, and performance unless the request calls for a change. Keep refactors scoped and explain meaningful tradeoffs.

## Design cohesive modules

- Organize code around cohesive responsibilities. Keep implementation details in private modules and expose a deliberate, simple API from crate roots with `pub use` where that improves use without widening visibility unnecessarily.
- Before adding an abstraction, inspect existing modules and call sites. Consolidate repeated logic when occurrences have the same meaning and are expected to change together. Two or more genuine copies are candidates for extraction; similar-looking code with different responsibilities is not automatically duplication.
- Put shared behavior in the narrowest appropriate owner. Use a `utils` crate only when it exists or the project intentionally provides one, and when the function is general enough to belong there. Domain-specific logic belongs with its domain; avoid a catch-all utility layer and dependency cycles.
- Prefer small functions, short focused modules, explicit data flow, and clear dependency direction. Do not split code into modules solely to reduce line count.
- Keep visibility narrow. Re-export stable user-facing items at a crate root when that makes the public import path clearer; keep internal structure private.

## Model valid states and boundaries

- Use enums for alternatives and state transitions that should be exhaustive. Use newtypes for primitive values whose meaning or constraints differ, especially at important boundaries.
- Make invalid values difficult to construct. Validate in constructors or conversion methods and return `Result<Self, Error>` when validation can fail.
- Prefer small, single-purpose traits when an abstraction enables real substitution or decouples a boundary. Accept trait bounds or references where useful, but do not add a trait to every function or force generic designs that make APIs harder to use.
- Choose generics, `impl Trait`, or trait objects according to the abstraction boundary and object-safety needs. Services must follow the no-trait-object rule below.
- Use ownership to clarify lifetimes: pass values when the caller is transferring ownership, borrow for temporary views, and use `String` or `Arc`/`Rc` when a value must persist or truly has shared ownership. Keep bindings immutable unless mutation is needed locally.

## Errors and production paths

- Return `Result` for recoverable failures, propagate with `?`, and add context where the layer understands the operation. Avoid `unwrap`, `expect`, and `panic!` on routine production failure paths.
- Use `anyhow::Result` for services and repositories. Create domain errors with `thiserror`. Convert domain errors manually; never implement `From` for domain-error conversions.
- Keep `unsafe` small and document its safety invariants. Make async cancellation, task ownership, and shared-state synchronization explicit; do not block an async executor with synchronous work.

## Tests, docs, and checks

- Write tests in the same file as the source. Use `pretty_assertions::assert_eq`, fixtures, and the `fixture` / `actual` / `expected` pattern. Keep tests concise and fixtures generic and reusable. Prefer `new`, `Default`, and `derive_setters::Setters` to construct actual values, expected values, and fixtures; avoid struct literals and `with_*` constructors for those setups. Assert on complete objects when practical, use `assert_eq!` for equality and `assert!` for boolean conditions. Test functions may use `unwrap()`; fixture helpers should return `anyhow::Result`. Use `expect` instead of `panic!` when an invariant needs a useful message. Treat snapshot acceptance as a reviewable change.
- Write concise `///` documentation for every public method, function, struct, enum, and trait. Include `# Arguments` and `# Errors` where applicable. Do not include code examples.
- Always verify Rust changes with tests and linting. Run crate-specific tests with `cargo insta test --accept`, formatting, and Clippy. Clippy warnings are unacceptable. Do not run `cargo build --release` for routine verification; use `cargo check`, tests, or a debug build. Report checks that could not run.

## Services and domain types

Apply these clean-architecture and domain-type rules to every Rust project:

- Services must not depend directly on other services. Services may depend on infrastructure abstractions.
- A service may take at most one generic type parameter for infrastructure. Store infrastructure in `Arc<T>`. For a simple service with one dependency, use a tuple struct.
- `new()` constructors must have no type bounds. Put bounds only on methods that need them. Compose multiple infrastructure traits with `+` rather than adding a type parameter for each dependency.
- Do not use trait objects (`dyn Trait`) in services. Use concrete types and generics.
- Use `derive_setters` on domain structs, including the `strip_option` and `into` attributes.

