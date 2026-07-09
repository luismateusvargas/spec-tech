#!/usr/bin/env node
/**
 * inject-sdd-guard.cjs — UserPromptSubmit hook
 *
 * SDD guardrail injected into EVERY user prompt:
 * 1. If specs/ exists → inject security constitution summary, warn about drift
 * 2. If specs/ missing AND user asks for code → suggest /sdd-spec-start or /sdd-spec-check
 * 3. If /sdd-spec-* command detected → verify constitution loaded
 *
 * Place in: ~/.claude/hooks/inject-sdd-guard.cjs
 * Register in: ~/.claude/settings.json under hooks.UserPromptSubmit
 */

var fs = require('fs');
var path = require('path');

var HOME = process.env.HOME || process.env.USERPROFILE || '';

function getProjectDir() {
  var cwd = process.env.CLAUDE_PROJECT_DIR || process.cwd();
  return cwd;
}

function hasSpecs(projectDir) {
  try {
    var specsDir = path.join(projectDir, 'specs');
    if (!fs.existsSync(specsDir)) return false;
    var entries = fs.readdirSync(specsDir);
    return entries.some(function(e) { return e.endsWith('.yaml') || e.endsWith('.yml'); });
  } catch(e) { return false; }
}

function countLockedSpecs(projectDir) {
  try {
    var specsDir = path.join(projectDir, 'specs');
    if (!fs.existsSync(specsDir)) return 0;
    var files = fs.readdirSync(specsDir).filter(function(f) { return f.endsWith('.yaml') || f.endsWith('.yml'); });
    var locked = 0;
    files.forEach(function(f) {
      try {
        var content = fs.readFileSync(path.join(specsDir, f), 'utf8');
        if (/status:\s*locked/.test(content)) locked++;
      } catch(e) {}
    });
    return locked;
  } catch(e) { return 0; }
}

function hasSourceCode(projectDir) {
  var srcDirs = ['src', 'app', 'lib', 'main', 'pkg', 'internal'];
  for (var i = 0; i < srcDirs.length; i++) {
    try {
      var dirPath = path.join(projectDir, srcDirs[i]);
      if (fs.existsSync(dirPath) && fs.statSync(dirPath).isDirectory()) {
        var entries = fs.readdirSync(dirPath);
        if (entries.length > 0) return true;
      }
    } catch(e) {}
  }
  // Fallback: check for source files in root
  try {
    var rootFiles = fs.readdirSync(projectDir);
    return rootFiles.some(function(f) {
      return /\.(ts|js|py|go|rs|java|cs|rb|php)$/.test(f);
    });
  } catch(e) { return false; }
}

function looksLikeProject(projectDir) {
  var markers = ['.git', 'package.json', 'CLAUDE.md', 'go.mod', 'Cargo.toml',
                 'pyproject.toml', 'Makefile', 'src', 'app'];
  for (var i = 0; i < markers.length; i++) {
    try { if (fs.existsSync(path.join(projectDir, markers[i]))) return true; } catch(e) {}
  }
  return false;
}

function isAskingForCode(prompt) {
  var codeKeywords = /\b(build|create|implement|code|develop|write|fix|add|change|modify|refactor|update|remove|delete|generate)\b/i;
  var codePatterns = /\.(ts|js|py|go|rs|java|cs|rb|php|sql|html|css|vue|jsx|tsx)\b/i;
  var sddCommands = /\/sdd-spec-(start|check|update|test)\b/i;

  // Don't flag if user is running SDD commands
  if (sddCommands.test(prompt)) return false;

  return codeKeywords.test(prompt) || codePatterns.test(prompt);
}

function isSddCommand(prompt) {
  return /\/sdd-spec-(start|check|update|test)\b/i.test(prompt);
}

