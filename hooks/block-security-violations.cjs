#!/usr/bin/env node
/**
 * block-security-violations.cjs — PreToolUse hook (matcher: Write|Edit)
 *
 * Scans file content BEFORE writing to disk. Checks against absolute blocker
 * patterns from the SDD security constitution. Injects warnings into context
 * on CRITICAL matches so the AI fixes before the next turn.
 *
 * Cannot block tool execution directly (hooks are advisory for Write/Edit),
 * but the injected warning + CLAUDE.md rules make the AI correct the violation.
 *
 * Target files: .ts, .js, .py, .go, .rs, .java, .cs, .rb, .php, .sql, .tf, .yml, Dockerfile
 * Skip: specs/, docs/, *.test.*, *.spec.*, *.md, package.json, tsconfig.json, .gitignore
 *
 * Place in: ~/.claude/hooks/block-security-violations.cjs
 * Register in: ~/.claude/settings.json under hooks.PreToolUse with matcher: "Write|Edit"
 */

var fs = require('fs');
var path = require('path');

// ── File path classification ─────────────────────────────────────────────────

var SOURCE_EXTS = ['.ts', '.js', '.jsx', '.tsx', '.py', '.go', '.rs', '.java',
  '.cs', '.rb', '.php', '.sql', '.tf', '.yml', '.yaml', '.sh', '.bash',
  '.env', '.toml', '.cfg', '.ini', '.xml', '.json'];

var SKIP_PATTERNS = ['specs/', 'docs/', '.test.', '.spec.', '__tests__/',
  'package.json', 'tsconfig.json', '.gitignore', '.eslintrc', '.prettierrc',
  'README.md', 'CHANGELOG.md', 'CONTRIBUTING.md', 'LICENSE', 'node_modules/',
  '.git/', 'dist/', 'build/', '__pycache__/', 'vendor/'];

function isSourceFile(filePath) {
  var ext = path.extname(filePath).toLowerCase();
  if (SOURCE_EXTS.indexOf(ext) === -1) return false;
  // Check skip patterns
  for (var i = 0; i < SKIP_PATTERNS.length; i++) {
    if (filePath.indexOf(SKIP_PATTERNS[i]) !== -1) return false;
  }
  // Dockerfile (no extension)
  if (path.basename(filePath) === 'Dockerfile') return true;
  return true;
}

// ── Absolute Blocker Patterns (from security constitution) ───────────────────

