# Plan 02: Staging Worktree Sandbox, Profile Validation, and Admin Separation

Status: done
Project rules: AGENTS.md, docs/coding/common.md, docs/coding/python.md, skills/python-dev/SKILL.md
Target files: sdd_engine/validation.py, sdd_engine/cli.py, sdd_engine/service.py, tests/test_validation.py, tests/test_docker_integration.py
Depends on: 01-limits-paths-and-errors.md
Fixes: C1, C2 (profile validation, option injection, CLI admin split, rootless/rootful user), C5 (sys.path shadowing in ruff/mypy), C6b (CommandSpec.name length), K6 (profile field validation and mount safety)

## Outcome and boundary

Isolate validation containers from the host repository's `.git` directory and `engine.db` by staging the worktree (excluding `.git`) into a disposable directory before bind-mounting into Docker. Strictly validate `ValidationProfile` fields (`image`, `commands[].name`, `memory_limit`), pass `--` before the image argument in `docker run`, auto-select `--user` only for rootful Docker (preserving rootless Docker's UID mapping), require `--admin` in `cli.py` for `configure_profile`, and pass `-P` to Python in `ruff`/`mypy` standard commands so `/workspace` cannot shadow linter/typechecker modules. Storing `profile_revision` on SQLite `runs` rows is covered in Plan 03.

## Acceptance criteria

1. **`.git` and `engine.db` never exposed to validation containers (`C1`)**: `DockerCommandRunner.run` stages `workspace_root` (excluding `.git`) into a temporary directory before mounting `/workspace`. A container command that checks `/workspace/.git` finds it does not exist, and any files written by the container inside `/workspace` do not appear in the host worktree or `.git/hooks/`.
2. **Profile field validation and option-injection defense (`C2`, `C6b`, `K6`)**:
   - `ValidationProfile(image="--privileged", ...)` is rejected with `ValidationError`.
   - `ValidationProfile(memory_limit="lots", ...)` is rejected with `ValidationError`.
   - `CommandSpec(name="n" * 129, argv=("true",))` is rejected at profile validation time (`max_length=128`), matching `CommandResult.command_name`.
   - `docker_argv` places `"--"` immediately before `profile.image`.
