#!/usr/bin/env node
/**
 * capture-cardinal-rules.cjs — UserPromptSubmit hook
 *
 * Learns and enforces "Cardinal Rules" the user declares mid-conversation.
 *
 * Capture (user types any of these):
 *   Cardinal Rule: ALWAYS USE .ENV FILES FOR SECRETS
 *   CR: ADD ERROR HANDLERS INSTEAD OF FALLBACKS
 *   /cardinal-rule NEVER COMMIT GENERATED FILES
 *   /cr USE PARAMETERIZED QUERIES
 *
 * Removal:
 *   /remove-rule <id>
 *   /delete-rule <id>
 *   Remove cardinal rule: <id>
 *
 * On every prompt, ALL stored rules are injected as mandatory context.
 * Rules persist in ~/.claude/hooks/cardinal-rules.json
 *
 * Place in: ~/.claude/hooks/capture-cardinal-rules.cjs
 * Register in: ~/.claude/settings.json under hooks.UserPromptSubmit
 */

var fs = require('fs');
var path = require('path');
var os = require('os');

var RULES_FILE = path.join(os.homedir(), '.claude', 'hooks', 'cardinal-rules.json');
var MAX_RULES = 30;

// ── Rule management ──────────────────────────────────────────────────────────

function readRules() {
  try {
    if (fs.existsSync(RULES_FILE)) {
      return JSON.parse(fs.readFileSync(RULES_FILE, 'utf8'));
    }
  } catch (e) {}
  return { rules: [] };
}

function writeRules(data) {
  try {
    var dir = path.dirname(RULES_FILE);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(RULES_FILE, JSON.stringify(data, null, 2), 'utf8');
  } catch (e) {}
}

function slugify(text) {
  return text.toLowerCase()
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .substring(0, 40);
}

function addRule(ruleText) {
  var data = readRules();
  var id = slugify(ruleText);

  // Check duplicate
  for (var i = 0; i < data.rules.length; i++) {
    if (data.rules[i].id === id || data.rules[i].rule.toLowerCase() === ruleText.toLowerCase()) {
      data.rules[i].occurrences += 1;
      data.rules[i].lastSeen = new Date().toISOString();
      writeRules(data);
      return { action: 'updated', rule: data.rules[i] };
    }
  }

  var newRule = {
    id: id,
    rule: ruleText.toUpperCase(),
    created: new Date().toISOString(),
    lastSeen: new Date().toISOString(),
    occurrences: 1
  };

  data.rules.push(newRule);

  // Trim oldest if over limit
  if (data.rules.length > MAX_RULES) {
    data.rules = data.rules.slice(-MAX_RULES);
  }

  writeRules(data);
  return { action: 'added', rule: newRule };
}

function removeRule(idOrText) {
  var data = readRules();
  var lower = idOrText.toLowerCase().trim();
  var removed = null;

  data.rules = data.rules.filter(function(r) {
    if (r.id === lower || r.id.indexOf(lower) !== -1 || r.rule.toLowerCase().indexOf(lower) !== -1) {
      removed = r;
      return false;
    }
    return true;
  });

  if (removed) {
    writeRules(data);
    return { action: 'removed', rule: removed };
  }
  return null;
}

// ── Prompt scanning ──────────────────────────────────────────────────────────

function scanForRules(prompt) {
  var results = [];

  // Pattern: Cardinal Rule: <text>
  var cardinalRe = /(?:^|\n)\s*(?:Cardinal\s+Rule|CR)\s*:\s*(.+?)(?:\n|$)/gim;
  var m;
  while ((m = cardinalRe.exec(prompt)) !== null) {
    var text = m[1].trim();
    if (text.length > 5 && text.length < 300) {
      var result = addRule(text);
      results.push(result);
    }
  }

  // Pattern: /cardinal-rule <text> or /cr <text>
  var slashRe = /(?:^|\n)\s*\/(?:cardinal-rule|cr)\s+(.+?)(?:\n|$)/gim;
  while ((m = slashRe.exec(prompt)) !== null) {
    var text2 = m[1].trim();
    if (text2.length > 5 && text2.length < 300) {
      var result2 = addRule(text2);
      results.push(result2);
    }
  }
  return results;
}

