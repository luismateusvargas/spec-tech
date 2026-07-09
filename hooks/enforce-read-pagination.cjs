#!/usr/bin/env node
/**
 * enforce-read-pagination.cjs — PreToolUse hook (matcher: Read)
 *
 * Prevents Claude from reading large files without pagination (offset/limit).
 * Large file reads waste tokens and context window. This hook:
 *
 * 1. Checks the file size before allowing a Read
 * 2. If file > LINE_THRESHOLD and no offset/limit is set: DENY with guidance
 * 3. If file > LINE_THRESHOLD but offset/limit is set: ALLOW
 * 4. If file < LINE_THRESHOLD: ALLOW
 *
 * The denial message tells Claude HOW to read the file properly.
 *
 * Place in: ~/.claude/hooks/enforce-read-pagination.cjs
 * Register in: ~/.claude/settings.json under hooks.PreToolUse with matcher: "Read"
 */

var fs = require('fs');
var path = require('path');

// Max lines allowed without pagination. Above this, offset/limit is REQUIRED.
var LINE_THRESHOLD = 500;

// Max file size (bytes) before pagination is required
var SIZE_THRESHOLD = 100 * 1024; // 100KB

// How many lines of context to recommend per read
var RECOMMENDED_CHUNK = 200;

function estimateLines(filePath) {
  try {
    var stat = fs.statSync(filePath);
    var size = stat.size;

    // For very large files, estimate based on average line length
    if (size > 10 * 1024 * 1024) { // > 10MB
      return { lines: 1000000, estimated: true, size: size };
    }

    // For smaller files, count actual lines
    var content = fs.readFileSync(filePath, 'utf8');
    var lines = content.split('\n').length;
    return { lines: lines, estimated: false, size: size };
  } catch (e) {
    return null;
  }
}

function allow() {
  var out = JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      permissionDecision: 'allow'
    }
  });
  process.stdout.write(out + '\n');
}

function deny(reason) {
  var out = JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      permissionDecision: 'deny',
      permissionDecisionReason: reason
    }
  });
  process.stdout.write(out + '\n');
}

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
      allow();
      return;
    }

    // Only intercept Read tool
    if (input.tool_name !== 'Read') {
      allow();
      return;
    }

    var toolInput = input.tool_input || {};
    var filePath = toolInput.file_path;
    var offset = toolInput.offset;
    var limit = toolInput.limit;
    var pages = toolInput.pages; // PDF mode: different rules

    // PDF mode: allow (page-based pagination is fine)
    if (pages) {
      allow();
      return;
    }

    // No file path: can't check, allow through
    if (!filePath) {
      allow();
      return;
    }

    // Already paginated: allow
    if (offset !== undefined || limit !== undefined) {
      allow();
      return;
    }

    // Check file size
    var info = estimateLines(filePath);

    // Can't read the file: allow (will fail at the Read level if truly broken)
    if (!info) {
      allow();
      return;
    }

    var lines = info.lines;
    var estimated = info.estimated;
    var size = info.size;

    // Small file: allow
    if (lines <= LINE_THRESHOLD && size <= SIZE_THRESHOLD) {
      allow();
      return;
    }

    // Large file without pagination: DENY and guide
    var estNote = estimated ? ' (estimated - file is very large)' : '';
    var reasonLines = [
      'File is ' + lines.toLocaleString() + ' lines' + estNote + ' (' + (size / 1024).toFixed(1) + ' KB).',
      'Reading it entirely wastes tokens and context window.',
      '',
      'Instead, use pagination:',
      '  - Read with offset: <starting line> and limit: ' + RECOMMENDED_CHUNK + ' to read chunks',
      '  - OR Grep for specific patterns first, then Read only the relevant sections',
      '  - OR if you know the line range you need, set offset + limit',
      '',
      'Quick reference:',
      '  Read("' + path.basename(filePath) + '", offset: 0, limit: ' + RECOMMENDED_CHUNK + ')  - first ' + RECOMMENDED_CHUNK + ' lines',
      '  Grep(pattern: "functionName", path: "' + path.basename(filePath) + '")  - find specific code'
    ];
    deny(reasonLines.join('\n'));
  });
}

main();
