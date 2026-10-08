# C#

- Use the target framework, language version, `.editorconfig`, and nullable settings already configured. Follow the repository's naming and file layout conventions.
- Keep types cohesive and public APIs deliberate. Use `PascalCase` for public types and members, `camelCase` for parameters and locals, and the project's convention for private fields.
- Prefer clear dependency injection through constructors for long-lived dependencies. Avoid service locators and mutable global state.
- Keep nullability accurate; check inputs at boundaries. Use records for value-like data when appropriate, and classes for identity and mutable behavior.
- Use `async`/`await` for asynchronous I/O; avoid `.Result` and `.Wait()` in async flows. Pass `CancellationToken` through cancelable operations.
- Dispose owned resources with `using`/`await using` or an explicit lifetime. Distinguish ownership when accepting streams or other disposable values.
- Catch specific exceptions where you can recover or add context. Do not hide exceptions; use structured logging without sensitive values.
- Test behavior and failure paths with the project's test framework. Run formatting, analyzers, build, and targeted tests configured by the solution.
