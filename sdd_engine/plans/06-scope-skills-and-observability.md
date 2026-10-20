# Plan 06: Scope Heuristics, Target Registry Consolidation, Structured Logging, and Skills Sync

Status: done
Project rules: AGENTS.md, docs/coding/common.md, docs/coding/python.md, skills/python-dev/SKILL.md
Target files: sdd_engine/scope.py, sdd_engine/targets.py, sdd_engine/guidance.py, sdd_engine/validation.py, sdd_engine/graph.py, sdd_engine/service.py, sdd_engine/README.md, skills/sdd-shared/templates/engine-protocol.md, skills/sdd-shared/templates/task.simple.template.md, skills/sdd-shared/templates/task.saas.template.md, skills/sdd-shared/templates/task.game.template.md, skills/sdd-shared/templates/task.spec.template.md, skills/sdd-implement-simple/SKILL.md, skills/sdd-implement-saas/SKILL.md, skills/sdd-implement-game/SKILL.md, skills/sdd-plan-simple/SKILL.md, skills/sdd-plan-saas/SKILL.md, skills/sdd-plan-game/SKILL.md, tests/test_validation.py, tests/test_graph.py
Depends on: 01-limits-paths-and-errors.md, 02-sandbox-and-profile-hardening.md, 03-store-and-worktree-isolation.md, 04-spec-and-submission-contracts.md, 05-graph-flow-and-lifecycle.md
Fixes: K8 (incomplete scope heuristics), C5 (root conftest.py & tool-path tamper detection), Q2 (three parallel target registries), Q9 (structured logging), K1 (undefined engine protocol in skills), K4 (legacy sdd-implement ambiguity), Q8 (complete test suite for all audit paths)

## Outcome and boundary

Expand `scope.py` heuristics to catch all config/test paths and suppression/skip markers from `K8` and `C5`; replace the three hand-synced target registries (`Target`, `TARGET_SKILLS`, `standard_commands`) with a single `TARGETS` registry in `sdd_engine/targets.py` (`Q2`); add structured `logging` across node transitions and command executions (`Q9`); document the complete engine protocol in `skills/sdd-shared/templates/engine-protocol.md`, add `Target files:` to the task templates, link `engine-protocol.md` from `sdd-implement-{simple,saas,game}/SKILL.md`, and mirror all skill and template edits to `/home/htxzz77/Projects/skills/` per `AGENTS.md` (`K1`, `K4`).

## Acceptance criteria

1. **Expanded scope-report heuristics (`K8`, `C5`)**:
   - `_TEST_PATH` and `_CHECK_CONFIG` in `sdd_engine/scope.py` flag root and nested `conftest.py`, `setup.cfg`, `tox.ini`, `noxfile.py`, `jest.config.*`, `vitest.config.*`, `.cargo/config.toml`, `clippy.toml`, `.clippy.toml`, `.golangci.yml`, and `.golangci.yaml`.
   - `_SUPPRESSION` flags `@ts-expect-error`, `@ts-nocheck`, `//nolint` / `// nolint`, `#![allow(...)]` (inner attributes), `pyright: ignore`, and `pylint: disable`.
   - `_SKIP` flags `pytest.mark.xfail`, `xit(`, `xdescribe(`, `test.todo(`, and `DISABLED_` (GTest).
2. **Single `TARGETS` registry (`Q2`)**:
   - `sdd_engine/targets.py` defines `TargetSpec(skills: tuple[str, ...], default_commands: Callable[[Path], tuple[CommandSpec, ...]] | None)` and `TARGETS: Mapping[Target, TargetSpec]`, used by both `guidance.py` and `validation.py`.
   - A unit test asserts `set(TARGETS) == set(Target)` and verifies every target's skills exist on disk.
3. **Structured observability (`Q9`)**:
   - `sdd_engine` logs structured events via `logging.getLogger("sdd_engine")` at node entry/exit (`run_id`, `node`, `attempt`, `status`, `failure_category`, `duration_ms`) and command execution (`command_name`, `exit_code`, `timed_out`, `duration_ms`), without logging file contents or secrets.
4. **Defined engine protocol in skills and mirrored to `/home/htxzz77/Projects/skills/` (`K1`, `C3`, `AGENTS.md`)**:
   - `skills/sdd-shared/templates/engine-protocol.md` specifies when to use the engine, how to select `target` from the 18 `Target` values, how `Target files:` in the committed spec binds `begin_task`, the `GenerationOutput` submission contract (`files`, `documentation_metadata`, `error_handling_mapping`, `no_failure_paths`), how to handle each failure category (`generation_contract`, `native_validation`, `validation_infrastructure`, `hydration`, `rollback`), `cancel_task`, and what to do when `finish_task` returns `restored: false`.
   - `skills/sdd-shared/templates/task.{simple,saas,game,spec}.template.md` include `Target files: <comma-separated relative paths>`.
   - `skills/sdd-implement-{simple,saas,game}/SKILL.md` link directly to `../sdd-shared/templates/engine-protocol.md`.
   - Every modified file under `skills/` is copied to `/home/htxzz77/Projects/skills/` and verified byte-identical with `diff -ru`.

## Implementation plan

