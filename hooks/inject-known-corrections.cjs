#!/usr/bin/env node
/**
 * inject-known-corrections.cjs — UserPromptSubmit hook
 *
 * Reads the persistent command-corrections.json file and injects
 * known bad command patterns into Claude's context so it NEVER
 * repeats the same command mistakes.
 *
 * Companion to catch-command-errors.cjs (PostToolUse), which writes
 * corrections when commands fail.
 *
 * Place in: ~/.claude/hooks/inject-known-corrections.cjs
 * Register in: ~/.claude/settings.json under hooks.UserPromptSubmit
 */

var fs = require('fs');
var path = require('path');
var os = require('os');

var CORRECTIONS_FILE = path.join(os.homedir(), '.claude', 'hooks', 'command-corrections.json');

function readCorrections() {
  try {
    if (fs.existsSync(CORRECTIONS_FILE)) {
      var raw = fs.readFileSync(CORRECTIONS_FILE, 'utf8');
      return JSON.parse(raw);
    }
  } catch (e) {}
  return { corrections: {} };
}

function main() {
  var data = readCorrections();
  var keys = Object.keys(data.corrections);

  if (keys.length === 0) {
    // No corrections to inject
    process.stdout.write(JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'UserPromptSubmit',
        additionalContext: ''
      }
    }) + '\n');
    return;
  }

  // Sort by occurrences (most frequent first) and recency
  keys.sort(function(a, b) {
    var ca = data.corrections[a];
    var cb = data.corrections[b];
    // Prioritize frequent offenders
    if (cb.occurrences !== ca.occurrences) {
      return cb.occurrences - ca.occurrences;
    }
    // Then by recency
    return (cb.lastSeen || '').localeCompare(ca.lastSeen || '');
  });

  // Take top 10 to keep injection compact
  var topKeys = keys.slice(0, 10);

  var lines = [
    '',
    '---',
    '## 🚫 KNOWN COMMAND CORRECTIONS — DO NOT REPEAT THESE MISTAKES',
    '',
    'The following commands have FAILED in previous sessions. You MUST NOT use them.',
    'Use the CORRECTED version instead. These were learned from actual errors.',
    '',
  ];

  for (var i = 0; i < topKeys.length; i++) {
    var key = topKeys[i];
    var entry = data.corrections[key];
    var occ = entry.occurrences;
    var occLabel = occ === 1 ? '1 failure' : occ + ' failures';

    lines.push('**BAD:** `' + key + '`  ');
    lines.push('→ **USE:** `' + entry.correction + '`  ');
    lines.push('  _Reason: ' + entry.reason + ' (' + occLabel + ')_  ');
    lines.push('');
  }

  if (keys.length > 10) {
    lines.push('_(' + (keys.length - 10) + ' more corrections not shown — check ' + CORRECTIONS_FILE + ')_');
    lines.push('');
  }

  lines.push('**Before running ANY command, mentally verify:**');
  lines.push('1. Is the command name spelled correctly?');
  lines.push('2. Are the flags valid for this command? (check with `command --help` if unsure)');
  lines.push('3. Is this a command that should use a dedicated tool instead? (Read, Grep, Glob)');
  lines.push('---');

  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'UserPromptSubmit',
      additionalContext: lines.join('\n')
    }
  }) + '\n');
}

main();
