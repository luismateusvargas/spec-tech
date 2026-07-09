# HANDOFF.md — spec-tech SDD Environment

## Session: 2026-07-09 — SDD Enhancement Sprint

### Completed
Added 4 new capabilities to the SDD environment:

1. **Git PR Workflow** (`commands/sdd-git.md`): Two-phase git management. Phase A: branch creation (local only, early in pipeline). Phase B: PR creation (last step, after specs + docs + versions). Embedded merge/rebase decision matrix. Branch naming: `<type>/<task-id>-<slug>`.

2. **Versioning Control** (`commands/sdd-version.md`): Coordinated version bumps across all files. Version inventory, auto-detect bump type from commits, coordinated cascading bumps, CHANGELOG.md generation (Keep a Changelog), annotated git tag creation (never auto-push).

3. **Documentation Sync Agent** (`agents/scribe.md`): New agent (green, sonnet, Edit/Write tools). Reads updated specs, compares with docs, identifies drift, updates docs preserving style. Runs AFTER sdd-spec-update.

4. **Reference Docs** (`docs/versioning-best-practices.md`, `docs/git-workflow-reference.md`): Semver rules + anti-patterns, merge vs rebase decision matrix, branch strategies.

### Validation (2026-07-09)
`docs/versioning-best-practices.md` validated against semver.org spec, Keep a Changelog v1.1.0, and git tag best practices via web research. 7 corrections applied:
- Internal refactoring: can be PATCH or MINOR (not just PATCH)
- Bug-as-API fix: judgment call, not always MAJOR
- Deprecation window: must survive ≥1 MINOR release before MAJOR removal
- Version string rules: no leading zeroes, immutability, numeric increase
- Pre-release dot separator: `alpha.1` not `alpha1` (lexicographic sorting pitfall)
- Changelog: `[Unreleased]` section, `[YANKED]` marker
- Build metadata: ignored for precedence

### Files Created (5)
- `commands/sdd-git.md`
- `commands/sdd-version.md`
- `agents/scribe.md`
- `docs/versioning-best-practices.md`
- `docs/git-workflow-reference.md`

### Files Modified (4)
- `skills/sdd-implement/SKILL.md`
- `commands/sdd-spec-update.md`
- `templates/spec.template.yaml`
- `README.md`

### Deployed to ~/.claude/
- `commands/sdd-git.md`, `commands/sdd-version.md` → `~/.claude/commands/`
- `agents/scribe.md` → `~/.claude/agents/`
- `skills/sdd-implement/SKILL.md` → `~/.claude/skills/sdd-implement/`
- `templates/spec.template.yaml` → `~/.claude/commands/sdd-templates/`
- Skills registered: sdd-implement, sdd-git, sdd-version. Agent registered: scribe.

### Key Decisions
- **Branch early, push late**: Branch created at Phase 1.5 (local only). First git push at Phase 9 (PR creation).
- **Phase ordering enforced**: 6→7→8→9. Specs before docs. Docs before version. Version before PR.
- **Scribe is green, uses Edit/Write**: Unlike maestro/guardian (read-only, blue/red).

### Pending
- Operational testing on a real project (full 9-phase pipeline)
- Commit and push spec-tech changes to `github.com/luismateusvargas/spec-tech`

### Next Actions
1. Commit + push spec-tech to GitHub
2. Run full `/sdd-implement` pipeline on a test project through all 9 phases
3. Test `scribe` agent on project with known doc drift
4. Test `/sdd-git pr` with `gh` CLI on a real repo
