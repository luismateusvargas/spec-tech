#!/usr/bin/env node
/**
 * block-attribution-commit.cjs — PreToolUse hook
 *
 * Intercepts `git commit` commands and rejects any commit message
 * that contains attribution-style lines (Co-authored-by, Signed-off-by, etc.).
 *
 * Claude Code generates these automatically; this hook strips them before
 * they land in the repo.
 */

const ATTRIBUTION_PATTERNS = [
  /\bco-authored-by\b/i,
  /\bauthored[-\s]?by\b/i,
  /\bsigned-off-by\b/i,
  /\bapproved[-\s]?by\b/i,
  /\breviewed[-\s]?by\b/i,
  /\bcreated[-\s]?by\b/i,
  /\bhelped[-\s]?by\b/i,
  /\bassisted[-\s]?by\b/i,
  /\bgenerated[-\s]?with\b/i,
  /\bgenerated[-\s]?by\b/i,
  /\bcontributed[-\s]?by\b/i,
  /\backnowledge[-\s]?ments?:?\b/i,
  // Catch the Claude Code auto-attribution specifically
  /Co-Authored-By:\s*Claude/i,
  /🤖\s*Generated with/i,
];

function hasAttributionPattern(message) {
  return ATTRIBUTION_PATTERNS.some(function (re) { return re.test(message); });
}

/**
 * Extract commit message from a git commit command.
 * Handles: -m "msg", -m 'msg', --message "msg", --message='msg', -F file
 * Returns the full message string, or null if it can't be determined.
 */
function extractMessage(command) {
  // Collect all -m arguments (git supports multiple -m for paragraphs)
  var messages = [];
  var mRegex = /(?:-m|--message)\s*(?:=\s*)?("[^"\\]*(?:\\.[^"\\]*)*"|'[^'\\]*(?:\\.[^'\\]*)*'|\S+)/g;
  var match;
  while ((match = mRegex.exec(command)) !== null) {
    var raw = match[1];
    // Strip surrounding quotes
    if ((raw.startsWith('"') && raw.endsWith('"')) ||
        (raw.startsWith("'") && raw.endsWith("'"))) {
      raw = raw.slice(1, -1);
    }
    // Unescape common escapes
    raw = raw.replace(/\\n/g, '\n').replace(/\\"/g, '"').replace(/\\'/g, "'");
    messages.push(raw);
  }

  if (messages.length > 0) {
    return messages.join('\n');
  }

  // Check for -F <file>
  var fMatch = command.match(/(?:-F|--file)\s*(?:=\s*)?(\S+)/);
  if (fMatch) {
    var fs = require('fs');
    var filePath = fMatch[1];
    // Only attempt to read if it looks like a safe path
    try {
      if (fs.existsSync(filePath)) {
        return fs.readFileSync(filePath, 'utf8');
      }
    } catch (e) {
      // Can't read — allow through (editor / template commit, low risk)
    }
  }

  // No -m and no readable -F file — likely editor-based commit.
  // Let it through; attribution risks are low without -m.
  return null;
}

function main() {
  // Read stdin JSON
  var chunks = [];
  process.stdin.setEncoding('utf8');
  process.stdin.on('readable', function () {
    var chunk;
    while ((chunk = process.stdin.read()) !== null) {
      chunks.push(chunk);
    }
  });

  process.stdin.on('end', function () {
    var input;
    try {
      input = JSON.parse(chunks.join(''));
    } catch (e) {
      // Can't parse input — allow
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: {
          hookEventName: 'PreToolUse',
          permissionDecision: 'allow',
        },
      }) + '\n');
      return;
    }

    var toolName = input.tool_name;
    var toolInput = input.tool_input || {};
    var command = toolInput.command || '';

    // Only intercept Bash/PowerShell git commit commands
    if (toolName !== 'Bash' && toolName !== 'PowerShell') {
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: {
          hookEventName: 'PreToolUse',
          permissionDecision: 'allow',
        },
      }) + '\n');
      return;
    }

    // Quick check — does it look like a git commit?
    if (!/git\s+commit\b/.test(command)) {
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: {
          hookEventName: 'PreToolUse',
          permissionDecision: 'allow',
        },
      }) + '\n');
      return;
    }

    var message = extractMessage(command);

    if (message === null) {
      // Can't determine message (editor commit, etc.) — allow
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: {
          hookEventName: 'PreToolUse',
          permissionDecision: 'allow',
        },
      }) + '\n');
      return;
    }

    // Check all patterns against the message
    var violations = [];
    for (var i = 0; i < ATTRIBUTION_PATTERNS.length; i++) {
      var match = message.match(ATTRIBUTION_PATTERNS[i]);
      if (match) {
        violations.push('"' + match[0] + '" (pattern: ' + ATTRIBUTION_PATTERNS[i].source + ')');
      }
    }

    if (violations.length > 0) {
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: {
          hookEventName: 'PreToolUse',
          permissionDecision: 'deny',
          permissionDecisionReason:
            'Commit blocked: message contains attribution pattern(s):\n' +
            violations.map(function (v) { return '  - ' + v; }).join('\n') +
            '\n\nRemove attribution lines (Co-authored-by, Signed-off-by, etc.) and retry.',
        },
      }) + '\n');
      return;
    }

    // Clean — allow
    process.stdout.write(JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'PreToolUse',
        permissionDecision: 'allow',
      },
    }) + '\n');
  });
}

main();
