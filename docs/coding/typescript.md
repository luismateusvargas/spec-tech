# TypeScript

- Follow the project's `tsconfig`, supported TypeScript version, formatter, and import conventions. Keep strictness enabled when already configured; do not weaken it to make a change pass.
- Model domain states with precise interfaces, types, and discriminated unions. Prefer `unknown` at external boundaries, narrow it with validation, and avoid `any`, non-null assertions, and broad casts without a documented reason.
- Use `type` or `interface` consistently with nearby code. Export only stable public types; keep implementation details private to the module.
- Reflect runtime behavior in types: optional fields, nullability, promises, and error results. Types do not validate JSON, environment variables, or network input at runtime.
- Prefer small generic helpers only when they remove real duplication. Avoid type machinery that obscures the value shape or makes diagnostics hard to understand.
- Preserve inference for local values and annotate public boundaries and complex returns where it clarifies the contract.
- Handle rejected promises and cancellation explicitly. For Node.js code, also follow the [Node.js guide](nodejs.md).
- Add tests for behavior and boundary validation. Run the project's type check as well as relevant tests and linting.
