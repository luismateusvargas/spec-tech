#!/bin/bash
# handoff-precompact.sh — PreCompact hook
# Forces an emergency handoff save before autocompaction.
# Creates HANDOFF.md if it doesn't exist.

HANDOFF_FILE="${CLAUDE_PROJECT_DIR}/HANDOFF.md"

if [ ! -f "$HANDOFF_FILE" ]; then
  cat > "$HANDOFF_FILE" << 'EOF'
# HANDOFF.md

## Session State (auto-saved before compaction)
**Last updated:** $(date -u '+%Y-%m-%dT%H:%M:%SZ')

**Status:** Active session was compacted.

## Current Focus
<!-- What was being worked on -->

## Completed
<!-- What was finished -->

## Pending
<!-- What remains -->

## Decisions Made
<!-- Key decisions and rationale -->

## Files Changed
<!-- Full paths of modified files -->

## Blockers / Questions
<!-- Anything blocking or unresolved -->
EOF
  echo "Created new HANDOFF.md"
fi

echo "PreCompact: HANDOFF safeguard written"