function main() {
  var chunks = [];
  process.stdin.setEncoding('utf8');
  process.stdin.on('readable', function () {
    var chunk;
    while ((chunk = process.stdin.read()) !== null) chunks.push(chunk);
  });

  process.stdin.on('end', function () {
    var input;
    try { input = JSON.parse(chunks.join('')); } catch (e) {
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: { hookEventName: 'UserPromptSubmit', additionalContext: '' }
      }) + '\n');
      return;
    }

    var prompt = input.prompt || '';
    var projectDir = getProjectDir();
    var lines = [];
    var specsExist = hasSpecs(projectDir);
    var lockedCount = countLockedSpecs(projectDir);
    var isCode = isAskingForCode(prompt);
    var isSdd = isSddCommand(prompt);

    // ── Case 1: /sdd-spec-* invoked ──
    if (isSdd) {
      var constFile = path.join(HOME, '.claude', 'commands', 'sdd-templates', 'security.constitution.base.yaml');
      var constExists = false;
      try { constExists = fs.existsSync(constFile); } catch(e) {}

      lines.push('');
      lines.push('---');
      lines.push('## SDD COMMAND ACTIVE — Security Constitution ENFORCED');
      lines.push('');
      if (constExists) {
        lines.push('Global security constitution v2.0 LOADED:');
        lines.push('- OWASP Top 10 2025 (all 10 categories)');
        lines.push('- OWASP API Security Top 10 2023');
        lines.push('- OWASP LLM Top 10 v2.0 (2025)');
        lines.push('- OWASP Agentic AI Top 10 (Dec 2025)');
        lines.push('- 200+ security rules, database-specific by 12 ORM/DB combos');
        lines.push('- 10 absolute blocker patterns (halt code generation on match)');
      } else {
        lines.push('WARNING: Security constitution file not found at ' + constFile);
        lines.push('SDD commands will not have full security rule coverage.');
      }
      lines.push('');
      lines.push('This command is MANUAL. User explicitly invoked it. Respect its constraints.');
      lines.push('- /sdd-spec-start: spec discovery ONLY. NO implementation code.');
      lines.push('- /sdd-spec-check: audit ONLY. Read code, generate specs. NO modifications.');
      lines.push('- /sdd-spec-update: spec update ONLY. NO implementation code.');
      lines.push('- /sdd-spec-test: test generation ONLY. NO implementation code.');
      lines.push('');
      lines.push('LLM Guardrails active: prompt injection defense, tool boundary enforcement, goal integrity.');
      lines.push('---');

      process.stdout.write(JSON.stringify({
        hookSpecificOutput: { hookEventName: 'UserPromptSubmit', additionalContext: lines.join('\n') }
      }) + '\n');
      return;
    }

    // ── Case 2: specs/ exists, user asking for code ──
    if (specsExist && isCode) {
      lines.push('');
      lines.push('---');
      lines.push('## SDD ACTIVE — Security Constitution v2.0 ENFORCED');
      lines.push('');
      lines.push('specs/ detected in this project. ' + lockedCount + ' spec(s) locked.');
      lines.push('');
      lines.push('Active security frameworks:');
      lines.push('- OWASP Top 10 2025 | OWASP API Top 10 2023');
      lines.push('- OWASP LLM Top 10 v2.0 | OWASP Agentic AI Top 10');
      lines.push('- Database-specific rules (auto-detected from project ORM)');
      lines.push('- 10 absolute blockers — CRITICAL patterns halt code generation');
      lines.push('');
      lines.push('**Before writing code:**');
      lines.push('1. Verify code matches locked specs. If behavior changes → update spec first.');
      lines.push('2. Scan for absolute blocker patterns. Any match → fix before writing.');
      lines.push('3. After code changes → run /sdd-spec-update to reconcile specs.');
      lines.push('');
      lines.push('**DRIFT PREVENTION:** Code changes without spec updates = drift. After this task, run /sdd-spec-update with description of changes made.');
      lines.push('---');

      process.stdout.write(JSON.stringify({
        hookSpecificOutput: { hookEventName: 'UserPromptSubmit', additionalContext: lines.join('\n') }
      }) + '\n');
      return;
    }

    // ── Case 3: specs/ exists, drift reminder (passive) ──
    if (specsExist && !isCode) {
      lines.push('');
      lines.push('---');
      lines.push('## SDD ACTIVE — ' + lockedCount + ' spec(s) locked');
      lines.push('Security constitution v2.0 enforced. Use /sdd-spec-update when specs change.');
      lines.push('---');

      process.stdout.write(JSON.stringify({
        hookSpecificOutput: { hookEventName: 'UserPromptSubmit', additionalContext: lines.join('\n') }
      }) + '\n');
      return;
    }

    // ── Case 4: no specs, project exists, user asks for code ──
    if (!specsExist && looksLikeProject(projectDir) && isCode) {
      var hasCode = hasSourceCode(projectDir);

      lines.push('');
      lines.push('---');
      lines.push('## NO SPECS DETECTED — Consider SDD Before Proceeding');
      lines.push('');
      if (hasCode) {
        lines.push('This project has source code but no specs/ directory.');
        lines.push('**Recommended:** Run /sdd-spec-check to audit existing code against security baseline and generate initial specs.');
      } else {
        lines.push('This is a new project with no specs/ directory.');
        lines.push('**Recommended:** Run /sdd-spec-start "<project description>" to define specs before writing code.');
      }
      lines.push('');
      lines.push('Without specs, security constitution rules are NOT actively enforced — only CLAUDE.md rules apply.');
      lines.push('---');

      process.stdout.write(JSON.stringify({
        hookSpecificOutput: { hookEventName: 'UserPromptSubmit', additionalContext: lines.join('\n') }
      }) + '\n');
      return;
    }

    // ── Default: silent — no SDD context needed ──
    process.stdout.write(JSON.stringify({
      hookSpecificOutput: { hookEventName: 'UserPromptSubmit', additionalContext: '' }
    }) + '\n');
  });
}

main();
