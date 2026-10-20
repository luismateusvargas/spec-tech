---
name: python-dev
description: Use automatically for all Python work, including planning, implementation, review, and refactoring in Python projects or mixed-language codebases. Apply these rules to build modular, typed, predictable Python systems.
---

# Python development reference

Use this skill for every task involving Python. Apply all rules here to Python work.

## Establish the project context

- Read repository instructions and the relevant Python guide before editing. Check the supported Python version, dependency and tooling configuration, package layout, callers, and nearby tests.
- Use the configured Python version and exact project commands. The rules in this skill remain mandatory; project configuration determines how they are enforced.
- Preserve behavior, public contracts, data formats, and performance unless the request calls for a change. Keep refactors scoped and explain meaningful tradeoffs.

## Design cohesive modules and services

- Organize modules around cohesive responsibilities. Keep internal implementation details private by convention and expose a deliberate, simple package API.
- Before adding an abstraction, inspect existing modules and call sites. Consolidate repeated logic when occurrences have the same meaning and are expected to change together. Two or more genuine copies are candidates for extraction; similar-looking code with different responsibilities is not automatically duplication.
- Put shared behavior in the narrowest appropriate module or package. Use a `utils` module/package only for behavior that is genuinely general; domain-specific logic belongs with its domain. Avoid catch-all utility modules and import cycles.
- Prefer small functions, focused modules, explicit data flow, and clear dependency direction. Do not split code solely to reduce line count.
- Services must not depend directly on other services. They may depend on infrastructure through structural interfaces defined with `typing.Protocol`.
- Inject infrastructure explicitly. Annotate dependencies with their `Protocol`; keep constructors simple and free of runtime type checks or generic type-variable bounds. Enforce contracts with strict static checking, and validate values at external trust boundaries.
- Keep each service to at most one generic infrastructure type parameter. Compose multiple infrastructure capabilities into a focused protocol instead of adding a type parameter for each dependency.
- Use shared thread-safe contexts or asynchronous connection pools when required. Make dependency lifetimes, concurrency, cancellation, and resource cleanup explicit.

## Use types and validated data models

- Add type hints to every public interface and nontrivial internal API. Run mypy or pyright in strict mode. Avoid `Any`; confine it to an unavoidable dynamic boundary and validate before it enters domain logic.
- Use enums, literal types, and discriminated unions to represent alternatives and states. Use `NewType` or small domain classes for primitive values with distinct meanings or constraints.
- Make invalid values difficult to construct. Validate at constructors, parsing functions, or other trust boundaries and raise a specific error when validation fails.
- Use Pydantic `BaseModel` for immutable domain data, network payloads, and operational configuration. Set models as frozen and prefer immutable field types where deep immutability matters. Use explicit builder or schema-copy operations for updates; do not mutate generic payload dictionaries as a substitute for typed models.
- Use regular classes for behavior with meaningful runtime state. Keep module imports free of side effects, and put executable entry points behind `if __name__ == "__main__":`.

## Handle errors explicitly

- Define an application domain exception base and specific exceptions for domain failures. Do not expose generic `Exception`, `ValueError`, or `KeyError` as service-boundary errors.
- Catch only specific exceptions at the layer that can recover or translate them. At infrastructure boundaries, explicitly map known low-level failures to domain exceptions with `raise DomainError(...) from exc`.
- Do not broadly catch, silently discard, or automatically re-raise framework or database exceptions through service boundaries. Preserve the original cause when translating an error.
- Keep failure paths predictable. Do not use assertions for input validation or expected runtime failures.

## Tests, documentation, and checks

- Keep focused unit tests in the same source file as the implementation. If the test runner does not discover colocated tests by default, configure it to do so. Use pytest and write each test in fixture/setup → actual → expected → assertion order. Prefer assertions on complete typed objects or schemas over checking fields one by one.
- Keep fixtures generic and reusable. Use descriptive names such as `fixture`, `actual`, and `expected`; keep test boilerplate small.
- Add concise triple-quoted docstrings to every public module, function, class, and method. Document interfaces with `Args:`, `Returns:`, and `Raises:` sections as applicable. Do not include usage examples in docstrings.
- Run tests and all configured checks for Python changes. Use Ruff for linting and formatting; warnings and style violations are blocking. Run either mypy or pyright in strict mode. Report checks that could not run.
- Use context managers for files, locks, and transactions. Use `pathlib` for paths, structured logging for library and service code, and never log secrets. Avoid mutable default arguments and shared mutable class attributes for instance state.
- In async code, do not block the event loop. Make task cancellation and cleanup explicit.

## Pydantic references

- Use the Pydantic version configured by the project. For Pydantic v2, model configuration uses `ConfigDict` assigned to `model_config`; do not use the deprecated inner `Config` class.
- For version-specific behavior, consult the [Pydantic model configuration documentation](https://docs.pydantic.dev/latest/concepts/config/).

