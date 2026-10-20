SDD Engine Audit: feat/sdd-engine @ cb3afce

Scope: sdd_engine/ (about 2,250 lines), tests/, toolchains/, all skills/ and sdd-shared/templates/. No repository files were changed.

Method: I read every engine module end to end. I ran the configured checks: 90 tests pass, including the 4 Docker tests; ruff, ruff-format and mypy-strict are clean. I then ran 20 read-only probes against throwaway Git repos in the scratchpad to confirm suspected defects. Each finding is tagged probed (reproduced) or code-read (from source only).

---

1. Executive summary

Overall health: 5 / 10. The internal engineering is strong: frozen strict Pydantic models, state that holds only pointers, specific exceptions mapped to FailureReports, bounded retry loops, content-addressed integrity checks and a hardened Docker command line. The problems are at the edges, where the engine is supposed to enforce SDD:

- The validation sandbox can write to the host repo's .git.
- The engine never checks the spec. It treats the spec as opaque text that the implementer supplies itself.
- The agent-facing contracts are untyped. Neither the MCP schemas nor the prompt tell the agent what a valid submission looks like.

┌────────────────────────────────────────────────────┬───────┬──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                        Area                        │ Score │                                               Note                                               │
├────────────────────────────────────────────────────┼───────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Internal state and type contracts                  │ 8     │ Strict, frozen, checked after every node                                                         │
├────────────────────────────────────────────────────┼───────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Agent-facing contracts (MCP, prompt, spec binding) │ 3     │ files: object, tier: string; the spec is never parsed               │
├────────────────────────────────────────────────────┼───────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Sandbox and trust boundaries                       │ 3     │ .git writable from the container; admin split is convention only                                 │
├────────────────────────────────────────────────────┼───────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Graph flow clarity                                 │ 6     │ Explicit edges, but an overloaded node and 18 duplicate subg        │
├────────────────────────────────────────────────────┼───────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Skill clarity (zero ambiguity)                     │ 5     │ The engine protocol is undefined in the skills; a legacy pipent one │
├────────────────────────────────────────────────────┼───────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ DRY / KISS / SRP                                   │ 6     │ Duplicated store, three parallel registries, magic numbers          │
├────────────────────────────────────────────────────┼───────┼──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Testability                                        │ 7     │ Good integration tests; nodes are closures that can't be uni        │
└────────────────────────────────────────────────────┴───────┴──────────────────────────────────────────────────────────────────────────────────────────────────┘

Strengths to keep:
- Graph state carries ArtifactRef pointers instead of raw text.
- _validated_patch checks the merged next state after every node.
- Infrastructure failures don't spend repair attempts.
- Every artifact read verifies its digest and length.
- The Docker command line uses an allowlisted environment and kills containers on timeout.
- Tests use scripted runners.

---

2. Critical vulnerabilities and blockers

C1 · Critical · probed: the validation container can write the host repo's .git.
- validation.py:145-146 bind-mounts the whole worktree read-write. --read-only only protects the container's own root filesystem.
- In a main worktree, my probe container wrote .git/hooks/post-checkout, and the file appeared on the host. It also had wringine.db (store.py:44).
- Consequence: code under validation can get host code execution through hooks or core.fsmonitor. The engine itself runs git add -A in finish_task.
- It can also rewrite validation profiles, run rows and checkpoints.
- Linked worktrees expose their .git pointer file the same way. I did not test that case separately.

C2 · Critical · code-read + probed: the admin/implementer separation exists only by convention.
- cli.py:23 exposes configure_profile to any caller.
- Profiles live in a database the implementer's user (and, per C1, the container) can write.
- Runs don't record which profile revision validated them, so tampering can't be detected afterwards.
- ValidationProfile.image is unvalidated and sits in docker's option position (validation.py:64,149).
- image="--privileged" is accepted. Docker would parse it as a flag and use argv[0] as the image.

