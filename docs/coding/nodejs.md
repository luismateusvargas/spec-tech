# Node.js and JavaScript

- Match the project's supported Node.js version, module system (ESM or CommonJS), package manager, and formatter. Do not mix module systems or lockfiles without a reason.
- Keep modules cohesive and exports deliberate. Use `const` by default, `let` when reassignment is needed, and avoid `var` in new code.
- Use `async`/`await` for asynchronous flows. Await or explicitly handle every promise; propagate failures with context and avoid unhandled rejections.
- Prefer nonblocking APIs in server request paths. Bound concurrency and timeouts for network, filesystem, and subprocess work; clean up timers, streams, and listeners.
- Validate untrusted input at the boundary. Use parameterized database APIs and argument arrays for subprocesses; avoid shell interpolation and `eval`.
- Keep configuration in the project's established mechanism. Do not expose secrets in errors or logs; use structured logs with request context when available.
- Keep state scoped to requests or modules deliberately. Avoid hidden mutable globals and circular dependencies.
- Write tests for observable behavior, including asynchronous errors and cleanup. Run the configured formatter, linter, tests, and build checks.
