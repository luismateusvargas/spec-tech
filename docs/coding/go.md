# Go

- Use the Go version in `go.mod` and the repository's tooling. Run `gofmt`; use `goimports` if configured. Keep packages focused and avoid unnecessary exported symbols.
- Name packages briefly and clearly, without stutter. Use Go naming conventions: exported identifiers start with capitals; initialisms stay consistent (`ID`, `URL`).
- Accept interfaces where they reduce coupling; return concrete types unless an interface is part of the API. Keep interfaces small and near their consumers.
- Check errors promptly and wrap with useful context using `%w` when callers may need `errors.Is` or `errors.As`. Do not use `panic` for ordinary failures.
- Pass `context.Context` as the first parameter for cancelable work; propagate deadlines and cancellation. Never store a request context in a long-lived struct.
- Make goroutine ownership and shutdown explicit. Avoid data races, unbounded goroutines, and channels when a simpler synchronization method fits.
- Close resources with `defer` once acquisition succeeds. Validate input at boundaries and use parameterized database calls.
- Write focused table-driven tests when cases share setup. Run targeted `go test`; run race checks for changed concurrent code when feasible.