1. Update [`sdd_engine/scope.py`](../scope.py#L14-L28):
   - Update `_SUPPRESSION`:
     ```python
     _SUPPRESSION = re.compile(
         r"(?:noqa\b|type:\s*ignore\b|pyright:\s*ignore\b|pylint:\s*disable\b|"
         r"eslint-disable\b|@ts-(?:ignore|expect-error|nocheck)\b|pragma:\s*no cover\b|"
         r"#!?\[allow\(|//\s*nolint\b|NOLINT\b)"
     )
     ```
   - Update `_SKIP`:
     ```python
     _SKIP = re.compile(
         r"(?:pytest\.mark\.(?:skip|xfail)\b|\bskip\s*\(|\bignore\s*\(|\b(?:x?it|x?describe|test)\.(?:skip|todo)\s*\(|"
         r"\bx(?:it|describe|test)\s*\(|#\[ignore\b|\bt\.Skip(?:Now|f)?\s*\(|\bGTEST_SKIP\s*\(|\bDISABLED_[A-Za-z0-9_]+)"
     )
     ```
   - Update `_TEST_PATH`:
     ```python
     _TEST_PATH = re.compile(
         r"(?:^|/)(?:tests?|__tests__)/|(?:^|/)(?:conftest\.py|test_[^/]+)|(?:_test|\.(?:test|spec))\.[^/]+$"
     )
     ```
   - Update `_CHECK_CONFIG`:
     ```python
     _CHECK_CONFIG = re.compile(
         r"(?:^|/)(?:\.gitignore|pyproject\.toml|setup\.cfg|tox\.ini|noxfile\.py|conftest\.py|"
         r"pytest\.ini|mypy\.ini|ruff\.toml|eslint\.config\.[^/]+|\.eslintrc[^/]*|"
         r"(?:jest|vitest)\.config\.[^/]+|tsconfig[^/]*\.json|Cargo\.toml|\.cargo/config\.toml|"
         r"\.?clippy\.toml|go\.mod|\.golangci\.ya?ml|CMakeLists\.txt|package\.json)$"
     )
     ```
2. Create `sdd_engine/targets.py` combining `TARGET_SKILLS` from [`sdd_engine/guidance.py:16-35`](../guidance.py#L16-L35) and `standard_commands` from [`sdd_engine/validation.py:239-313`](../validation.py#L239-L313) into `TARGETS: Mapping[Target, TargetSpec]`, and re-export `TARGET_SKILLS` and `standard_commands` from `guidance.py` and `validation.py` so existing imports remain unbroken.
3. Add `logging.getLogger(__name__)` instrumentation in `sdd_engine/graph.py`, `sdd_engine/validation.py`, and `sdd_engine/service.py` using `time.monotonic()` to record elapsed milliseconds and structured `extra={...}` fields (`Q9`).
4. Create `skills/sdd-shared/templates/engine-protocol.md` and update:
   - `skills/sdd-shared/templates/task.simple.template.md`
   - `skills/sdd-shared/templates/task.saas.template.md`
   - `skills/sdd-shared/templates/task.game.template.md`
   - `skills/sdd-shared/templates/task.spec.template.md`
   - `skills/sdd-implement-simple/SKILL.md`
   - `skills/sdd-implement-saas/SKILL.md`
   - `skills/sdd-implement-game/SKILL.md`
   - `skills/sdd-plan-simple/SKILL.md`, `skills/sdd-plan-saas/SKILL.md`, `skills/sdd-plan-game/SKILL.md`
   - `sdd_engine/README.md`
5. Mirror all changed files in `skills/` to `/home/htxzz77/Projects/skills/` and verify with `diff -q` / `cmp`.

## Verification

- Run `uv run pytest`:
  - Add parametrized tests in `tests/test_graph.py` covering every path and marker in `K8` (`conftest.py`, `.cargo/config.toml`, `jest.config.js`, `vitest.config.ts`, `setup.cfg`, `tox.ini`, `.golangci.yml`, `clippy.toml`, `noxfile.py`, `// @ts-expect-error`, `// @ts-nocheck`, `//nolint:errcheck`, `#![allow(dead_code)]`, `# pyright: ignore`, `# pylint: disable=all`, `@pytest.mark.xfail`, `xit('x', () => {})`, `TEST(Suite, DISABLED_case)`).
  - Add a test in `tests/test_validation.py` verifying `set(TARGETS) == set(Target)` and that every skill referenced by `TARGETS` exists under `skills/`.
- Run `uv run ruff check sdd_engine tests`, `uv run ruff format --check sdd_engine tests`, and `uv run mypy sdd_engine tests`.
- Run `diff -ru skills/sdd-shared /home/htxzz77/Projects/skills/sdd-shared` and `for d in sdd-{orchestrate,plan,implement,review}-{simple,saas,game}; do diff -ru "skills/$d" "/home/htxzz77/Projects/skills/$d"; done` to confirm 0 diffs.

## Open decisions and sources

- **Legacy `skills/sdd-implement/SKILL.md` and top-level `templates/` (`K4`, Fact-Check #6)**: [`README.md:19`](../../README.md#L19) explicitly states *"The older `skills/sdd-implement/` and top-level `templates/` remain in the tree for existing users."* Confirm whether to (a) move `skills/sdd-implement/` and `templates/` into `legacy/` and update `README.md:19`, or (b) keep them in place per `README.md:19` with a deprecation notice at the top of `skills/sdd-implement/SKILL.md`.
