#!/usr/bin/env node
/**
 * remind-spec-drift.cjs — PostToolUse hook (matcher: Write|Edit)
 *
 * After writing source files, reminds the AI about spec drift.
 * Maps modified file paths to affected spec domains.
 * Tracks cumulative file changes since last /sdd-spec-update.
 *
 * Place in: ~/.claude/hooks/remind-spec-drift.cjs
 * Register in: ~/.claude/settings.json under hooks.PostToolUse with matcher: "Write|Edit"
 */

var fs = require('fs');
var path = require('path');

var HOME = process.env.HOME || process.env.USERPROFILE || '';

// ── File path → Spec domain mapping ──────────────────────────────────────────

var DOMAIN_MAP = [
  {
    domain: 'security.constitution.yaml',
    patterns: [/\/auth\//, /\/middleware\/auth/, /\/guards\//, /\/passport/,
               /\/session\//, /\/csrf\//, /\/helmet/, /\/cors\//, /\/oauth\//,
               /\/jwt\//, /\/rbac\//, /\/permissions\//, /\/roles\//],
  },
  {
    domain: 'api-surface.spec.yaml',
    patterns: [/\/routes\//, /\/controllers\//, /\/handlers\//, /\/endpoints\//,
               /\/router\//, /\/graphql\//, /\/trpc\//, /\/openapi\//,
               /\/swagger\//, /server\.(ts|js|py|go)/, /app\.(ts|js|py|go)/,
               /main\.(ts|js|py|go)/, /index\.(ts|js|py|go)/],
  },
  {
    domain: 'data-model.spec.yaml',
    patterns: [/\/models\//, /\/entities\//, /\/schema\//, /\/migrations\//,
               /\/dal\//, /\/repositories\//, /schema\.prisma/, /\/sql\//,
               /\/db\//, /\/database\//, /alembic\//],
  },
  {
    domain: 'business-domain.spec.yaml',
    patterns: [/\/services\//, /\/usecases\//, /\/domain\//, /\/core\//,
               /\/business\//, /\/logic\//, /\/workflows\//, /\/processors\//],
  },
  {
    domain: 'deployment.spec.yaml',
    patterns: [/\/infra\//, /\/deploy\//, /\/terraform\//, /\/k8s\//,
               /\/kubernetes\//, /docker-compose/, /Dockerfile/, /\/helm\//,
               /\/ansible\//, /\/cloudformation\//, /\/pulumi\//,
               /\.github\/workflows\//, /\.gitlab-ci\.yml/, /Jenkinsfile/],
  },
];

var SOURCE_EXTS = ['.ts', '.js', '.jsx', '.tsx', '.py', '.go', '.rs', '.java',
  '.cs', '.rb', '.php', '.sql', '.tf', '.yml', '.yaml', '.sh'];

var SKIP_PATTERNS = ['specs/', 'docs/', '.test.', '.spec.', '__tests__/',
  'node_modules/', '.git/', 'dist/', 'build/', '__pycache__/', 'vendor/',
  'package.json', 'package-lock.json', 'yarn.lock', 'tsconfig.json',
  '.eslintrc', '.prettierrc', '.gitignore', 'README.md', 'CHANGELOG.md',
  'LICENSE', 'CLAUDE.md', 'HANDOFF.md'];

function isSourceFile(filePath) {
  var ext = path.extname(filePath).toLowerCase();
  if (SOURCE_EXTS.indexOf(ext) === -1 && path.basename(filePath) !== 'Dockerfile') {
    return false;
  }
  for (var i = 0; i < SKIP_PATTERNS.length; i++) {
    if (filePath.indexOf(SKIP_PATTERNS[i]) !== -1) return false;
  }
  return true;
}

function getProjectDir() {
  return process.env.CLAUDE_PROJECT_DIR || process.cwd();
}

function hasSpecs(projectDir) {
  try {
    var specsDir = path.join(projectDir, 'specs');
    return fs.existsSync(specsDir);
  } catch(e) { return false; }
}

function mapToDomains(filePath) {
  var domains = [];
  for (var i = 0; i < DOMAIN_MAP.length; i++) {
    var entry = DOMAIN_MAP[i];
    for (var j = 0; j < entry.patterns.length; j++) {
      if (entry.patterns[j].test(filePath)) {
        if (domains.indexOf(entry.domain) === -1) {
          domains.push(entry.domain);
        }
        break;
      }
    }
  }
  return domains;
}

// ── Drift tracking (simple file-based counter) ───────────────────────────────

var DRIFT_FILE = path.join(HOME, '.claude', 'hooks', 'sdd-drift-tracker.json');

function readDrift() {
  try {
    if (fs.existsSync(DRIFT_FILE)) {
      return JSON.parse(fs.readFileSync(DRIFT_FILE, 'utf8'));
    }
  } catch(e) {}
  return {};
}

function writeDrift(data) {
  try {
    var dir = path.dirname(DRIFT_FILE);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(DRIFT_FILE, JSON.stringify(data, null, 2), 'utf8');
  } catch(e) {}
}

function recordChange(projectDir, filePath, domains) {
  var data = readDrift();
  if (!data[projectDir]) {
    data[projectDir] = { files: [], lastUpdate: null, totalChanges: 0 };
  }
  var proj = data[projectDir];
  proj.totalChanges += 1;
  proj.files.push({ file: filePath, domains: domains, time: new Date().toISOString() });
  // Keep last 50 entries max
  if (proj.files.length > 50) proj.files = proj.files.slice(-50);
  writeDrift(data);
  return proj;
}

function markUpdated(projectDir) {
  var data = readDrift();
  if (data[projectDir]) {
    data[projectDir].files = [];
    data[projectDir].totalChanges = 0;
    data[projectDir].lastUpdate = new Date().toISOString();
  }
  writeDrift(data);
}

function getDriftCount(projectDir) {
  var data = readDrift();
  if (data[projectDir]) return data[projectDir].totalChanges || 0;
  return 0;
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
        hookSpecificOutput: { hookEventName: 'PostToolUse', additionalContext: '' }
      }) + '\n');
      return;
    }

    var toolName = input.tool_name;
    var toolInput = input.tool_input || {};
    var filePath = toolInput.file_path || '';

    // Only check Write/Edit
    if (toolName !== 'Write' && toolName !== 'Edit') {
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: { hookEventName: 'PostToolUse', additionalContext: '' }
      }) + '\n');
      return;
    }

    var projectDir = getProjectDir();

    // Check if this is an SDD command updating specs (skip drift tracking)
    if (filePath.indexOf('specs/') !== -1) {
      // If writing to a spec file, reset drift counter
      if (/specs\/.*\.(yaml|yml)/.test(filePath)) {
        markUpdated(projectDir);
      }
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: { hookEventName: 'PostToolUse', additionalContext: '' }
      }) + '\n');
      return;
    }

    // Only track source files
    if (!isSourceFile(filePath)) {
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: { hookEventName: 'PostToolUse', additionalContext: '' }
      }) + '\n');
      return;
    }

    // Check if specs exist
    if (!hasSpecs(projectDir)) {
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: { hookEventName: 'PostToolUse', additionalContext: '' }
      }) + '\n');
      return;
    }

    var domains = mapToDomains(filePath);
    var driftState = recordChange(projectDir, filePath, domains);
    var changeCount = driftState.totalChanges;

    var lines = [];
    lines.push('');
    lines.push('---');
    lines.push('## SDD DRIFT CHECK — PostToolUse');
    lines.push('');

    if (domains.length > 0) {
      lines.push('File modified: `' + filePath + '`');
      lines.push('Affected spec domain(s):');
      domains.forEach(function(d) { lines.push('  - `' + d + '`'); });
    } else {
      lines.push('File modified: `' + filePath + '`');
      lines.push('Domain: could not map to a spec domain automatically.');
    }

    lines.push('');

    if (changeCount === 1) {
      lines.push('**1 file modified** since last spec update.');
    } else if (changeCount <= 5) {
      lines.push('**' + changeCount + ' files modified** since last spec update.');
      lines.push('Drift is accumulating. Run /sdd-spec-update after this task.');
    } else if (changeCount <= 15) {
      lines.push('**' + changeCount + ' files modified** since last spec update.');
      lines.push('**DRIFT ACCUMULATING.** Specs likely stale. Run /sdd-spec-update soon.');
    } else {
      lines.push('**' + changeCount + ' files modified** since last spec update.');
      lines.push('**CRITICAL DRIFT.** Specs almost certainly out of sync. Run /sdd-spec-update NOW.');
    }

    lines.push('');
    lines.push('After completing code changes, run: `/sdd-spec-update "<summary of changes>"`');
    lines.push('This resets the drift counter and keeps specs synchronized.');
    lines.push('---');

    process.stdout.write(JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'PostToolUse',
        additionalContext: lines.join('\n'),
      }
    }) + '\n');
  });
}

main();