C3 · High · probed: the engine does not enforce the spec.
- begin_task takes the spec as free text from the implementer. The implementer also chooses its own target_files, target an
- Nothing links them to the committed spec file.
- The status gate is a denylist regex (service.py:30). It allows Status: draft, an unfilled Status: draft | ready | blocked template line, and specs with no Status line at all.
- It refuses a ready spec whose Open decisions section contains an indented status: blocked.

C4 · High · probed: the agent-facing contract is untyped and never disclosed.
- The MCP schemas published to agents (mcp_server.py:19-20,30) are tier/target: string, files: object, and an untyped objec
- GenerationPrompt (models.py:226) never states the submission contract.
- So an agent discovers documentation_metadata and error_handling_mapping only by failing a submission and burning a repair

C5 · High · code-read + probed: a run can be marked "validated" without the code actually passing.
- Profiles run tooling straight from the worktree: node_modules/.bin/{tsc,eslint,prisma} and cmake --build build (validation.py:267-293).
- Those paths are normally gitignored, which makes them invisible to the start and finish Git trees (scope.py:47-53). Tampeorted nor rolled back.
- node_modules/.bin/tsc is also accepted as an approved target file.
- python -m ruff|mypy|pytest runs with /workspace first on sys.path.
- A root conftest.py is not flagged as a test or check-config change.

C6 · High · probed (a, b) / code-read (c, d): runtime blockers.
- (a) Oversized submissions fail terminally after being written. WorkspaceFile.content has no size bound. A 5 MB file is written to disk, then the validate node fails reading it back at the 4 MB limit (graph.py:304). The result is failed / artifact_contract with no retry, although it is an ordinary contract violation.
- (b) There is no cancel or abort operation. An abandoned run blocks its worktree permanently: begin_task returns "workspacngine run". Any unexpected exception in submit also leaves the run pending. One concrete trigger: a profile command name over 128 characters passes CommandSpec (validation.py:45) but crashes CommandResult (models.py:259).
- (c) The engine only works from a source checkout. Skills are loaded from Path(__file__).parents[1]/skills (service.py:54) only sdd_engine. _load_skill then raises FileNotFoundError (guidance.py:114), which no handler maps.
- (d) submit runs the full validation synchronously inside one MCP call. With default profiles that can be up to 600 s per command, which MCP client timeouts may cut off.

---

3. Detailed findings

3.1 LangGraph state and flow

- L1 · Medium · probed: the generate node has too many jobs (SRP). graph.py:219-290 does hydration, the interrupt, the contract check, the target-path check, snapshots, writes and persistence. Because LangGraph re-runs a node on resume, hydration runs again on every submit. If a target file changed in the meantime (now too large, or not UTF-8), a valid submission is discarded as a hydration failure.
- L2 · Medium · measured: the graph builds 18 identical subgraphs on every MCP call. They differ only by a captured target, and take 88 ms to compile. _engine registers one profile (service.py:55), so 17 of them can never be reached (graph.py:92-96,159).
- L3 · Medium · code-read: the retry budget is misnamed. max_generation_attempts limits generation_failures per repair rounraph.py:231-238). The real bound on implementer prompts is max_gen × max_val (up to 9 with defaults), and nothing documentsit.
- L4 · Low: GraphPatch overloads None. None means both "clear this field" and "not set"; only exclude_unset tells them aparpes also allow patches like generation_attempts=None, which are caught only later, when the merged state is validated. Also,GraphPatch.model_validate(patch) on an existing instance does nothing (graph.py:425).
- L5 · Low: RouteDecision is ceremony. It regex-checks route strings but doesn't tie them to the edge maps (models.py:302-3ld be stricter and simpler.
- L6 · Low · latent: _step's error handling is too wide. One try wraps both the lock and graph.invoke (graph.py:141-150). Any ArtifactError raised inside a node would be relabeled "the workspace could not be locked". WorkspaceBusyError is also flattened, so callers can't tell
  a retryable "busy" from other errors.