3. **Rootless vs. rootful Docker user handling (`C2`, `L8`, Fact-Check #1)**:
   - Under rootless Docker (`test_docker_integration.py`), container UID `0` maps to `os.getuid()` on the host; `DockerCommandRunner` does not pass `--user 1000:1000` (which would map to a host subuid) and `test_workspace_writes_are_owned_by_the_host_user` (adapted to verify ownership inside the staged workspace or via command output) passes.
   - When `DockerCommandRunner(user="1000:1000")` is explicitly configured or rootful Docker is detected, `--user` is passed.
4. **Admin CLI flag required for `configure_profile` (`C2`)**: Running `python -m sdd_engine.cli configure_profile` without `--admin` exits with a parser error; `python -m sdd_engine.cli --admin configure_profile` succeeds.
5. **No `sys.path[0]` shadowing for `ruff` and `mypy` (`C5`)**: `standard_commands(Target.PYTHON, ...)` uses `("python", "-P", "-m", "ruff", "check", ".")` and `("python", "-P", "-m", "mypy", "--strict", ".")` so a `/workspace/ruff.py` or `/workspace/mypy.py` file cannot hijack linter or typechecker execution.

## Implementation plan

1. In [`sdd_engine/validation.py`](../validation.py#L42-L79), define strict annotated types using `sdd_engine/limits.py`:
   - `CommandName = Annotated[str, Field(min_length=1, max_length=limits.MAX_COMMAND_NAME_CHARS, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")]`
   - `ImageRef = Annotated[str, Field(min_length=1, max_length=255, pattern=r"^(?:sha256:[0-9a-f]{64}|[a-z0-9][a-z0-9._/-]*(?::[a-zA-Z0-9_.-]+)?(?:@sha256:[0-9a-f]{64})?)$")]`
   - `MemoryLimit = Annotated[str, Field(pattern=r"^[1-9][0-9]*[bkmgBKMG]$")]`
   - Apply `CommandName` to `CommandSpec.name`, `ImageRef` to `ValidationProfile.image`, and `MemoryLimit` to `ValidationProfile.memory_limit`.
   - Add a `ValidationProfile.digest() -> str` helper returning the SHA-256 hex digest of `self.model_dump_json().encode("utf-8")` for Plan 03's run-level profile pinning.
2. Add `stage_worktree(workspace_root: Path, staging_root: Path) -> None` in [`sdd_engine/validation.py`](../validation.py):
   - Copy all entries in `workspace_root` except `.git` (whether `.git` is a directory in a main worktree or a pointer file in a linked worktree) into `staging_root`.
   - Use `subprocess.run(("cp", "-a", "--reflink=auto", "--", *sources, str(staging_root)), check=True)` on POSIX with a `shutil.copytree(..., symlinks=True, ignore=shutil.ignore_patterns(".git"))` fallback if `cp --reflink=auto` is unsupported.
   - In `NativeValidator.validate` ([`validation.py:213-236`](../validation.py#L213-L236)) or `DockerCommandRunner.run` ([`validation.py:112-189`](../validation.py#L112-L189)), create a `tempfile.TemporaryDirectory(prefix="sdd-validate-")` per validation run (or per command), stage the worktree once before running the profile's commands sequentially so build artifacts from step 1 (e.g. `cmake --build build`) remain visible to step 2 (`ctest`) within the same validation round, and never mount the host worktree directly.
3. In [`DockerCommandRunner.run`](../validation.py#L122-L151):
   - Mount `staging_root` at `/workspace` instead of `workspace_root`. Because `staging_root` is generated by `tempfile.TemporaryDirectory(prefix="sdd-validate-")`, its path contains no commas or quotes (`K6`).
   - Place `"--"` immediately before `profile.image` (`"--", profile.image, *command.argv`).
4. In [`standard_commands`](../validation.py#L252-L260):
   - Change `ruff-check` argv to `("python", "-P", "-m", "ruff", "check", ".")` and `mypy-strict` argv to `("python", "-P", "-m", "mypy", "--strict", ".")`.
5. In [`sdd_engine/cli.py`](../cli.py#L13-L35):
   - Add `--admin` flag (`parser.add_argument("--admin", action="store_true")`).
   - Restrict default commands to `("begin_task", "submit", "finish_task", "get_run_report")` (plus `"cancel_task"` in Plan 05), and allow `("configure_profile", "get_profile")` only when `--admin` is passed (or allow `get_profile` on both and require `--admin` for `configure_profile`).

## Verification

- Run `uv run pytest tests/test_validation.py tests/test_docker_integration.py`:
  - Add unit tests in `tests/test_validation.py` verifying rejection of `image="--privileged"`, `memory_limit="lots"`, and `CommandSpec(name="x" * 129, ...)`.
  - Add a unit test verifying `"--"` precedes `profile.image` and `--mount` uses the staging directory rather than `workspace_root`.
  - Add a Docker integration test in `tests/test_docker_integration.py` confirming `/workspace/.git` does not exist inside the container even when `workspace` is a Git repository with `.git/hooks/` and `.git/spec-tech/engine.db`.
  - Add a CLI test verifying `configure_profile` is rejected without `--admin` and accepted with `--admin`.
- Run `uv run ruff check sdd_engine tests`, `uv run ruff format --check sdd_engine tests`, and `uv run mypy sdd_engine tests`.

## Open decisions and sources

- Staging once per `NativeValidator.validate()` call (via a context manager on the runner or validator) is preferred over staging per individual command so multi-step profiles like C++ (`cmake --build build` followed by `ctest --test-dir build`) share the staged `/workspace` across commands in the same validation pass while still discarding the staging directory afterward.
