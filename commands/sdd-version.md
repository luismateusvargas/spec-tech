# /sdd-version — SDD Versioning Control & Tag Management

## Trigger
Manual only. User MUST type `/sdd-version <action>` where action is:
- `status` — Show current versions of all components (default if no action specified)
- `bump <type>` — Bump versions across all files (`major`, `minor`, `patch`, `premajor`, `preminor`, `prepatch`, `prerelease`)
- `changelog` — Generate/update CHANGELOG.md from spec changelog entries
- `tag` — Create annotated git tag for current version
- `sync` — Check and fix version inconsistencies across spec files

## Purpose
Coordinate versioning across ALL spec files, project files (package.json/pyproject.toml), CHANGELOG.md, and git tags. Apply research-backed semver best practices. Run AFTER `/sdd-spec-update` and Scribe, BEFORE PR creation (sdd-implement Phase 8).

## Pre-Conditions
- Specs are up to date (`/sdd-spec-update` completed). Reject if spec update hasn't run.
- Git repository exists (for tag creation)
- All changes committed (for tag creation — clean working tree)

---

## Phase 1: Version Inventory (`/sdd-version status`)

### 1.1 Scan all versioned files
Read every file that carries a version:

```
Project files:
  package.json (or pyproject.toml, Cargo.toml, etc.)

Spec files:
  specs/<domain>.spec.yaml  — each has metadata.version

Documentation:
  CHANGELOG.md (if exists)

Git:
  git tag -l 'v*' --sort=-creatordate | head -5
```

### 1.2 Build version matrix
Present a unified view:

```
VERSION INVENTORY — <project>
===============================
Project:             1.2.3  (package.json)
CHANGELOG.md:        1.2.3  (latest entry)

Spec files:
  api-surface:        1.2.3  locked
  data-model:         1.2.0  locked  ⚠ behind project
  business-domain:    1.2.0  locked  ⚠ behind project
  security:           2.0.0  locked  (extends global baseline v2.0.0)
  deployment:         1.1.0  locked

Git:
  Latest tag:         v1.2.3  (2026-07-08)
  Tags:               v1.2.3, v1.2.0, v1.1.0, v1.0.0

Status: 2 spec files behind project version. Run /sdd-version sync.
```

### 1.3 Flag inconsistencies
- Spec version < project version and spec was modified → needs bump
- CHANGELOG.md missing or latest entry doesn't match project version → needs update
- Git tag missing for current version → needs tag
- Multiple spec files at different versions without changelog entries → possible drift

---

## Phase 2: Change Classification (`/sdd-version bump`)

### 2.1 Auto-detect bump type from commits
Parse git log since last version tag:

```bash
git log v<last-version>..HEAD --oneline
```

Classify each commit by conventional commit prefix:

| Prefix | Bump implication |
|--------|-----------------|
| `feat!:` or `BREAKING CHANGE:` | MAJOR |
| `feat:` | MINOR |
| `fix:`, `perf:`, `refactor:`, `docs:`, `chore:`, `test:`, `build:`, `ci:`, `style:` | PATCH |

**Rule:** Highest detected bump wins. If ANY commit implies MAJOR → MAJOR bump. If ANY implies MINOR (and none MAJOR) → MINOR bump. All PATCH → PATCH bump.

**Fallback:** If no conventional commit prefixes found, or git history doesn't help:
1. Show user the commits since last tag
2. Ask: "What type of change is this? [major/minor/patch]"
3. User specifies explicitly

### 2.2 Bump type semantics (from versioning-best-practices.md)

| Bump | When |
|------|------|
| **MAJOR** (X+1.0.0) | Breaking API changes, removed endpoints, changed response schema, renamed fields, dropped tables/columns, changed auth requirements |
| **MINOR** (X.Y+1.0) | New endpoints, new optional fields, new entities, new features, deprecations (not removals) |
| **PATCH** (X.Y.Z+1) | Bug fixes, internal refactoring, performance improvements, typo fixes, documentation fixes |
| **PREM AJOR** (X+1.0.0-alpha.1) | MAJOR change, pre-release |
| **PREMINOR** (X.Y+1.0-alpha.1) | MINOR change, pre-release |
| **PREPATCH** (X.Y.Z+1-alpha.1) | PATCH change, pre-release |
| **PRERELEASE** (X.Y.Z-alpha.N+1) | Increment pre-release counter |

### 2.3 Confirm with user
Before modifying any file:

```
VERSION BUMP PLAN
==================
Change type: MINOR (auto-detected — 2 feat: commits)
Commits analyzed: 5 (since v1.2.3)

Files to bump:
  package.json:                     1.2.3 → 1.3.0
  specs/api-surface.spec.yaml:      1.2.3 → 1.3.0  (MINOR — new endpoint added)
  specs/data-model.spec.yaml:       1.2.0 → 1.2.1  (PATCH — index added, no entity change)
  specs/business-domain.spec.yaml:  1.2.0 → no bump (unchanged)
  specs/security.constitution.yaml: 2.0.0 → no bump (unchanged)
  specs/deployment.spec.yaml:       1.1.0 → no bump (unchanged)
  CHANGELOG.md:                     new entry for 1.3.0

Proceed? [y/N]
```

---

## Phase 3: Coordinated Bump

### 3.1 Apply version changes
For each file that needs bumping, update the version field:

**Spec files** (`specs/<domain>.spec.yaml`):
- Update `metadata.version`
- Update `metadata.updated` to current ISO timestamp
- Append to `# CHANGELOG` comment block

**Project file** (`package.json` / `pyproject.toml`):
- Update `version` field
- For `package.json`: also update `package-lock.json` if it exists (npm needs it)

**CHANGELOG.md**: See Phase 4.

### 3.2 Cascading bump rules
When one spec bumps, dependent specs may need bumps:

