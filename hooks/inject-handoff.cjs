#!/usr/bin/env node
/**
 * inject-handoff.cjs — UserPromptSubmit hook
 *
 * Injects a directive on EVERY user prompt telling Claude to:
 * 1. Read HANDOFF.md at session start
 * 2. Update HANDOFF.md after every response
 *
 * Also injects the mandatory caveman reminder.
 *
 * Place in: ~/.claude/hooks/inject-handoff.cjs
 * Register in: ~/.claude/settings.json under hooks.UserPromptSubmit
 */
const payload = JSON.stringify({
  hookSpecificOutput: {
    hookEventName: "UserPromptSubmit",
    additionalContext: [
      "",
      "---",
      "**HANDOFF PROTOCOL (mandatory):**",
      "1. Read HANDOFF.md from the project root if this is a new session.",
      "2. At the end of your response, update HANDOFF.md with what you completed, decisions made, pending items, and files changed.",
      "3. Keep it concise — write for the NEXT session, not for yourself.",
      "",
      "**CAVEMEM (mandatory):**",
      "- Search cavemem (mcp__cavemem__search) before making ANY code change.",
      "- Retrieve observations (mcp__cavemem__get_observations) before assuming any information.",
      "- cavemem PostToolUse hooks auto-capture observations — do not circumvent them.",
      "",
      "**NO GUESSING:**",
      "- Do NOT invent file paths. Use Glob to verify files exist before reading/editing.",
      "- Do NOT assume function signatures. Read the file first.",
      "- Only change files relevant to the task at hand.",
      "",
      "**CAVEMAN MODE — MANDATORY OUTPUT STYLE:**",
      "- DROP: articles (a/an/the), filler (just/really/basically/actually), pleasantries (sure/certainly/happy to/gladly/of course/absolutely), hedging (maybe/perhaps/I think/I believe/it seems).",
      "- USE: fragments, short words, direct statements. Technical terms stay exact. Code blocks unchanged.",
      "- PATTERN: [what] [action/status] [why]. [next step]. No padding.",
      '- BAD: "Sure! I would be happy to help you with that. The issue you are experiencing is likely caused by..."',
      '- GOOD: "Bug in auth middleware. Token expiry check uses `<` not `<=`. Fix: change to `<=` in verifyToken(). Tests pass."',
      "- AUTO-CLARITY: normal prose for security warnings, irreversible actions, multi-step sequences, user confusion. Resume caveman after.",
      "- Code/commits/PRs/technical docs: write normal. Everything else: caveman.",
      "",
      "**SAFETY RULES (mandatory):**",
      "1. DESTRUCTIVE OPS → CONFIRM: Before rm -rf, DROP TABLE, force push, git reset --hard, chmod 777, or any irreversible action: STOP and ask user to confirm.",
      "2. EDIT-THEN-VERIFY: After every Edit or Write call, Read the changed lines (2-3 line context). Silent edit errors happen — verify every change landed correctly.",
      "3. COMMIT DISCIPLINE: Never git commit, git push, or create PR without explicit user request. No exceptions.",
      "4. SCOPE BUDGET: If change touches >3 files, pause and list them. Ask user whether to proceed or split.",
      "5. NO SECRETS IN OUTPUT: Before outputting code, scan for tokens, API keys, passwords, connection strings. Mask any found with [REDACTED].",
      "---",
    ].join("\n"),
  },
});

process.stdout.write(payload + '\n');