#!/usr/bin/env node
/**
 * catch-command-errors.cjs — PostToolUse hook (matcher: Bash|PowerShell)
 *
 * Catches failed shell commands and records them so Claude learns
 * to never repeat the same mistakes. Example: if Claude types "ech0"
 * instead of "echo", this hook captures the failure, records that
 * "ech0" → "echo", and a companion UserPromptSubmit hook injects
 * the correction into future contexts.
 *
 * Corrections are stored persistently in:
 *   ~/.claude/hooks/command-corrections.json
 *
 * Place in: ~/.claude/hooks/catch-command-errors.cjs
 * Register in: ~/.claude/settings.json under hooks.PostToolUse with matcher: "Bash|PowerShell"
 */

var fs = require('fs');
var path = require('path');
var os = require('os');

// ── Configuration ────────────────────────────────────────────────────────────

var CORRECTIONS_FILE = path.join(os.homedir(), '.claude', 'hooks', 'command-corrections.json');

// Max corrections to store (prevent unbounded growth)
var MAX_CORRECTIONS = 50;

// ── Error detectors ──────────────────────────────────────────────────────────

/**
 * Each detector:
 *   test: function(command, stderr, stdout, exitCode) → bool
 *   categorize: function(command, stderr) → { badPattern, correction, reason }
 */