var ABSOLUTE_BLOCKERS = [
  {
    id: 'SEC-REJECT-HARDCODED-SECRET',
    severity: 'CRITICAL',
    regex: /(api_key|apikey|secret|password|token|private_key|SECRET|API_KEY)\s*[:=]\s*["'][a-zA-Z0-9+\/=]{16,}["']/,
    message: 'Hardcoded secret detected. Move to KMS/vault immediately.',
  },
  {
    id: 'SEC-REJECT-SQL-CONCAT',
    severity: 'CRITICAL',
    regex: /("SELECT.*"\s*\+\s*|`SELECT.*\$\{)/i,
    message: 'SQL injection vector: string concatenation in query. Use parameterized queries.',
  },
  {
    id: 'SEC-REJECT-WEAK-HASH',
    severity: 'CRITICAL',
    regex: /(md5|sha1|sha256|sha512)\(.*password/i,
    message: 'Weak password hash algorithm. Use bcrypt(cost>=12) or argon2id.',
  },
  {
    id: 'SEC-REJECT-JWT-NONE',
    severity: 'CRITICAL',
    regex: /algorithms\s*:\s*\[.*none.*\]/i,
    message: 'JWT "none" algorithm accepted. Use only ["RS256", "ES256"].',
  },
  {
    id: 'SEC-REJECT-EVAL-USER',
    severity: 'CRITICAL',
    regex: /(eval|exec|new Function)\s*\(.*(req\.|user|input|params|query|body)/i,
    message: 'Code injection vector: eval/exec with user data.',
  },
  {
    id: 'SEC-REJECT-HTTP-SENSITIVE',
    severity: 'CRITICAL',
    regex: /http:\/\/.*(auth|login|payment|checkout|signup|register|token|credential)/i,
    message: 'HTTP used for sensitive endpoint. Must be HTTPS.',
  },
  {
    id: 'SEC-REJECT-DB-EXPOSED',
    severity: 'CRITICAL',
    regex: /0\.0\.0\.0\/0.*(5432|3306|27017|6379|1433)/,
    message: 'Database port exposed to public internet (0.0.0.0/0). Restrict to VPC.',
  },
  {
    id: 'SEC-REJECT-UNSAFE-DESERIALIZE',
    severity: 'CRITICAL',
    regex: /(pickle\.loads|yaml\.load\(|unserialize\(|Marshal\.load|ObjectInputStream)/i,
    message: 'Unsafe deserialization. Use JSON/protobuf instead.',
  },
  {
    id: 'SEC-REJECT-LLM-EXEC',
    severity: 'CRITICAL',
    regex: /(eval|exec|new Function|spawn|execSync)\s*\(.*(llm|completion|chat|agent|model|ai)/i,
    message: 'Executing LLM output without sanitization. Review and sandbox.',
  },
  {
    id: 'SEC-REJECT-PROMPT-SECRET',
    severity: 'CRITICAL',
    regex: /system_prompt.*=\s*.*(api_key|secret|password|token|credential).*["']/i,
    message: 'Secret in system prompt. Prompts CAN be extracted. Move to external service.',
  },
];

var HIGH_PATTERNS = [
  {
    id: 'SEC-WARN-INNERHTML',
    severity: 'HIGH',
    regex: /(innerHTML|dangerouslySetInnerHTML|v-html|bypassSecurityTrust)/,
    message: 'XSS vector: unescaped HTML insertion. Use textContent or DOMPurify.',
  },
  {
    id: 'SEC-WARN-INSECURE-CSP',
    severity: 'HIGH',
    regex: /unsafe-inline|unsafe-eval/,
    message: 'Insecure CSP directive. Use nonces or hashes instead.',
  },
  {
    id: 'SEC-WARN-MASS-ASSIGN',
    severity: 'HIGH',
    regex: /(Model\.create\(req\.body\)|Model\.update\(req\.body\)|Object\.assign\(.*req\.body|\.\.\.req\.body)/,
    message: 'Mass assignment from request body. Use allowlisted DTOs.',
  },
  {
    id: 'SEC-WARN-CORS-WILDCARD',
    severity: 'HIGH',
    regex: /Access-Control-Allow-Origin\s*:\s*\*/,
    message: 'Wildcard CORS. Specify exact origins.',
  },
  {
    id: 'SEC-WARN-DEBUG-PROD',
    severity: 'HIGH',
    regex: /(debug\s*:\s*true|DEBUG\s*=\s*True|NODE_ENV\s*=\s*['"]development['"])/,
    message: 'Debug mode enabled. Must be disabled in production.',
  },
  {
    id: 'SEC-WARN-MISSING-PARAM',
    severity: 'HIGH',
    regex: /\.raw\(.*\$\{|\.query\(.*\$\{|\.execute\(.*\$\{|cursor\.execute\(f["']/i,
    message: 'Raw query with interpolation. Use parameterized bindings.',
  },
  {
    id: 'SEC-WARN-JWT-WEAK',
    severity: 'HIGH',
    regex: /ignoreExpiration\s*:\s*true|jwt\.verify.*algorithms.*none/i,
    message: 'JWT validation bypass: expiration ignored or none algorithm accepted.',
  },
  {
    id: 'SEC-WARN-WEAK-PASSWORD-POLICY',
    severity: 'HIGH',
    regex: /password.*(min_length|minLength|min)\s*[:=]\s*[1-7]\b/i,
    message: 'Weak password policy: minimum length < 8. Should be >= 8 (12+ for admin).',
  },
];

// ── Content extraction ───────────────────────────────────────────────────────

function getContent(toolName, toolInput) {
  // Write tool: content is in toolInput.content
  if (toolInput.content) return toolInput.content;

  // Edit tool: new_string is the new content being written
  if (toolInput.new_string) return toolInput.new_string;

  return '';
}

// ── Scanning ─────────────────────────────────────────────────────────────────

function scanContent(content, filePath) {
  var findings = [];

  // Scan absolute blockers
  for (var i = 0; i < ABSOLUTE_BLOCKERS.length; i++) {
    var blocker = ABSOLUTE_BLOCKERS[i];
    var match = content.match(blocker.regex);
    if (match) {
      findings.push({
        id: blocker.id,
        severity: blocker.severity,
        message: blocker.message,
        matched: match[0].substring(0, 80) + (match[0].length > 80 ? '...' : ''),
        file: filePath,
      });
    }
  }

  // Scan high-severity patterns
  for (var j = 0; j < HIGH_PATTERNS.length; j++) {
    var warn = HIGH_PATTERNS[j];
    var wmatch = content.match(warn.regex);
    if (wmatch) {
      findings.push({
        id: warn.id,
        severity: warn.severity,
        message: warn.message,
        matched: wmatch[0].substring(0, 80) + (wmatch[0].length > 80 ? '...' : ''),
        file: filePath,
      });
    }
  }

  return findings;
}

// ── Main ─────────────────────────────────────────────────────────────────────

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
        hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: 'allow' }
      }) + '\n');
      return;
    }

    var toolName = input.tool_name;
    var toolInput = input.tool_input || {};
    var filePath = toolInput.file_path || '';

    // Only check Write/Edit
    if (toolName !== 'Write' && toolName !== 'Edit') {
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: 'allow' }
      }) + '\n');
      return;
    }

    // Only check source files
    if (!isSourceFile(filePath)) {
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: 'allow' }
      }) + '\n');
      return;
    }

    var content = getContent(toolName, toolInput);
    if (!content || content.length < 3) {
      // Too short to meaningfully scan
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: 'allow' }
      }) + '\n');
      return;
    }

    var findings = scanContent(content, filePath);

    if (findings.length === 0) {
      // Clean — allow silently
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: 'allow' }
      }) + '\n');
      return;
    }

    // Separate critical from high
    var criticals = findings.filter(function(f) { return f.severity === 'CRITICAL'; });
    var highs = findings.filter(function(f) { return f.severity === 'HIGH'; });

    // Build warning injection
    var lines = [];
    lines.push('');
    lines.push('---');
    lines.push('## SECURITY VIOLATION DETECTED — PreToolUse (SDD Constitution)');
    lines.push('');

    if (criticals.length > 0) {
      lines.push('### CRITICAL — Fix before proceeding:');
      lines.push('');
      criticals.forEach(function(f) {
        lines.push('**[CRITICAL] ' + f.id + '**');
        lines.push('  ' + f.message);
        lines.push('  File: `' + f.file + '`');
        lines.push('  Pattern matched: `' + f.matched + '`');
        lines.push('');
      });
    }

    if (highs.length > 0) {
      lines.push('### HIGH — Review before proceeding:');
      lines.push('');
      highs.forEach(function(f) {
        lines.push('**[HIGH] ' + f.id + '**');
        lines.push('  ' + f.message);
        lines.push('  File: `' + f.file + '`');
        lines.push('');
      });
    }

    lines.push('**Action:** Fix violations before writing to disk. All security rules are MANDATORY per CLAUDE.md and SDD constitution.');
    lines.push('---');

    // Inject warning as additionalContext — advisory, not blocking
    process.stdout.write(JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'PreToolUse',
        permissionDecision: 'allow',
        additionalContext: lines.join('\n'),
      }
    }) + '\n');
  });
}

main();
