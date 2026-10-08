# Python

- Use the Python version and formatter configured by the project. Default to four spaces for indentation; never mix tabs and spaces. Keep imports at module scope unless delayed import is needed for a reason.
- Use `snake_case` for modules, functions, variables, and methods; `PascalCase` for classes; `UPPER_SNAKE_CASE` for constants. Keep public names descriptive and avoid shadowing built-ins.
- Organize modules around one responsibility. Put executable entry points behind `if __name__ == "__main__":`; avoid work with side effects at import time.
- Prefer functions for stateless behavior. Use classes when an object has meaningful state or a stable interface; keep constructors simple. Use `dataclass` for suitable data records and properties only when they improve the interface.
- Add type hints to public interfaces and nontrivial internal APIs. Use the project's type checker and supported syntax; do not add annotations that hide uncertainty with `Any`.
- Use context managers for files, locks, and transactions. Avoid mutable default arguments and shared mutable class attributes for instance state.
- Catch specific exceptions where recovery or added context is possible. Preserve the original cause with `raise ... from exc` when wrapping. Do not use bare `except` to hide failures.
- Use `pathlib` for paths when practical. Use structured logging instead of `print` in library or service code; never log secrets.
- In async code, avoid blocking calls in the event loop and make task cancellation and resource cleanup explicit.
- Test public behavior and edge cases with the project's test framework. Run the configured formatter, linter, type checker, and targeted tests.
