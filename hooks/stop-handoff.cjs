#!/usr/bin/env node
/**
 * stop-handoff.cjs — Stop hook
 *
 * Fires when Claude stops. Only reports when HANDOFF.md needs attention:
 * - HANDOFF.md exists but hasn't been updated in >30 min → warn
 * - In a real project dir (has .git/pkg.json/CLAUDE.md) but no HANDOFF.md → suggest creating one
 * - Otherwise → silent (no noise in home dir or random folders)
 *
 * Place in: ~/.claude/hooks/stop-handoff.cjs
 * Register in: ~/.claude/settings.json under hooks.Stop
 */

var fs = require('fs');
var path = require('path');

var STALE_MINUTES = 30; // Only warn if handoff is older than this

function looksLikeProject(dir) {
  // Check for indicators that this is an actual project directory
  var markers = ['.git', 'package.json', 'CLAUDE.md', 'go.mod', 'Cargo.toml',
                 'pyproject.toml', 'Makefile', 'src/', 'app/', 'lib/'];
  for (var i = 0; i < markers.length; i++) {
    try {
      if (fs.existsSync(path.join(dir, markers[i]))) {
        return true;
      }
    } catch (e) {}
  }
  return false;
}

function main() {
  try {
    var projectDir = process.env.CLAUDE_PROJECT_DIR;
    if (!projectDir) {
      // No project dir — silent
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: { hookEventName: 'Stop', additionalContext: '' }
      }) + '\n');
      return;
    }

    var handoffFile = path.join(projectDir, 'HANDOFF.md');
    var handoffExists = false;
    try { handoffExists = fs.existsSync(handoffFile); } catch (e) {}

    var message = '';

    if (handoffExists) {
      var stat = fs.statSync(handoffFile);
      var ageMinutes = Math.round((Date.now() - stat.mtimeMs) / 60000);

      if (ageMinutes > STALE_MINUTES) {
        message = 'HANDOFF.md not updated in ' + ageMinutes + ' min — may be stale for next session.';
      }
      // If fresh: silent — no need to say "everything is fine"
    } else if (looksLikeProject(projectDir)) {
      message = 'No HANDOFF.md in this project. Create one so the next session knows where to resume.';
    }
    // Not a project dir and no handoff: silent

    process.stdout.write(JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'Stop',
        additionalContext: message,
      }
    }) + '\n');
  } catch (e) {
    // Silent on any error
    process.stdout.write(JSON.stringify({
      hookSpecificOutput: { hookEventName: 'Stop', additionalContext: '' }
    }) + '\n');
  }
}

main();
