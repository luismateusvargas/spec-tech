# Rust

- Use the edition and minimum supported Rust version configured by the crate. Run `cargo fmt` and follow the repository's Clippy policy.
- Model invariants with types and ownership. Prefer borrowing when it avoids unnecessary ownership transfer, but use owned data when it simplifies lifetimes or APIs.
- Keep modules focused and visibility narrow. Use `snake_case` for modules and functions, `CamelCase` for types and traits, and `SCREAMING_SNAKE_CASE` for constants.
- Return `Result` for recoverable failures and add context at boundaries. Avoid `unwrap` and `expect` on untrusted or routine failure paths; reserve `panic!` for broken invariants.
- Prefer enums and pattern matching for distinct states. Avoid invalid states represented by loosely related booleans or optional fields.
- Keep `unsafe` small, justified, and documented with its safety invariants. Prefer safe library APIs whenever possible.
- For async and concurrent code, make cancellation, task ownership, and shared-state synchronization explicit. Do not block an async executor with synchronous work.
- Test public behavior, edge cases, and error paths. Run targeted tests, formatting, and Clippy or other configured checks.