- L7 · Medium: there are two overlapping rollback systems with different coverage. The graph's rollback node restores snapshots of target files, including ignored ones. finish_task separately runs a Git-tree restore over everything else (graph.py:187-217, service.py:175-181). Because the graph reverts target files first, the scope report for a failed run under-reports what the implementer changed.
- L8 · Medium: several exception types escape unmapped. restore_tree raises raw OSError from unlink, replace and symlink (sh_task catches only ArtifactError. With rootful Docker this is realistic: no Dockerfile sets USER and the service passes no--user, so root-owned files appear in the worktree. The run is then stuck at terminal with a partial restore. SQLite errors and Pydantic ValidationErrors from node code escape the same way.
- L9 · Low: lock semantics are misdescribed. The lock() docstring says it is held "for the duration of one run"; it is held per step. Run exclusivity actually comes from the SQLite partial unique index. submit's phase check runs outside any lock (service.py:118-126), so two
  concurrent submits could resume the wrong interrupt.
- L10 · Medium: repair diagnostics are hydrated last. Validation and failure feedback load after existing files have used up the 2 MB budget (guidance.py:83-96). A repair round can therefore fail hydration and end the run, when it is the round that most needs those diagnostics.
- L11 · Medium · probed: one worktree's path can drive another worktree's run. _run_store uses workspace only to find the sares it with row["workspace"] (service.py:38-40). From a sibling worktree's path, submit validated a run and wrote its fileinto the other worktree.

3.2 Skill configurations and prompts

- K1 · High: the skills never define the engine protocol. sdd-implement-*/SKILL.md:9 says only "drive begin_task (tier: "…"It never says:
  - when to use the engine;
  - how to choose target from 18 combined values (a full-stack SaaS change fits none of them);
  - how to derive target_files from the spec;
  - whether spec is the file's content or its path, or what format model and context take;
  - what a submission looks like, or how to react to each failure category;
  - what to do when finish_task returns restored: false.

  The engine README covers part of this, but no skill links to it.
- K2 · Medium: a workflow skill is injected as "engineering guidance". guidance.py:73 sends the full sdd-implement-<tier> text tells the agent to make checkpoint commits, run checks and call begin_task, which contradicts being inside the engineloop. Which instructions take precedence is undefined.
- K3 · Medium · probed: the submission's documentation fields are vague.
  - documentation_metadata is free text checked by keywords. @param … @returns … passes the required errors section, because @returns counts as one (models.py:213-214). So does the literal string "Args: Raises:".
  - error_handling_mapping requires at least one entry even for changes with no failure path, which invites made-up entries.
  - Neither field is checked against the code.
  - The files semantics are undocumented: a submission is a partial set of whole files; files from earlier rounds stay on disk; there is no way to delete a file.
- K4 · Medium: a legacy pipeline and duplicate templates create ambiguity (DRY). skills/sdd-implement/SKILL.md (3,655 wordsnds that don't exist (Maestro, cavecrew, Guardian, /sdd-spec-*, cavemem, HANDOFF.md), hard-codes model names, and pushesbranches. That contradicts git-checkpoints.md, which keeps everything local. The top-level templates/ folder is byte-identical to skills/sdd-shared/templates/. Anyone installing all of skills/ gets two implementation pipelines.
- K5 · Low: status vocabularies have drifted. Templates use draft | ready | blocked (task.simple.template.md:3). The legacylus uncertainty. The engine checks only blocked.
- K6 · Medium · probed: input sanitization has gaps.
  - Path checks compare raw strings without normalizing them. Aliased duplicates are accepted (src/x.py, src/./x.py, src//x.py), as are .GIT/… (which bypasses the .git check on case-insensitive filesystems) and NUL bytes. A NUL byte later crashes as an unmapped ValueError.
  - The same check is copied three times (models.py:79-86, artifacts.py:276-290, scope.py:118-125).
  - Profile image, memory_limit="lots" and 500-character command names are all accepted.
  - The --mount value interpolates the host path without CSV escaping (validation.py:146).
- K7 · Low/Medium: untrusted text reaches the agent's prompt unlabeled. Test stdout and stderr, existing file contents and caller context flow verbatim into the prompt (graph.py:437-445, guidance.py:98-110). That is a prompt-injection surface. The fields are at least structurally separate.
- K8 · Medium · probed: the scope-report heuristics are incomplete (scope.py:14-28).
  - Unflagged config paths: conftest.py, setup.cfg, tox.ini, jest.config.*, vitest.config.*, .cargo/config.toml, clippy.toml, .golangci.yml.
  - Missed markers: @ts-expect-error, @ts-nocheck, //nolint, #![allow(…)], pyright/pylint disables, pytest.mark.xfail, xit(

3.3 Code quality and design principles

- Q1 · Medium: the artifact store is implemented twice (DRY).
  - ProjectStore re-implements put/get/get_text/get_model from FileArtifactStore (store.py:162-212 vs artifacts.py:59-126),d only by tests.
  - import hashlib sits inside methods (store.py:164,176).
- Q2 · Medium: three per-target registries are kept in sync by hand. The Target enum (models.py:32), TARGET_SKILLS (guidance.py:16) and the standard_commands if-ladder (validation.py:239-313) have no test that ties them together.
- Q3 · Low: models and allowlists are duplicated.
  - GraphInput, GraphState and GraphPatch repeat the same fields (models.py:130-174,287-299).
  - Checkpoint types are allowlisted twice, once through checkpoint_serializer() and again through with_allowlist (graph.py:55-62,99-103).
- Q4 · Medium: size limits are magic numbers. 16_000, 16_000_000, 4_000_000, 2_000_000 and 1_000_000 appear inline in five  the 4 MB read limit and the unbounded write is the C6a bug.
- Q5 · Medium: persistence is stringly typed.
  - The run phase literals (pending/terminal/finished, 11 occurrences) have no enum.
  - ProjectStore.run() returns dict[str, object], so service.py casts with str(row[…]) and json.loads.
  - ProjectStore does too much (SRP): migrations, profiles, artifacts, runs and snapshots.
- Q6 · Low: some data is dead or write-only (YAGNI).
  - The snapshots table is written in production but read only by a test.
  - target_entities can't be set through the service.
  - standard_commands is reachable only from Python.
- Q7 · Low: names and errors are ambiguous.
  - workspace_id=run_id (service.py:96), engine.submit(run_id, run_id, files) (service.py:125).
  - A single ArtifactError covers Git failures, locks, missing runs and missing profiles, so callers can't branch on the error type.
- Q8 · Medium: the nodes can't be unit-tested. They are closures inside _build_specialist_subgraph, so every test goes through SQLite, Git and the service layer. Untested paths: exhausted generation or validation budgets, hydration failure, a validation-infrastructure failure inside the graph, a failing rollback node, oversized submissions, the MCP schemas, the CLI, cross-worktree access, and OSError during restore.
- Q9 · Medium: there is no observability. sdd_engine has no logging at all. Failures exist only as artifacts, with no node timeline and no timing data.

---

4. Recommendations and refactoring plan

Phase 0: close the sandbox (C1, C2)

1. Never mount the real worktree. Copy it into a throwaway directory without .git and mount that. Use cp -a --reflink=auto or equivalent, so node_modules and build/ stay cheap to copy. As a side benefit, files the container writes stop appearing in scope reports.
with tempfile.TemporaryDirectory(prefix="sdd-validate-") as staging:
    stage_worktree(workspace_root, Path(staging), exclude=(".git",))
    mount = ("--mount", f"type=bind,src={staging},dst=/workspace")
2. Default to the host user. Pass --user {uid}:{gid} unless Docker is detected as rootless, and add USER to the three Dockerfiles.
3. Tighten profile types and record which profile ran. Record profile_revision and the profile digest on each run and in it finish a run if the revision changed mid-run. Take configure_profile out of the default CLI.
ImageRef = Annotated[str, Field(max_length=255, pattern=r"^(sha256:[0-9a-f]{64}|[a-z0-9][a-z0-9._/-]*(:[\w.-]+)?@sha256:[0-9a-f]{64})$")]
CommandName = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9._-]*$")]
MemoryLimit = Annotated[str, Field(pattern=r"^[1-9][0-9]*[bkmg]$")]

Phase 1: SDD contracts at the boundary (C3, C4, C6a, K3, K6)

4. Type the MCP tools. FastMCP derives JSON Schema from annotations, so agents would see the real contract.
@implementer.tool()
def submit(workspace: str, run_id: RunId, submission: GenerationOutput) -> StepResult: ...

    kind: Literal["terminal"] = "terminal"
    run_id: RunId
    state: GraphState
StepResult = Annotated[PromptStep | TerminalStep, Field(discriminator="kind")]
   Do the same for tier: Tier and target: Target. Renaming files to submission is a contract change; update the README and skills with it.
5. Bind runs to the committed spec. begin_task(spec_path=…) would read the spec from HEAD, where the checkpoint workflow has already committed it, and record its blob SHA. Replace the denylist with a header allowlist:
_HEADER_STATUS = re.compile(r"^Status:\s*(?P<status>[a-z]+)\s*$", re.MULTILINE)

def require_ready(spec_text: str) -> None:
    header = spec_text.split("\n## ", 1)[0]          # header block only; nested sections never match
    statuses = _HEADER_STATUS.findall(header)
    if statuses != ["ready"]:
        raise SpecContractError(f"task spec header must say exactly 'Status: ready', found {statuses}")
   Add a machine-readable Target files: header to the three task templates. The engine then derives target_files from the spec instead of trusting the caller. Mirror the template change to /home/htxzz77/Projects/skills/.
6. Put the contract in the prompt. Add submission_schema = GenerationOutput.model_json_schema() to GenerationPrompt so the first submission can succeed.
7. Bound submissions before anything is written. Put the limits in a single limits.py, cap each file and the total in the ms a retryable generation_contract failure:
class WorkspaceFile(StrictModel):
    path: SafeRelativePath
    content: Annotated[str, Field(max_length=limits.MAX_FILE_CHARS)]
# GenerationOutput model_validator: sum(len(f.content.encode()) for f in files) <= limits.MAX_SUBMISSION_BYTES
8. Use one canonicalizing path validator in models, artifacts and scope:
def canonical_relative_path(value: str) -> str:
    if "\\" in value or any(ord(c) < 0x20 for c in value):
        raise ValueError("path contains a backslash or control character")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError("path must be a relative file path inside the workspace")
    if any(part.casefold() == ".git" for part in path.parts):
        raise ValueError("paths under .git are not allowed")
    return path.as_posix()          # 'src/./x.py' and 'src//x.py' both become 'src/x.py'
   Also refuse target paths under the profile's tool directories (node_modules/.bin, build/).
9. Rework the documentation fields. Either drop documentation_metadata and error_handling_mapping or make them structured. For example, per symbol: {symbol, params, raises}. Make the error mapping optional: tuple[...] = () with an explicit no_failure_paths: bool.

Phase 2: simplify the graph (L1-L11)

10. Build one specialist graph from module-level node functions, so each node can be unit-tested with fakes:
graph = StateGraph(GraphState)
graph.add_node("hydrate", partial(hydrate_prompt, deps=deps))      # stores prompt as an ArtifactRef
graph.add_node("await_submission", partial(await_submission, deps=deps))  # interrupt() only
graph.add_node("check_contract", partial(check_contract, deps=deps))      # pure; stores submission ref
graph.add_node("apply_files", partial(apply_files, deps=deps))            # snapshot + write
graph.add_node("validate", partial(run_native_checks, deps=deps))         # uses state.target
graph.add_node("rollback", partial(rollback_workspace, deps=deps))

def route_after_contract(state: GraphState) -> Literal["apply_files", "hydrate", "rollback", "__end__"]: ...
    Re-running await_submission on resume then only reloads a stored prompt, so it is deterministic. LangGraph can infer the edge map from the Literal return type, which makes RouteDecision unnecessary.
11. Rename and document the budgets. Use max_submissions_per_round and max_repair_rounds, add max_total_submissions, and sa
12. Hydrate diagnostics first, before existing files, so they get the budget.
13. Add an error taxonomy and a structured error envelope for MCP. Subclasses of an EngineError base: WorkspaceBusy, RunNotfactIntegrity, GitError, ProfileError, SpecContractError. The envelope is {"error": {"code", "message", "retryable"}}. WrapOSError in restore_tree.
14. Add cancel_task(workspace, run_id). It marks the run failed and runs both rollbacks. On any unexpected exception, submit should do the same, so a crash never strands the worktree.                                                                                               Check workspace ownership in _run_store: Path(row["workspace"]) == resolved workspace.
16. Make validation asynchronous. submit returns awaiting_validation and get_run_report polls. Alternatively, send MCP progress notifications.
17. Reconcile the two rollbacks. Document which one covers what, or keep only the Git-tree restore plus an explicit list of ignored target files.
Phase 3: DRY and clean code (Q1-Q9, K1, K2, K4, K8)
                                                                                                                                                                                                                                                                                      Replace the three registries with one table, plus a test that set(TARGETS) == set(Target):
@dataclass(frozen=True)
class TargetSpec:
    skills: tuple[str, ...]
    default_checks: Callable[[Path], tuple[CommandSpec, ...]] | None  # None: explicit profile required                                                                                                                                                                               ETS: Mapping[Target, TargetSpec] = MappingProxyType({...})
19. Split the store. Use RunRepository (returning a typed RunRecord with a RunPhase StrEnum), ProfileRepository and ArtifactRepository, with migrations in their own module. Delete FileArtifactStore or move it to tests. Drop the snapshots table and target_entities, or wire them up.
20. Fix the skills. Add a shared sdd-shared/templates/engine-protocol.md covering when to use the engine, target and target-file selection, the submission shape, how to handle each failure category, and how to handle cancellation and rollback errors. Link it from the three
    implement skills. Stop injecting the workflow skill as guidance; inject only the language skills. Move skills/sdd-imple into legacy/, outside the install set. Per AGENTS.md, mirror every skill change to /home/htxzz77/Projects/skills/.
21. Harden the scope report. Add the missing patterns from K8. Fingerprint the profile's tool paths (node_modules/.bin/*, build/) at begin and at finish, and flag any change. Better still, run only tools baked into the image.
22. Add structured logging per node (run_id, node, attempt, duration, failure category), plus tests for every path listed i

---

Verification and limits:
- Tests, ruff, format and mypy were all run and all pass.
- The probe scripts are in /tmp/claude-1000/-home-htxzz77-Projects-spec-tech/73d88276-5b47-4664-9c18-879198b5e9f1/scratchpad/probe_contracts.py, /tmp/claude-1000/-home-htxzz77-Projects-spec-tech/73d88276-5b47-4664-9c18-879198b5e9f1/scratchpad/probe_runs.py and /tmp/claude-1000/-home-htxzz77-Projects-spec-tech/73d88276-5b47-4664-9c18-879198b5e9f1/scratchpad/probe_worktree.py.
- The repo is unchanged: git status is clean.
- Not exercised: rewriting the .git pointer file of a linked worktree, PermissionError under rootful Docker, real MCP clienwheel (the packaging finding is from source only).
- I recorded the results in Caipira: #54 (the .git sandbox gotcha) and #55 (the audit status, which supersedes stale #39).