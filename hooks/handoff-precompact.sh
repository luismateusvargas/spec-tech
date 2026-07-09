#!/bin/bash
# handoff-precompact.sh — PreCompact hook
# Forces an emergency handoff save before autocompaction.
# Place in: ~/.claude/hooks/handoff-precompact.sh
# chmod +x ~/.claude/hooks/handoff-precompact.sh

HANDOFF_FILE="${CLAUDE_PROJECT_DIR}/HANDOFF.md"

if [ ! -f "$HANDOFF_FILE" ]; then
  cat > "$HANDOFF_FILE" << EOF
# HANDOFF.md

## Session State (auto-saved before compaction)
**Last updated:** $(date -u '+%Y-%m-%dT%H:%M:%SZ')

**Status:** Active session was compacted. Handoff below may be stale — Claude should read current state before continuing.

## Current Focus
<!-- Describe what was being worked on -->

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

echo "PreCompact: HANDOFF.md exists at $HANDOFF_FILE"