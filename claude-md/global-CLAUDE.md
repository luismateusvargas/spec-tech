# MANDATORY GLOBAL RULES — applied to ALL projects

## 1. Caveman Memory System (MANDATORY everywhere)

This system has a **cavemem** persistent memory layer. You MUST use it for ALL operations:

- **Before any code change**, call `mcp__cavemem__search` to check if relevant observations exist.
- **Before assuming information**, call `mcp__cavemem__get_observations` to retrieve full context.
- **After completing any task**, the cavemem PostToolUse hook automatically captures observations. Do NOT skip or circumvent it.
- Treat cavemem as the source of truth for cross-session context. Do NOT rely on your own context window alone.

## 2. Cavecrew for Subagent Work

For tasks that require subagents (complex multi-step work, research, review), you MUST delegate using cavecrew:

- **cavecrew-investigator** — for locating code, finding definitions & call sites
- **cavecrew-builder** — for surgical 1-2 file edits
- **cavecrew-reviewer** — for diff review / bug hunting

Before delegating to any subagent, call the cavecrew skill to decide which subagent type to use. Delegation saves context budget and prevents context drift.

## 3. HANDOFF Protocol (EVERY TURN)

This project uses a HANDOFF.md protocol:

- **At session start**: Read the existing HANDOFF.md file from the project root. Resume from where the previous session left off.
- **At the end of every response**: Update HANDOFF.md with:
  1. What was completed this turn
  2. What decisions were made (with rationale)
  3. What is still pending / next actions
  4. Any files changed (full paths)
  5. Any blockers or open questions
- **Keep handoffs concise**: Focus on what the NEXT session needs, not everything you did.
- **Before `/compact` or session end**: Ensure HANDOFF.md is fully updated first.

## 4. No Guessing — Verify Before Acting

You MUST NOT guess file paths, module names, or API signatures. Follow this order:

1. **Search memory first**: `mcp__cavemem__search` for any existing knowledge
2. **Check the graph** (if madar is available for this project): `mcp__graphify-madar__retrieve`
3. **Verify paths**: Use Glob to confirm a file exists before reading or editing it
4. **Verify structure**: Read file headers / imports before assuming what a module exports
5. **Only then**: Make changes

NEVER:
- Invent file paths that don't exist
- Assume function signatures without verifying
- Write code based on a "pattern you've seen" without reading the actual file
- Change files that weren't explicitly requested or aren't directly related to the task

## 5. Scope Discipline

- Only modify files within the project scope you were asked about.
- If a change would affect files in another project (e.g., changing a shared service while working in a client app), ask for confirmation.
- Do not "improve" code unrelated to the task without explicit permission.