function scanForRemovals(prompt) {
  var results = [];

  // Pattern: /remove-rule <id> or /delete-rule <id>
  var slashRe = /(?:^|\n)\s*\/(?:remove|delete)-rule\s+(.+?)(?:\n|$)/gim;
  var m;
  while ((m = slashRe.exec(prompt)) !== null) {
    var result = removeRule(m[1].trim());
    if (result) results.push(result);
  }

  // Pattern: Remove cardinal rule: <id>
  var textRe = /(?:^|\n)\s*(?:Remove|Delete)\s+(?:cardinal|CR)\s+rule\s*:\s*(.+?)(?:\n|$)/gim;
  while ((m = textRe.exec(prompt)) !== null) {
    var result2 = removeRule(m[1].trim());
    if (result2) results.push(result2);
  }

  return results;
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
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: { hookEventName: 'UserPromptSubmit', additionalContext: '' }
      }) + '\n');
      return;
    }

    var prompt = input.prompt || '';

    // Scan for new rules and removals
    var added = scanForRules(prompt);
    var removed = scanForRemovals(prompt);
    var hasChanges = added.length > 0 || removed.length > 0;

    // Read current rules
    var data = readRules();

    // If user just asked to list rules
    var listRequest = /\b(?:list|show|display)\s+(?:cardinal\s+)?rules\b/i.test(prompt) ||
                      /^\/rules$/im.test(prompt) ||
                      /^\/cardinal-rules$/im.test(prompt);

    if (listRequest) {
      var listMsg = '';
      if (data.rules.length === 0) {
        listMsg = 'No cardinal rules set. Add: "Cardinal Rule: <your rule>" or "/cr <your rule>"';
      } else {
        var items = data.rules.map(function(r, i) {
          return (i + 1) + '. `' + r.id + '`: ' + r.rule + ' (' + r.occurrences + 'x)';
        });
        listMsg = 'Cardinal Rules (' + data.rules.length + '):\n' + items.join('\n');
      }
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: {
          hookEventName: 'UserPromptSubmit',
          additionalContext: '\n---\n' + listMsg + '\n---'
        }
      }) + '\n');
      return;
    }

    // Build injection
    var lines = [];

    // Acknowledge changes
    if (hasChanges) {
      lines.push('');
      lines.push('---');
      lines.push('## CARDINAL RULE UPDATED');
      added.forEach(function(r) {
        lines.push('- ' + r.action.toUpperCase() + ': `' + r.rule.id + '` → ' + r.rule.rule);
      });
      removed.forEach(function(r) {
        lines.push('- REMOVED: `' + r.rule.id + '`');
      });
      lines.push('---');
      lines.push('');
    }

    // Inject all rules
    if (data.rules.length > 0) {
      lines.push('');
      lines.push('---');
      lines.push('## CARDINAL RULES — ENFORCE DURING ALL CODE CHANGES');
      lines.push('');
      lines.push('These are user-defined mandatory rules. You MUST follow them when writing, editing, or reviewing code. Violating any of these is an error.');
      lines.push('');

      data.rules.forEach(function(r, i) {
        lines.push((i + 1) + '. **' + r.rule + '**');
        lines.push('   _id: `' + r.id + '` | added: ' + r.created.split('T')[0] + ' | enforced: ' + r.occurrences + 'x_');
      });

      lines.push('');
      lines.push('Before writing code, mentally verify: do ALL cardinal rules pass? If any fail → fix before output.');
      lines.push('');
      lines.push('Manage: "Cardinal Rule: <rule>" to add, "/remove-rule <id>" to delete, "list cardinal rules" to see all.');
      lines.push('---');
    }

    var additionalContext = lines.join('\n');

    process.stdout.write(JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'UserPromptSubmit',
        additionalContext: additionalContext
      }
    }) + '\n');
  });
}

main();