| Trigger | Cascade | Rationale |
|---------|---------|-----------|
| api-surface MAJOR | deployment MINOR (at least) | API migration affects deployment config |
| data-model MAJOR | business-domain MINOR (at least) | Entities changed, business rules must reflect |
| data-model MAJOR | api-surface MINOR (at least) | Models drive API shapes |
| security MINOR (new rules) | No cascade | Security is additive, doesn't break other specs |
| deployment MINOR | No cascade | Infrastructure changes don't affect domain specs |

### 3.3 Specs that don't change
Specs with no changes since last bump → NO version bump. Do NOT artificially inflate versions. A spec at v1.2.0 that hasn't changed stays at v1.2.0 even when the project releases v1.3.0.

---

## Phase 4: Changelog Generation (`/sdd-version changelog`)

### 4.1 Read existing CHANGELOG.md
If it doesn't exist, create from template.

### 4.2 Gather changes from spec changelogs
Each spec file has an inline `# CHANGELOG` comment block. Collect entries since the last CHANGELOG.md version.

### 4.3 Generate new entry
Insert at top of CHANGELOG.md:

```markdown
## [1.3.0] - 2026-07-09

### Added
- Payment webhook endpoint (POST /api/v1/payments/webhook) [API-TASK-004]
- Rate limiting on auth endpoints [SEC-TASK-003]

### Changed
- User `name` split into `firstName`/`lastName` [DM-TASK-002]

### Fixed
- Token refresh race condition [API-TASK-002]
```

**Rules:**
- Group by: Added, Changed, Deprecated, Removed, Fixed, Security
- Each entry references the spec task ID: `[API-TASK-004]`
- Human-readable descriptions, not commit messages
- If a group has no entries, write `- (none)` or omit entirely

### 4.4 Cross-reference
Link version to git tag (if hosted on GitHub):
```markdown
[1.3.0]: https://github.com/<org>/<repo>/releases/tag/v1.3.0
```

---

## Phase 5: Git Tag (`/sdd-version tag`)

### 5.1 Pre-tag checks
- Working tree clean (`git status --porcelain` is empty)
- CHANGELOG.md updated for this version
- User confirms tag creation

### 5.2 Create annotated tag
```bash
git tag -a v1.3.0 -m "Release v1.3.0

- Added: payment webhook (API-TASK-004)
- Fixed: token refresh race condition (API-TASK-002)
- Specs: api-surface v1.2.3→v1.3.0, data-model v1.2.0→v1.2.1"
```

**Always annotated.** Never lightweight for releases.

### 5.3 Output
```
SDD VERSION — Tag Created
==========================
Tag: v1.3.0 (annotated)
Commit: abc1234
Message: Release v1.3.0 — payment webhook, rate limiting
Status: LOCAL ONLY (not pushed)
Next: Push tag after PR is merged: git push origin v1.3.0
```

**Do NOT auto-push tags.** User decides when to push (usually after PR merge).

---

## Phase 6: Sync (`/sdd-version sync`)

### 6.1 Detect inconsistencies
Run Phase 1 (inventory). Flag every inconsistency:
- Spec version doesn't match project version (and spec was modified)
- CHANGELOG.md version doesn't match project version
- Git tag missing
- Two specs reference each other with wrong versions

### 6.2 Fix plan
Show what will change to get everything consistent:

```
SYNC PLAN
==========
Issues: 3

1. specs/data-model.spec.yaml: v1.2.0 → v1.3.0
   Reason: Modified in this release cycle but not bumped.
   Changes: Payment entity added.

2. specs/business-domain.spec.yaml: v1.2.0 → v1.3.0
   Reason: References updated Payment entity from data-model v1.3.0.

3. CHANGELOG.md: Latest entry v1.2.3, project is v1.3.0
   Reason: Changelog wasn't updated after bump.

Apply all fixes? [y/N]
```

### 6.3 Apply
Update each file. Cross-validate after (no new inconsistencies introduced).

---

## Output Format (all actions)

```
SDD VERSION — <Action Complete>
================================
<action-specific fields>
Next: <what to do next>
```

## Constraints

### Absolute
- NEVER run before `/sdd-spec-update`. Specs must be current before versions are bumped.
- NEVER auto-push git tags. User confirms and pushes manually.
- NEVER auto-bump MAJOR without user confirmation. MAJOR = breaking change = user MUST acknowledge.
- NEVER skip CHANGELOG.md update when bumping. Every version bump gets a changelog entry.
- NEVER bump a spec file that hasn't changed. Artificially inflated versions break traceability.
- ALWAYS use annotated tags for releases. Lightweight tags reserved for temporary markers only.

### Edge cases
- **No git tags exist yet**: Start from the initial commit. "No previous tags found. First release. Suggested version: 1.0.0."
- **No conventional commits in git log**: Auto-detection fails. Ask user to specify bump type explicitly.
- **CHANGELOG.md doesn't exist**: Create it with Keep a Changelog format. First entry is the current version.
- **Version conflict**: Two files at different versions that both need bumps. Bump each independently based on its own change type. Project version takes the HIGHEST bump.
- **Pre-release to release**: `1.3.0-rc.1` → `1.3.0`. Drop the pre-release suffix. Tag both if the rc was tagged.
- **Uncommitted changes at tag time**: "Uncommitted changes found. Commit all changes before creating a tag." Show `git status`.

### Integration with sdd-implement
- Called at Phase 8 (after spec update + doc sync, before PR).
- Receives: task board (for changelog cross-reference), list of changed spec files, bump type from orchestrator.
- Returns: new version, changelog entry, tag name. These feed into Phase 9 PR body.

### Semver Reference
See `docs/versioning-best-practices.md` for full semver rules, edge cases, and anti-patterns.
