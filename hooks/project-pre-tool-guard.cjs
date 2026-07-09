#!/usr/bin/env node
/**
 * pre-tool-guard.cjs — PreToolUse hook
 *
 * Guards against the model guessing/creating files it shouldn't:
 * 1. Blocks Edit to files that don't exist (prevents guessing paths)
 * 2. Blocks writes to security-sensitive files (.env, .pem, credentials, etc.)
 * 3. Warns about writes outside project scope
 *
 * Exit codes:
 *   0 → allow
 *   2 → block
 */

const ALLOWED_CREATE_PATTERNS = [
  '/HANDOFF\\.md$',
  '\\.claude/',
  '\\.github/',
  'README\\.md$',
];

const BLOCKED_PATH_PATTERNS = [
  '\\.env$',
  '\\.env\\.',
  '\\.pem$',
  '\\.key$',
  '\\.cert$',
  'credentials',
  'secrets',
  'node_modules/',
];

let input = '';

process.stdin.on('data', (chunk) => { input += chunk; });

process.stdin.on('end', () => {
  try {
    const payload = JSON.parse(input);
    const toolName = payload.tool_name || payload.tool || '';
    const toolInput = payload.tool_input || payload.input || {};

    let filePath = '';
    if (toolInput.file_path) filePath = toolInput.file_path;
    else if (toolInput.path) filePath = toolInput.path;

    if (!filePath) process.exit(0);

    const fs = require('fs');
    const projectDir = process.env.CLAUDE_PROJECT_DIR || '';

    // Check 1: Block security-sensitive paths
    for (const pattern of BLOCKED_PATH_PATTERNS) {
      if (new RegExp(pattern, 'i').test(filePath)) {
        console.error('[GUARD] BLOCKED: ' + filePath + ' matches blocked pattern "' + pattern + '"');
        process.exit(2);
      }
    }

    // Check 2: Edit requires file to exist (no guessing!)
    const isEditOp = toolName === 'Edit' || toolName === 'MultiEdit';
    if (isEditOp) {
      try {
        fs.accessSync(filePath, fs.constants.F_OK);
      } catch {
        console.error('[GUARD] BLOCKED: Edit on non-existent file "' + filePath + '". Use Glob to verify the path first.');
        process.exit(2);
      }
    }

    // Check 3: Write to new files — warn but allow within project
    const isWriteOp = toolName === 'Write';
    if (isWriteOp && projectDir && !filePath.startsWith(projectDir)) {
      if (!filePath.startsWith(process.env.HOME || '')) {
        console.error('[GUARD] BLOCKED: Creating file outside project: "' + filePath + '"');
        process.exit(2);
      }
    }

    process.exit(0);
  } catch (err) {
    console.error('[GUARD] Error (allowing): ' + err.message);
    process.exit(0);
  }
});
