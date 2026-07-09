# Versioning Best Practices — SDD Environment

Research-backed reference for semantic versioning in spec-driven development. Informs `/sdd-version` command behavior.

---

## Semantic Versioning 2.0.0 (Semver)

### Core Rules

Given version `MAJOR.MINOR.PATCH`:

| Bump | When | Examples |
|------|------|----------|
| **MAJOR** (X+1.0.0) | Backward-incompatible changes | Remove endpoint, change response schema, rename field, drop table column, change auth requirement |
| **MINOR** (X.Y+1.0) | Backward-compatible new functionality | Add endpoint, add optional field, add entity, deprecate (but don't remove) |
| **PATCH** (X.Y.Z+1) | Backward-compatible bug fixes | Fix incorrect status code, fix validation, fix typo in error message, performance improvement |

### Edge Cases

| Scenario | Bump Type | Rationale |
|----------|-----------|-----------|
| Internal refactoring (no API change) | PATCH (or MINOR if substantial) | No user-visible behavior change. MINOR acceptable for major internal rewrites (new architecture, new patterns) |
| Add optional field to response | MINOR | Backward-compatible addition |
| Make optional field required | MAJOR | Existing clients may break |
| Fix a bug that clients may have depended on | MAJOR or PATCH (judgment) | If widely relied-upon buggy behavior, MAJOR with migration note. If obscure bug nobody depends on, PATCH. Semver FAQ: "use your best judgment." |
| Add new validation (reject previously-accepted input) | MAJOR | Previously-working requests now fail |
| Relax validation (accept previously-rejected input) | MINOR | More permissive = backward-compatible |
| Deprecate functionality (but keep it working) | MINOR | Deprecation is NOT breaking. MUST remain for at least one MINOR release before removal in MAJOR. |
| Change error message format | MAJOR if clients parse errors, PATCH otherwise | Depends on documented contract |
| Change HTTP status code for existing response | MAJOR | Clients may depend on specific codes |
| Add rate limit header | MINOR | New header, no behavior change |
| Change rate limit value | MAJOR | Behavior change for rate-limited clients |
| Security fix that changes behavior | MINOR if additive, MAJOR if restrictive | New required header = MAJOR |

### Version String Rules

From the semver 2.0.0 specification:

- **No leading zeroes:** `1.02.3` is invalid. Use `1.2.3`.
- **Numeric increase:** Each element must increase numerically: `1.9.0 → 1.10.0 → 1.11.0`.
- **Immutability:** Once a version is released, its contents MUST NOT be modified. Any change requires a new version.
- **The `v` prefix is NOT part of SemVer:** `v1.2.3` is a git tag convention. The actual version is `1.2.3`.
- **Build metadata is ignored for precedence:** `1.0.0+build.42` equals `1.0.0+build.99` in precedence comparisons.

### Pre-Release Versioning

Standard semver pre-release identifiers (from semver 2.0.0 spec):

```
Precedence order (lowest to highest):
1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-alpha.beta < 1.0.0-beta < 1.0.0-beta.2 < 1.0.0-beta.11 < 1.0.0-rc.1 < 1.0.0
```

**Conventions:**
- `alpha` — Internal testing. Features incomplete. Known bugs expected.
- `beta` — External testing. Feature-complete. Bugs being fixed.
- `rc` (release candidate) — Final testing. No planned changes. Only critical bug fixes.

**Numbering:**
- `X.Y.Z-alpha.1`, `X.Y.Z-alpha.2`, ... — sequential alpha builds
- `X.Y.Z-beta.1`, `X.Y.Z-beta.2`, ... — sequential beta builds
- `X.Y.Z-rc.1`, `X.Y.Z-rc.2`, ... — sequential release candidates

**Critical pitfall — always use dot separator:**
```
✅ alpha.1 < alpha.2 < alpha.11  (numeric comparison — correct)
❌ alpha1 > alpha11 > alpha2     (lexicographic comparison — WRONG)
```
Without the dot, `alpha11` sorts BEFORE `alpha2` lexicographically. Always use `.N` dot-separated numeric counters.

**SDD application:** Spec files rarely use pre-release versions. Use pre-release for:
- Specs that are being drafted but not yet locked: `0.1.0-draft`
- Specs undergoing major revision: `1.0.0-rc.1` before locking at `1.0.0`

---

## Changelog Format

### Keep a Changelog (recommended)

Based on [keepachangelog.com](https://keepachangelog.com) v1.1.0.

```markdown
# Changelog

All notable changes to this project will be documented in this file.

## [1.3.0] - 2026-07-09

### Added
- Payment webhook endpoint (POST /api/v1/payments/webhook) [API-TASK-004]
- Rate limiting on auth endpoints [SEC-TASK-003]

### Changed
- User model: `name` split into `firstName` and `lastName` [DM-TASK-002]

### Deprecated
- POST /api/v1/webhooks/legacy-endpoint — use /api/v1/payments/webhook instead [API-TASK-001]

### Removed
- (none)

### Fixed
- Token refresh race condition under concurrent requests [API-TASK-002]
- Missing CORS header on upload endpoint [SEC-TASK-005]

### Security
- Input sanitization on all user-facing fields [MAESTRO-001]
```

**Rules:**
- Each entry references the spec task ID that generated it (`[API-TASK-004]`)
- Entries grouped by type: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`
- Most recent version at top
- Dates in ISO 8601 format (`YYYY-MM-DD`)
- Link versions to git tags (if hosted on GitHub/GitLab)
- Always include an `[Unreleased]` section at the top for work-in-progress changes
- Mark pulled releases with `[YANKED]` after the date: `## [1.2.0] - 2026-07-05 [YANKED]`
- Write for humans, not machines. Describe WHAT changed for users, not what you did as a developer

### Spec-File Inline Changelog

Spec files maintain their own inline changelog in YAML comment blocks (defined in `spec.template.yaml`):

```yaml
# CHANGELOG:
#   1.3.0 (2026-07-09): Added payment webhook AC-012, deprecated legacy endpoint
#   1.2.0 (2026-07-05): Added Stripe integration entities
#   1.1.0 (2026-07-03): Added rate limiting constraints
#   1.0.0 (2026-07-01): Initial locked spec from code analysis
```

**Rules:**
- Spec changelog is concise — one line per version. Detail lives in CHANGELOG.md.
- Cross-reference: spec changelog references acceptance criteria IDs. CHANGELOG.md references task IDs.
- Spec version bumps are INDEPENDENT of other spec files (each spec has its own version).
- CHANGELOG.md represents the PROJECT release version (which may bundle multiple spec bumps).

---

## Git Tag Conventions

### Naming

| Type | Format | Example |
|------|--------|---------|
| Release tag | `v<semver>` | `v1.3.0` |
| Pre-release tag | `v<semver>-<identifier>.<N>` | `v1.3.0-rc.1` |
| Build metadata (rare) | `v<semver>+<metadata>` | `v1.3.0+build.42` |

**The `v` prefix:** Use it. It's the universal convention (Git itself, GitHub Releases, npm, Go modules all expect it). Tags without `v` (bare `1.3.0`) cause issues with some tools.

### Annotated vs Lightweight

**Always use annotated tags** for releases:
```bash
git tag -a v1.3.0 -m "Release v1.3.0: payment webhook, rate limiting"
```

Annotated tags store: tagger name, email, date, message. Lightweight tags are just a pointer to a commit — no metadata.

**Annotated tags enable:**
- `git describe` (returns `v1.3.0-3-gabc1234` — how far from the tag)
- GitHub Releases (auto-creates from annotated tags)
- `git tag -l --sort=-creatordate` (sort by tag date)

Lightweight tags are for temporary/private markers only.

### Signing

Sign tags when:
- You have a GPG key set up
- The project requires signed releases (enterprise/government)
- You're publishing to a package registry that verifies signatures (npm, PyPI optional)

```bash
git tag -s v1.3.0 -m "Release v1.3.0"
```

Not signing is acceptable for internal/team projects. Most open-source projects don't sign tags.

### Tag Messages

Tag messages should be concise but informative:
```
Release v1.3.0

- Added: payment webhook (API-TASK-004)
- Fixed: token refresh race condition (API-TASK-002)
- Specs: api-surface v0.1.0→v0.2.0, data-model v0.1.0→v0.1.1
```

---

## Multi-File Version Synchronization

### The Problem

An SDD project has multiple versioned files:
- 5+ spec files (each with independent versions)
- `package.json` / `pyproject.toml` / `Cargo.toml` (project version)
- `CHANGELOG.md` (project changelog)
- Git tags (project releases)

These versions MUST be consistent. Inconsistent versions cause:
- Confusion about what spec describes what code state
- Broken traceability between tasks, commits, and releases
- Impossible to determine "what changed when"

### Synchronization Strategy

**Rule 1: Spec files are independently versioned.**
Each spec file tracks its own version based on changes to THAT domain:
- Adding a payment endpoint → bump `api-surface.spec.yaml` (MINOR)
- Adding a payment entity → bump `data-model.spec.yaml` (MINOR)
- No changes to security → `security.constitution.yaml` stays at current version

**Rule 2: Project version aligns with the primary spec.**
The project's `package.json` version should match the API surface spec version in most cases. If there's no API spec, use the business-domain spec.

**Rule 3: Bump cascading.**
When one spec bumps, dependent specs may need bumps:
- `api-surface` MAJOR bump → `deployment.spec.yaml` gets at least MINOR (API migration affects deployment)
- `data-model` MAJOR bump → `business-domain.spec.yaml` gets at least MINOR (entities changed)
- `security.constitution.yaml` is INDEPENDENT — it tracks project-specific security additions, not code changes

**Rule 4: CHANGELOG.md = project release version.**
CHANGELOG.md version = `package.json` version = git tag version (without the `v`).
Spec file versions are recorded in the CHANGELOG.md entry description.

### Version Matrix Example

```
Project release: v1.3.0
├── package.json:                    1.3.0
├── CHANGELOG.md:                    1.3.0 entry at top
├── specs/api-surface.spec.yaml:     1.3.0 (MINOR — added webhook endpoint)
├── specs/data-model.spec.yaml:      1.2.1 (PATCH — added index)
├── specs/business-domain.spec.yaml: 1.2.0 (no change)
├── specs/security.constitution.yaml: 1.1.0 (no change)
├── specs/deployment.spec.yaml:      1.1.0 (no change)
└── Git tag:                         v1.3.0
```

---

## Spec Version vs Software Version

### The Relationship

| Concept | Version source | What it describes |
|---------|---------------|-------------------|
| **Spec version** | Each spec file's `metadata.version` | Version of the specification document itself |
| **Software version** | `package.json` / `pyproject.toml` / git tag | Version of the running software |

**They are related but independent.**

### Recommendation: Align on releases

For most SDD projects, align the primary spec version with the software release version:

```
Software v1.3.0 ships with:
- api-surface spec v1.3.0 (describes the 1.3.0 API)
- data-model spec v1.2.1 (hasn't changed since 1.2.1)
- security constitution v1.1.0 (hasn't changed since 1.1.0)
```

This makes it obvious: "What API spec matches software v1.3.0? → api-surface v1.3.0."

### Alternative: Independent versioning

For large projects with independent teams per domain, spec versions may diverge from software versions:

```
Software v5.2.1 ships with:
- api-surface spec v12.3.0 (API team iterates fast)
- data-model spec v8.1.0 (DB team has own cadence)
- security constitution v3.0.0 (security reviews are quarterly)
```

This is valid but harder to trace. Requires a version compatibility matrix.

### SDD Recommendation

**Align on releases.** Keep spec versions in sync with software versions for traceability. A spec that didn't change keeps its old version — don't artificially bump it. But when a spec DOES change, its new version should match the software release it ships with.

---

## Common Pitfalls & Anti-Patterns

| Pitfall | Why It's Bad | Correct Approach |
|---------|-------------|-----------------|
| **0.x versioning forever** | Semver rules differ for 0.x (anything can change). Projects stuck at 0.x never commit to stability. | Release 1.0.0 when the API is stable enough for external consumers. |
| **Bumping MAJOR for every breaking change without migration path** | Users can't upgrade. They stay on old versions. Ecosystem fragments. | Deprecate first (MINOR), then remove later (MAJOR). Give migration window. |
| **"This is just a small breaking change" → MINOR bump** | Breaks semver contract. Downstream tooling (npm, cargo) treats MINOR as safe to auto-update. | If it breaks ANY documented behavior = MAJOR. No exceptions. |
| **Bumping version in a single file only** | Spec says v1.3.0, package.json says v1.2.8, CHANGELOG.md says v1.1.0. Chaos. | Always coordinate. `/sdd-version` exists for this reason. |
| **Commit messages as changelog** | `git log` is not a changelog. It includes WIP, reverts, and noise. | Maintain CHANGELOG.md. Human-written, human-readable. |
| **Date-based versions without semver** | `v2026.07.09` tells you when it was released, not what changed. No compatibility signal. | Use semver. Date stamps can be build metadata: `1.3.0+20260709`. |
| **Version inflation** | "We did a lot of work so it's 2.0.0 now." Version numbers signal compatibility, not effort. | Bump based on WHAT changed, not HOW MUCH changed. |
| **Skipping versions** | Jumping from 1.0.0 to 2.0.0 with no 1.x releases. | Every MAJOR should have at least one MINOR release first. |

---

## Versioning in SDD Context

### Spec File Lifecycle Versions

```
0.1.0-draft    → Spec being written (from /sdd-spec-start or /sdd-spec-check)
0.1.0-locked   → Spec finalized, ready for implementation
1.0.0-locked   → First stable release
1.1.0-locked   → MINOR update (new features)
2.0.0-locked   → MAJOR update (breaking changes)
1.0.0-stale    → Spec no longer matches code (requires /sdd-spec-update)
```

### When to Bump in the SDD Pipeline

The version bump happens at Phase 8 — AFTER spec update and doc sync, BEFORE PR creation:

1. `/sdd-spec-update` reconciles specs with code. Each spec gets individual version bumps based on its changes.
2. Scribe syncs docs. No version changes here.
3. `/sdd-version` coordinates: bumps project version, updates CHANGELOG.md, creates git tag.
4. PR includes ALL version changes together.

### Version Traceability

Every version change must be traceable:
- Spec version bump → changelog entry references AC IDs
- CHANGELOG.md entry → references task IDs
- Git tag → references CHANGELOG.md version
- Commit → references task ID
- PR → references all of the above

This creates a complete chain: `git tag → changelog → task → spec → acceptance criterion`.
