#!/usr/bin/env node
/**
 * redirect-bash-to-tools.cjs — PreToolUse hook (matcher: Bash|PowerShell)
 *
 * Blocks Bash/PowerShell commands that duplicate dedicated tools.
 * Dedicated tools (Read, Grep, Glob) are more token-efficient because:
 * - Their output is structured and doesn't count as "user input" verbatim
 * - They integrate with the permission UI
 * - They handle large outputs gracefully (truncation, pagination)
 *
 * Blocked patterns (standalone — NOT when piped):
 *   cat <file>           → use Read
 *   grep <pattern> <file> → use Grep
 *   find ... -name ...   → use Glob
 *   ls / dir             → use Glob (for finding files)
 *   head <file>          → use Read with limit
 *   tail <file>          → use Read with offset + limit
 *   wc -l <file>         → use Read + count lines in response
 *   echo <content>        → just output directly (don't use Bash to "say" things)
 *
 * Allowed (always):
 *   Piped commands        → legitimate shell pipelines
 *   git, npm, yarn, pnpm  → no dedicated tool equivalent
 *   docker, kubectl, etc. → infrastructure
 *   Actual shell logic    → loops, conditionals, redirects, subshells
 *
 * Place in: ~/.claude/hooks/redirect-bash-to-tools.cjs
 * Register in: ~/.claude/settings.json under hooks.PreToolUse with matcher: "Bash|PowerShell"
 */

const fs = require('fs');

// ── Pattern definitions ──────────────────────────────────────────────────────

/**
 * Each rule: { pattern: RegExp, tool: 'Read'|'Grep'|'Glob', description: string }
 * Only blocked when the command is NOT part of a pipeline.
 */