var DETECTORS = [

  // Unix: command not found (e.g., "ech0: command not found")
  {
    name: 'unix-command-not-found',
    test: function(cmd, stderr) {
      return /(?:^|\n)(\S+):\s*(command not found|not found)\b/im.test(stderr);
    },
    categorize: function(cmd, stderr) {
      var m = stderr.match(/(?:^|\n)(\S+):\s*(command not found|not found)/im);
      var badCmd = m ? m[1] : extractBaseCommand(cmd);
      var suggestion = findClosestCommand(badCmd);
      var correction = suggestion
        ? suggestion
        : '[check if this is a typo - did you mean a different command?]';
      var reason = suggestion
        ? badCmd + ': command not found. Did you mean ' + suggestion + '?'
        : badCmd + ': command not found. This command does not exist.';
      return {
        badPattern: badCmd,
        correction: correction,
        reason: reason,
        category: 'typo'
      };
    }
  },

  // Windows: command not recognized (e.g., "'ech0' is not recognized")
  {
    name: 'windows-command-not-recognized',
    test: function(cmd, stderr) {
      return /'(\S+)'\s+is not recognized as an internal or external command/i.test(stderr);
    },
    categorize: function(cmd, stderr) {
      var m = stderr.match(/'(\S+)'\s+is not recognized/i);
      var badCmd = m ? m[1] : extractBaseCommand(cmd);
      var suggestion = findClosestCommand(badCmd);
      var correction = suggestion
        ? suggestion
        : '[check if this is a typo - did you mean a different command?]';
      var reason = suggestion
        ? badCmd + ': not recognized. Did you mean ' + suggestion + '?'
        : badCmd + ': not recognized as a command on Windows.';
      return {
        badPattern: badCmd,
        correction: correction,
        reason: reason,
        category: 'typo'
      };
    }
  },

  // Git: unknown subcommand (e.g., "git: 'pul' is not a git command")
  {
    name: 'git-unknown-command',
    test: function(cmd, stderr) {
      return /git:\s*'(\S+)'\s+is not a git command/i.test(stderr);
    },
    categorize: function(cmd, stderr) {
      var m = stderr.match(/git:\s*'(\S+)'\s+is not a git command/i);
      var badSub = m ? m[1] : '';
      // Map common git typos
      var GIT_CORRECTIONS = {
        'pul': 'pull',
        'psuh': 'push',
        'commt': 'commit',
        'chekout': 'checkout',
        'checout': 'checkout',
        'brach': 'branch',
        'merg': 'merge',
        'rebas': 'rebase',
        'stash': 'stash',
        'statsu': 'status',
        'satus': 'status',
        'log': 'log',
        'dff': 'diff',
        'dif': 'diff',
        'resrt': 'reset',
        'reser': 'reset',
        'clon': 'clone',
        'fetech': 'fetch',
        'fech': 'fetch',
        'swich': 'switch',
        'swtich': 'switch',
        'restroe': 'restore'
      };
      var correction = GIT_CORRECTIONS[badSub] || '[check git help for the correct subcommand]';
      return {
        badPattern: 'git ' + badSub,
        correction: 'git ' + correction,
        reason: 'git ' + badSub + ' is not a valid git command. Use git ' + correction + ' instead.',
        category: 'git-typo'
      };
    }
  },

  // Invalid option/flag (e.g., "unknown option --foo", "illegal option -X")
  {
    name: 'invalid-option',
    test: function(cmd, stderr) {
      return /(?:unknown|invalid|illegal|unrecognized)\s+(?:option|flag|switch)\s*[`"']?\s*[-]{1,2}\s*[\w-]+/im.test(stderr);
    },
    categorize: function(cmd, stderr) {
      var m = stderr.match(/(?:unknown|invalid|illegal|unrecognized)\s+(?:option|flag|switch)\s*[`"']?\s*([-]{1,2}\s*[\w-]+)/im);
      var badFlag = m ? m[1].replace(/\s+/g, '') : '[unknown flag]'; // normalize "-- flag" to "--flag"
      var baseCmd = extractBaseCommand(cmd);
      return {
        badPattern: baseCmd + ' ' + badFlag,
        correction: baseCmd + ' [check --help for valid options]',
        reason: badFlag + ' is not a valid option for ' + baseCmd + '. Check the help for correct flags.',
        category: 'invalid-flag'
      };
    }
  },

  // npm/yarn: unknown command
  {
    name: 'npm-unknown-command',
    test: function(cmd, stderr) {
      return /(?:npm|yarn|pnpm)\s+(?:error|ERR!)?\s*(?:unknown|Unknown)\s+(?:command|Command)/i.test(stderr) ||
             /Usage:\s+npm\s+<command>/i.test(stderr);
    },
    categorize: function(cmd, stderr) {
      var parts = cmd.trim().split(/\s+/);
      var badSub = parts[1] || '[unknown]';
      return {
        badPattern: parts[0] + ' ' + badSub,
        correction: parts[0] + ' [check ' + parts[0] + ' --help for available commands]',
        reason: badSub + ' is not a valid ' + parts[0] + ' command.',
        category: 'npm-typo'
      };
    }
  },

  // Permission denied (e.g., "Permission denied", "EACCES")
  {
    name: 'permission-denied',
    test: function(cmd, stderr, stdout) {
      return /(?:permission denied|EACCES|not permitted|operation not permitted)/im.test(stderr + stdout);
    },
    categorize: function(cmd, stderr) {
      return {
        badPattern: extractBaseCommand(cmd),
        correction: '[needs elevated permissions or different file path]',
        reason: 'Permission denied. This operation requires elevated permissions or the target is protected.',
        category: 'permissions'
      };
    }
  },

  // File not found for operation target (not the command itself)
  {
    name: 'file-not-found',
    test: function(cmd, stderr) {
      return /(?:No such file or directory|cannot access|cannot find|ENOENT)/im.test(stderr) &&
             !/command not found/im.test(stderr);
    },
    categorize: function(cmd, stderr) {
      // Try to extract the filename from the error
      var m = stderr.match(/(?:cannot access|cannot find|ENOENT[:\s]+|No such file or directory[:\s]+)([`"']?)([^`"'\n]+)\1/i);
      var missingFile = m ? m[2] : '[file]';
      return {
        badPattern: missingFile,
        correction: '[verify the file path exists before running the command]',
        reason: 'File not found: ' + missingFile + '. The file does not exist at the specified path.',
        category: 'missing-file'
      };
    }
  },

  // PowerShell: cmdlet not found
  {
    name: 'ps-cmdlet-not-found',
    test: function(cmd, stderr) {
      return /The term '(\S+)' is not recognized as the name of a cmdlet/i.test(stderr);
    },
    categorize: function(cmd, stderr) {
      var m = stderr.match(/The term '(\S+)' is not recognized as the name of a cmdlet/i);
      var badCmd = m ? m[1] : extractBaseCommand(cmd);
      return {
        badPattern: badCmd,
        correction: '[check if this is a typo in the cmdlet/function name]',
        reason: badCmd + ': not recognized as a PowerShell cmdlet, function, or alias.',
        category: 'ps-typo'
      };
    }
  }
];

// ── Common commands for fuzzy matching ───────────────────────────────────────

var COMMON_COMMANDS = [
  // Unix basics
  'ls', 'cd', 'pwd', 'cp', 'mv', 'rm', 'mkdir', 'rmdir', 'touch', 'chmod', 'chown',
  'cat', 'head', 'tail', 'less', 'more', 'grep', 'find', 'locate', 'which', 'whereis',
  'echo', 'printf', 'date', 'cal', 'sleep', 'true', 'false', 'test',
  'sort', 'uniq', 'wc', 'tr', 'cut', 'paste', 'sed', 'awk', 'diff', 'patch',
  'tar', 'gzip', 'gunzip', 'zip', 'unzip', 'curl', 'wget', 'ssh', 'scp', 'rsync',
  'ps', 'kill', 'top', 'htop', 'df', 'du', 'free', 'mount', 'umount',
  'ln', 'readlink', 'stat', 'file', 'basename', 'dirname', 'realpath',
  'xargs', 'tee', 'env', 'export', 'source', 'alias', 'unalias',
  'man', 'help', 'info', 'whatis',
  // Dev tools
  'git', 'npm', 'yarn', 'pnpm', 'npx', 'node', 'python', 'python3', 'ruby', 'perl',
  'make', 'cmake', 'gcc', 'g++', 'clang', 'rustc', 'cargo', 'go', 'java', 'javac',
  'docker', 'kubectl', 'helm', 'terraform', 'ansible',
  'pip', 'pip3', 'gem', 'bundle', 'composer',
  'vim', 'nvim', 'nano', 'emacs', 'code',
  // Windows
  'dir', 'copy', 'del', 'move', 'ren', 'type', 'findstr', 'where',
  'Get-ChildItem', 'Get-Content', 'Set-Content', 'Select-String', 'Invoke-WebRequest',
  'Write-Output', 'Write-Host', 'Get-Process', 'Stop-Process', 'Start-Service'
];

function levenshtein(a, b) {
  if (a.length === 0) return b.length;
  if (b.length === 0) return a.length;
  var matrix = [];
  for (var i = 0; i <= b.length; i++) {
    matrix[i] = [i];
  }
  for (var j = 0; j <= a.length; j++) {
    matrix[0][j] = j;
  }
  for (var i = 1; i <= b.length; i++) {
    for (var j = 1; j <= a.length; j++) {
      if (b.charAt(i - 1) === a.charAt(j - 1)) {
        matrix[i][j] = matrix[i - 1][j - 1];
      } else {
        matrix[i][j] = Math.min(
          matrix[i - 1][j - 1] + 1, // substitution
          matrix[i][j - 1] + 1,     // insertion
          matrix[i - 1][j] + 1      // deletion
        );
      }
    }
  }
  return matrix[b.length][a.length];
}

function findClosestCommand(badCmd) {
  var best = null;
  var bestDist = Infinity;
  var lower = badCmd.toLowerCase();
  for (var i = 0; i < COMMON_COMMANDS.length; i++) {
    var candidate = COMMON_COMMANDS[i];
    var dist = levenshtein(lower, candidate.toLowerCase());
    if (dist < bestDist) {
      bestDist = dist;
      best = candidate;
    }
  }
  // Only suggest if reasonably close (max 3 edits for words under 8 chars, else proportional)
  var maxDist = lower.length <= 3 ? 1 : (lower.length <= 6 ? 2 : 3);
  if (best && bestDist <= maxDist) {
    return best;
  }
  return null;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function extractBaseCommand(cmd) {
  // Get the first word of the command (skip leading whitespace, handle paths)
  var trimmed = cmd.trim();
  var firstWord = trimmed.split(/\s+/)[0] || '';
  // If it's a path, get just the executable name
  return path.basename(firstWord);
}

function extractCommand(cmd) {
  // Get up to first 3 words as the "command pattern"
  return cmd.trim().split(/\s+/).slice(0, 3).join(' ');
}

function isFailure(stderr, stdout, exitCode) {
  // Exit code indicates failure
  if (exitCode !== undefined && exitCode !== null && exitCode !== 0) {
    return true;
  }
  // Error patterns in stderr
  if (stderr && stderr.trim().length > 0) {
    // Some commands write to stderr even on success (e.g., git clone writes progress to stderr)
    // Check for actual error indicators
    var errorIndicators = [
      /error/i, /fatal/i, /failed/i, /denied/i, /not found/i,
      /cannot/i, /invalid/i, /unknown/i, /unrecognized/i,
      /EACCES/i, /ENOENT/i, /EPERM/i, /EISDIR/i,
      /SyntaxError/i, /ReferenceError/i, /TypeError/i,
      /exit code 1/i, /exited with/i
    ];
    for (var i = 0; i < errorIndicators.length; i++) {
      if (errorIndicators[i].test(stderr)) {
        return true;
      }
    }
  }
  return false;
}

function readCorrections() {
  try {
    if (fs.existsSync(CORRECTIONS_FILE)) {
      var raw = fs.readFileSync(CORRECTIONS_FILE, 'utf8');
      return JSON.parse(raw);
    }
  } catch (e) {}
  return { corrections: {} };
}

function writeCorrections(data) {
  try {
    var dir = path.dirname(CORRECTIONS_FILE);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    fs.writeFileSync(CORRECTIONS_FILE, JSON.stringify(data, null, 2), 'utf8');
  } catch (e) {
    // Silent fail — corrections file is best-effort
  }
}

function addCorrection(badPattern, correction, reason, category) {
  var data = readCorrections();
  var key = badPattern.toLowerCase().trim();

  if (data.corrections[key]) {
    // Update existing
    data.corrections[key].occurrences += 1;
    data.corrections[key].lastSeen = new Date().toISOString();
    // Update reason and correction if they improved
    if (reason && data.corrections[key].reason !== reason) {
      data.corrections[key].reason = reason;
    }
    // Update correction if we now have a better suggestion (not just a placeholder)
    if (correction && correction.indexOf('[check if') === -1 && data.corrections[key].correction.indexOf('[check if') !== -1) {
      data.corrections[key].correction = correction;
    }
  } else {
    // Add new
    data.corrections[key] = {
      correction: correction,
      reason: reason,
      category: category,
      firstSeen: new Date().toISOString(),
      lastSeen: new Date().toISOString(),
      occurrences: 1
    };
  }

  // Prune old entries if too many (keep most recent by lastSeen)
  var keys = Object.keys(data.corrections);
  if (keys.length > MAX_CORRECTIONS) {
    keys.sort(function(a, b) {
      return (data.corrections[b].lastSeen || '').localeCompare(data.corrections[a].lastSeen || '');
    });
    var toRemove = keys.slice(MAX_CORRECTIONS);
    for (var i = 0; i < toRemove.length; i++) {
      delete data.corrections[toRemove[i]];
    }
  }

  writeCorrections(data);
}

// ── Main ─────────────────────────────────────────────────────────────────────

function main() {
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
      // Can't parse — nothing to do
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: {
          hookEventName: 'PostToolUse',
          additionalContext: ''
        }
      }) + '\n');
      return;
    }

    // Only process Bash/PowerShell
    var toolName = input.tool_name;
    if (toolName !== 'Bash' && toolName !== 'PowerShell') {
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: {
          hookEventName: 'PostToolUse',
          additionalContext: ''
        }
      }) + '\n');
      return;
    }

    var toolInput = input.tool_input || {};
    var command = toolInput.command || '';

    // No command — nothing to do
    if (!command || command.trim() === '') {
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: {
          hookEventName: 'PostToolUse',
          additionalContext: ''
        }
      }) + '\n');
      return;
    }

    // Get the response — structure varies, be flexible
    var toolResponse = input.tool_response || '';
    var stdout = '';
    var stderr = '';
    var exitCode = undefined;

    if (typeof toolResponse === 'string') {
      // Combined output — try to detect errors from the string
      var combined = toolResponse;
      stdout = combined;
      stderr = ''; // Can't separate
    } else if (typeof toolResponse === 'object' && toolResponse !== null) {
      stdout = toolResponse.stdout || toolResponse.output || '';
      stderr = toolResponse.stderr || '';
      exitCode = toolResponse.exitCode || toolResponse.exit_code || toolResponse.code;
    }

    // Check if the command failed
    if (!isFailure(stderr, stdout, exitCode)) {
      // Success — nothing to record
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: {
          hookEventName: 'PostToolUse',
          additionalContext: ''
        }
      }) + '\n');
      return;
    }

    // Run detectors against the failure
    for (var i = 0; i < DETECTORS.length; i++) {
      var detector = DETECTORS[i];
      if (detector.test(command, stderr, stdout, exitCode)) {
        var result = detector.categorize(command, stderr, stdout);
        if (result && result.badPattern) {
          addCorrection(
            result.badPattern,
            result.correction,
            result.reason,
            result.category
          );
        }
        break; // First match wins
      }
    }

    // Always allow — this hook only observes and records, never blocks
    process.stdout.write(JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'PostToolUse',
        additionalContext: ''
      }
    }) + '\n');
  });
}

main();
