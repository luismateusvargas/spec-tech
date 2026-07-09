-- SDD Learning Store Schema
-- Database: .claude/learnings.db
-- Engine: SQLite 3.x, WAL mode
-- Access: via better-sqlite3 in Node.js hooks (future migration)
-- Current: JSON file storage at .claude/hooks/learnings.json

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Core learning entries
CREATE TABLE IF NOT EXISTS learnings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Classification
    category    TEXT NOT NULL CHECK(category IN (
                    'spec_error',       -- Spec was factually wrong (CHALLENGE: SPEC_FACTUALLY_WRONG)
                    'spec_incomplete',   -- Spec missed a concern (CHALLENGE: SPEC_INCOMPLETE)
                    'implementation',    -- Implementation insight or pattern
                    'discovery',         -- Discovered opportunity during implementation
                    'decision',          -- Architectural decision (from spec decisions: section)
                    'failure'            -- What was tried and failed
                )),
    subcategory TEXT,                    -- Free-text subcategory for filtering

    -- Content
    title       TEXT NOT NULL,
    description TEXT NOT NULL,           -- What was learned

    -- Context
    project     TEXT NOT NULL,           -- Project directory path
    spec_file   TEXT,                     -- Related spec file (relative path)
    task_id     TEXT,                     -- Related task ID (if applicable)
    challenge_id TEXT,                   -- Related CHALLENGE ID (if from Challenge)

    -- Evidence chain (tracks back to source)
    evidence     TEXT NOT NULL DEFAULT '[]',  -- JSON array of {file, line, summary}
    rationale    TEXT,                    -- WHY this learning matters
    alternatives TEXT DEFAULT '[]',      -- JSON array of alternatives considered

    -- Status
    resolution  TEXT NOT NULL DEFAULT 'accepted' CHECK(resolution IN (
                    'accepted',          -- Incorporated into spec/process
                    'deferred',          -- Postponed to future cycle
                    'rejected',          -- Considered but rejected
                    'experimental'       -- Being tested, not yet adopted
                )),

    -- Metadata
    source      TEXT NOT NULL DEFAULT 'auto' CHECK(source IN (
                    'auto',              -- Auto-captured by hook
                    'manual',            -- Explicitly added by user/command
                    'challenge',         -- From a CHALLENGE verdict
                    'spike',             -- From spike agent findings
                    'opportunity'        -- From discovered_opportunities
                )),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),

    UNIQUE(project, title, created_at)
);

-- Tags for cross-cutting categorization
CREATE TABLE IF NOT EXISTS learning_tags (
    learning_id INTEGER NOT NULL,
    tag         TEXT NOT NULL,
    PRIMARY KEY (learning_id, tag),
    FOREIGN KEY (learning_id) REFERENCES learnings(id) ON DELETE CASCADE
);

-- Decision log (why things were done)
CREATE TABLE IF NOT EXISTS decision_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    learning_id INTEGER,                 -- Optional link to learning entry
    project     TEXT NOT NULL,
    area        TEXT NOT NULL,            -- Domain area (auth, payments, db, etc.)
    decision    TEXT NOT NULL,            -- What was decided
    rationale   TEXT NOT NULL,            -- WHY (must trace to root cause, not consequences)
    alternatives_considered TEXT DEFAULT '[]',
    evidence    TEXT DEFAULT '[]',
    decided_by  TEXT NOT NULL,            -- Who/what made the decision (user, spike, CHALLENGE)
    date        TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (learning_id) REFERENCES learnings(id) ON DELETE SET NULL
);

-- Full-text search via simple LIKE queries (SQLite FTS not needed for this scale)
CREATE INDEX IF NOT EXISTS idx_learnings_category ON learnings(category);
CREATE INDEX IF NOT EXISTS idx_learnings_project ON learnings(project);
CREATE INDEX IF NOT EXISTS idx_learnings_source ON learnings(source);
CREATE INDEX IF NOT EXISTS idx_learnings_resolution ON learnings(resolution);
CREATE INDEX IF NOT EXISTS idx_decision_log_project ON decision_log(project);
CREATE INDEX IF NOT EXISTS idx_decision_log_area ON decision_log(area);

-- Export view (used by /sdd-learnings export --format md)
CREATE VIEW IF NOT EXISTS learning_export AS
SELECT
    l.id,
    l.category,
    l.title,
    l.description,
    l.project,
    l.spec_file,
    l.task_id,
    l.challenge_id,
    l.evidence,
    l.rationale,
    l.alternatives,
    l.resolution,
    l.source,
    l.created_at,
    GROUP_CONCAT(DISTINCT lt.tag, ', ') AS tags
FROM learnings l
LEFT JOIN learning_tags lt ON lt.learning_id = l.id
GROUP BY l.id
ORDER BY l.created_at DESC;