const REDIRECT_RULES = [
  // cat — only when reading a specific file (not piped, no flags that modify behavior)
  {
    pattern: /^\s*cat\s+(?:-[\w]+\s+)*['"]?([^\s|>;<'"]+)['"]?\s*$/,
    tool: 'Read',
    description: 'Use Read tool instead of cat — it handles large files better and is more token-efficient',
  },
  // cat with multiple files (concatenation) — less common, still redirect
  {
    pattern: /^\s*cat\s+(?:-[\w]+\s+)*((?:['"]?[^\s|>;<'"]+['"]?\s+)+)$/,
    tool: 'Read',
    description: 'Use Read tool for each file instead of cat — better pagination and error handling',
  },

  // grep on a specific file (not piped, not -r recursive)
  {
    pattern: /^\s*grep\s+(?:-[a-zA-Z]+\s+)*(['"][^'"]+['"]|\S+)\s+(['"]?[^\s|>;<'"]+['"]?)\s*$/,
    tool: 'Grep',
    description: 'Use Grep tool instead of bash grep — output is structured and integrates with file links',
  },
  // grep -r (recursive) — redirect to Grep with path
  {
    pattern: /^\s*grep\s+-r\w*\s+(?:-[a-zA-Z]+\s+)*(['"][^'"]+['"]|\S+)\s+(['"]?[^\s|>;<'"]+['"]?)\s*$/,
    tool: 'Grep',
    description: 'Use Grep tool with a path instead of grep -r — structured output with file links',
  },

  // rg (ripgrep) — same as grep redirect
  {
    pattern: /^\s*rg\s+(?:-[a-zA-Z]+\s+)*(['"][^'"]+['"]|\S+)\s+(['"]?[^\s|>;<'"]+['"]?)\s*$/,
    tool: 'Grep',
    description: 'Use Grep tool instead of rg — integrates with permission UI and file links',
  },

  // find with -name (simple file search)
  {
    pattern: /^\s*find\s+(['"]?[^\s|>;<'"]+['"]?)\s+-name\s+(['"][^'"]+['"]|\S+)\s*$/,
    tool: 'Glob',
    description: 'Use Glob tool instead of find — faster pattern matching with modification-time sorting',
  },
  // find . -name "pattern" (simplest case)
  {
    pattern: /^\s*find\s+(['"]?[^\s|>;<'"]+['"]?)\s+-name\s+(['"][^'"]+['"]|\S+)\s+(?:-type\s+[fd]\s+)?(?:-print(?:0)?)?\s*$/,
    tool: 'Glob',
    description: 'Use Glob tool instead of find — faster and more token-efficient',
  },

  // head file
  {
    pattern: /^\s*head\s+(?:-n\s*(\d+)\s+)?(['"]?[^\s|>;<'"]+['"]?)\s*$/,
    tool: 'Read',
    description: 'Use Read with limit: N instead of head — handles encoding and large files better',
  },

  // tail file
  {
    pattern: /^\s*tail\s+(?:-n\s*(\d+)\s+)?(['"]?[^\s|>;<'"]+['"]?)\s*$/,
    tool: 'Read',
    description: 'Use Read with offset + limit instead of tail — read from the end of the file efficiently',
  },

  // wc -l (counting lines)
  {
    pattern: /^\s*wc\s+-l\s+(['"]?[^\s|>;<'"]+['"]?)\s*$/,
    tool: 'Read',
    description: 'Use Read tool — the line count is shown in the output. Or use Glob/Grep to find what you need without counting',
  },

  // ls / dir (basic listing — use Glob for pattern matching)
  {
    pattern: /^\s*(?:ls|dir)\s+(?:-la?\s+)?(['"]?[^\s|>;<'"]+['"]?)\s*$/,
    tool: 'Glob',
    description: 'Use Glob tool instead of ls — returns sorted, structured file listings',
  },

  // echo (using bash just to output text — wasteful)
  {
    pattern: /^\s*echo\s+.+$/,
    tool: 'Text',
    description: 'Output text directly in your response instead of using echo in Bash — saves a tool call entirely',
  },

  // PowerShell: Get-ChildItem -Recurse (same as ls/find)
  {
    pattern: /^\s*(?:Get-ChildItem|gci|ls|dir)\s+(?:-[a-zA-Z]+\s+)*-(?:Recurse|r)\s*(?:-[a-zA-Z]+\s+)*(['"]?[^\s|>;<'"]+['"]?)?\s*$/i,
    tool: 'Glob',
    description: 'Use Glob tool with ** patterns instead of Get-ChildItem -Recurse — more efficient and token-friendly',
  },

  // PowerShell: Select-String (same as grep)
  {
    pattern: /^\s*(?:Select-String|sls)\s+(?:-[a-zA-Z]+\s+)*(['"][^'"]+['"]|\S+)\s+(?:-[a-zA-Z]+\s+)*(['"]?[^\s|>;<'"]+['"]?)\s*$/i,
    tool: 'Grep',
    description: 'Use Grep tool instead of Select-String — structured output with file links',
  },

  // PowerShell: Get-Content (same as cat)
  {
    pattern: /^\s*(?:Get-Content|gc|cat|type)\s+(?:-[a-zA-Z]+\s+)*(['"]?[^\s|>;<'"]+['"]?)\s*$/i,
    tool: 'Read',
    description: 'Use Read tool instead of Get-Content/cat — handles large files with automatic pagination',
  },
];

// Commands that are always allowed (pipeline, infrastructure, package management, etc.)
const ALWAYS_ALLOW_PREFIXES = [
  'git ', 'npm ', 'yarn ', 'pnpm ', 'npx ',
  'docker ', 'kubectl ', 'k9s ', 'helm ',
  'python ', 'python3 ', 'node ', 'ruby ', 'go ', 'cargo ', 'rustc ',
  'ssh ', 'scp ', 'rsync ', 'curl ', 'wget ',
  'gh ', 'gcloud ', 'aws ', 'az ', 'terraform ', 'tofu ', 'ansible ',
  'psql ', 'mysql ', 'sqlite3 ', 'redis-cli ',
  'make ', 'cmake ', 'bazel ', 'gradle ', 'mvn ',
  'systemctl ', 'service ', 'brew ', 'choco ', 'scoop ', 'winget ',
  'which ', 'where ', 'whereis ', 'type ',
  'cd ', 'pushd ', 'popd ',
  'export ', 'set ', 'unset ',
  'source ', '. ',
];

