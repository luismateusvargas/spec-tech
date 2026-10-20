---
name: database-dev
description: Use automatically whenever designing, implementing, reviewing, or refactoring database access, schemas, migrations, queries, or persistence in any project. Apply the shared safety rules and the matching TypeScript/Prisma, Python/SQLAlchemy/Alembic, or Rust/Diesel guidance.
---

# Database Development

Use this skill for application persistence and database schema work. First identify the database engine, configured library versions, migration system, and existing repository boundaries. Follow the project’s established stack; do not add or replace an ORM or migration tool without a clear task requirement.

## Shared Rules

- Keep database access behind a focused persistence or repository boundary. Map persistence records into domain types at that boundary; do not expose ORM records or driver errors as public API contracts.
- Treat database constraints as the final integrity boundary. Use primary keys, foreign keys, unique, not-null, and check constraints for invariants that must hold for every writer. Add application validation for useful early feedback; it does not replace database constraints.
- Validate untrusted input at runtime. Static types, generated client types, and ORM models do not prove that external JSON or stored data is valid.
- Parameterize all values. Never build SQL by interpolating user input. Keep raw SQL narrow, reviewed, and justified by functionality or measured performance needs.
- Define transaction scope around one coherent use case. Keep transactions short; avoid network calls or unrelated slow work while holding locks. Make isolation, retries, and locking explicit where correctness depends on them.
- Scope connections, clients, sessions, and transactions to the application’s lifecycle and concurrency model. Reuse pools appropriately; do not share a non-concurrent session across requests, threads, or tasks.
- Make schema changes through version-controlled migrations. Review generated SQL, data effects, lock behavior, and deployment ordering. Test migrations against representative existing data. Use expand-and-contract changes when old and new application versions may overlap. Never rewrite an applied migration.
- Preserve least privilege and keep credentials out of source, logs, and error messages. Avoid logging sensitive query parameters or row contents.
- Measure query performance with representative workloads and query plans. Select only needed columns, handle pagination deliberately, batch related work, and check for N+1 queries before adding speculative indexes or caches.
- Test domain behavior separately from persistence mapping. Use integration tests with an isolated disposable database or schema to cover real queries, constraints, transaction behavior, and migration upgrades. Never point tests at production data.
- Translate persistence failures into stable application or domain errors at the boundary. Preserve useful causes for diagnostics while avoiding database-specific details in user-facing responses.

## TypeScript with Prisma

- Treat the Prisma schema and generated Prisma Client as the source of application query types. After schema changes, generate the client using the project’s configured workflow and verify generated artifacts are current where they are committed or required.
- Use generated query argument and result types, and select or include only the fields needed. Keep external request validation separate: Prisma’s types do not validate runtime input.
- Keep Prisma Client inside the persistence layer and reuse an appropriately scoped client instance so the process does not create unnecessary connection pools. Follow the deployment platform’s lifecycle model, including serverless reuse guidance when applicable.
- Use Prisma’s parameterized query APIs. For raw SQL, prefer tagged parameterized APIs and never concatenate untrusted input or use unsafe raw-query variants with interpolated values.
- Keep `$transaction` blocks focused and bounded. Do not hold a transaction open while calling remote services or performing unrelated work.
- Map Prisma errors at the repository boundary to application errors that callers can handle. Do not return raw Prisma error objects through HTTP or other public interfaces.
- Commit and review Prisma Migrate SQL files. Distinguish local development migration creation from deployment migration application, and use the project’s configured commands. Do not treat schema push as a substitute for reviewed migrations in shared or production environments.

## Python with SQLAlchemy and Alembic

- Keep SQLAlchemy persistence models and Pydantic domain/API models distinct when they serve different contracts. Write explicit mapping at the repository boundary; do not assume an ORM row is automatically a validated domain object.
- Follow the configured SQLAlchemy version and typed mapping style. Scope `Session` or `AsyncSession` to a request or unit of work, use explicit transaction contexts, and do not share a session across concurrent tasks or threads.
- Make commit, flush, and rollback behavior clear. Avoid hidden commits in lower-level repository helpers; let the use-case boundary own the transaction where practical.
- Use Alembic migrations as the reviewed schema history. Treat autogenerate output as a draft: inspect and edit it because it may miss changes or produce operations that need data-aware handling. Commit migrations and test upgrades against a representative database. Test downgrades when they are safe and supported.
- Convert SQLAlchemy and driver failures explicitly at the persistence boundary into stable domain/application errors, preserving the original cause for diagnostics.
- Use SQLAlchemy expression parameters or bound parameters for values. Do not construct SQL with f-strings or string concatenation from external input.
- Choose eager-loading strategies deliberately and verify query counts for relationship-heavy reads to prevent N+1 behavior.

## Rust with Diesel

- Use Diesel as the default Rust persistence layer. Prefer its typed query DSL, schema declarations, and typed result mapping so table, column, expression, and result-shape mismatches are caught by Rust’s type checker.
- Keep Diesel schema declarations synchronized with the database. Use the project’s configured Diesel CLI workflow (such as `diesel print-schema`) and review schema changes alongside migrations.
- Define focused query helpers that build or return Diesel queries where possible. Keep query construction reusable and separate from execution when that makes the query easier to compose.
- Map Diesel query results into persistence or domain types deliberately. Use Diesel’s `Selectable` / `Queryable` patterns appropriate to the configured version and backend; select only the fields needed rather than binding domain types directly to every table column.
- Use Diesel’s typed query DSL for ordinary reads and writes. Use `diesel::dsl::sql` for a small SQL expression or `sql_query` for a whole statement only when the DSL cannot reasonably express the operation. Bind all values; never interpolate untrusted data. Raw SQL annotations and `QueryableByName` mappings require extra review because Diesel cannot type-check their SQL/result types like DSL queries.
- Keep connections and pools scoped to the application’s lifecycle and concurrency model. Acquire a connection for the operation, and make transaction boundaries and commit/rollback behavior explicit. Avoid holding transactions across unrelated or remote awaits.
- Keep Diesel migrations in version control and review generated migration SQL before applying it. Test upgrades against representative data; test downgrades when safe and supported. Keep generated `schema.rs` aligned with the applied migration state.
- Convert `diesel::result::Error` and backend failures into domain/application errors explicitly at the repository boundary; preserve diagnostic context without exposing database details to API callers.

## Verification

- Run the project’s configured formatting, lint, type-check/build, and database validation commands. Do not invent new tool versions or commands when the repository already defines them.
- Verify both the schema/migration change and affected application behavior. For Diesel, compile the configured queries and verify schema declarations against migrations/database state. For Prisma, verify generated client state and migrations. For SQLAlchemy/Alembic, inspect migration output and exercise the migration path.
- Report checks that could not run because a database, service, or credential was unavailable. Never substitute a production database for a missing test database.

## Official References

- Prisma type safety and generated client: https://docs.prisma.io/docs/orm/prisma-client/type-safety
- Prisma Migrate: https://docs.prisma.io/docs/orm/v7/prisma-migrate
- SQLAlchemy transaction management: https://docs.sqlalchemy.org/en/21/orm/session_transaction.html
- Alembic autogenerate limitations and review: https://alembic.sqlalchemy.org/en/latest/autogenerate.html
- Diesel typed query construction and result mapping: https://diesel.rs/guides/all-about-selects/
- Diesel CLI schema and migration management: https://diesel.rs/guides/configuring-diesel-cli.html
- Composing reusable Diesel queries: https://diesel.rs/guides/composing-applications/