// ── Helpers ──────────────────────────────────────────────────────────────────

function hasPipe(command) {
  // Check for pipe outside of quotes
  let inSingle = false, inDouble = false;
  for (let i = 0; i < command.length; i++) {
    const c = command[i];
    if (c === "'" && !inDouble) inSingle = !inSingle;
    if (c === '"' && !inSingle) inDouble = !inDouble;
    if (c === '|' && !inSingle && !inDouble) return true;
  }
  return false;
}

function hasRedirect(command) {
  // Check for > or >> or < outside of quotes
  let inSingle = false, inDouble = false;
  for (let i = 0; i < command.length; i++) {
    const c = command[i];
    if (c === "'" && !inDouble) inSingle = !inSingle;
    if (c === '"' && !inSingle) inDouble = !inDouble;
    if ((c === '>' || c === '<') && !inSingle && !inDouble) return true;
  }
  return false;
}

function isAlwaysAllowed(command) {
  const trimmed = command.trimStart();
  for (const prefix of ALWAYS_ALLOW_PREFIXES) {
    if (trimmed.startsWith(prefix)) return true;
  }
  return false;
}

// ── Main ─────────────────────────────────────────────────────────────────────

function main() {
  try {
    const chunks = [];
    process.stdin.setEncoding('utf8');
    process.stdin.on('readable', function () {
      let chunk;
      while ((chunk = process.stdin.read()) !== null) {
        chunks.push(chunk);
      }
    });

    process.stdin.on('end', function () {
      let input;
      try {
        input = JSON.parse(chunks.join(''));
      } catch (e) {
        process.stdout.write(JSON.stringify({
          hookSpecificOutput: {
            hookEventName: 'PreToolUse',
            permissionDecision: 'allow',
          },
        }) + '\n');
        return;
      }

      const toolName = input.tool_name;
      const toolInput = input.tool_input || {};
      const command = toolInput.command || '';

      // Only intercept Bash and PowerShell
      if (toolName !== 'Bash' && toolName !== 'PowerShell') {
        process.stdout.write(JSON.stringify({
          hookSpecificOutput: {
            hookEventName: 'PreToolUse',
            permissionDecision: 'allow',
          },
        }) + '\n');
        return;
      }

      // No command — allow
      if (!command || command.trim() === '') {
        process.stdout.write(JSON.stringify({
          hookSpecificOutput: {
            hookEventName: 'PreToolUse',
            permissionDecision: 'allow',
          },
        }) + '\n');
        return;
      }

      // Always-allow prefixes (git, npm, docker, etc.)
      if (isAlwaysAllowed(command)) {
        process.stdout.write(JSON.stringify({
          hookSpecificOutput: {
            hookEventName: 'PreToolUse',
            permissionDecision: 'allow',
          },
        }) + '\n');
        return;
      }

      // Pipeline or redirect — allow (legitimate shell usage)
      if (hasPipe(command) || hasRedirect(command)) {
        process.stdout.write(JSON.stringify({
          hookSpecificOutput: {
            hookEventName: 'PreToolUse',
            permissionDecision: 'allow',
          },
        }) + '\n');
        return;
      }

      // Check against redirect rules
      for (const rule of REDIRECT_RULES) {
        if (rule.pattern.test(command)) {
          const reason = [
            `This bash command duplicates a dedicated tool that is more token-efficient.`,
            ``,
            `${rule.description}.`,
            ``,
            `Command blocked: \`${command.trim()}\``,
            `Use the \`${rule.tool}\` tool instead.`,
          ].join('\n');

          process.stdout.write(JSON.stringify({
            hookSpecificOutput: {
              hookEventName: 'PreToolUse',
              permissionDecision: 'deny',
              permissionDecisionReason: reason,
            },
          }) + '\n');
          return;
        }
      }

      // No rule matched — allow
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: {
          hookEventName: 'PreToolUse',
          permissionDecision: 'allow',
        },
      }) + '\n');
    });
  } catch (e) {
    process.stdout.write(JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'PreToolUse',
        permissionDecision: 'allow',
      },
    }) + '\n');
  }
}

main();
