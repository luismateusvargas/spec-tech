#!/usr/bin/env node
/**
 * clarify-ambiguity.cjs — UserPromptSubmit hook
 *
 * Analyzes the user's prompt for ambiguity signals and injects a directive
 * that FORCES Claude to self-evaluate clarity before acting.
 *
 * "Understandable" = Claude has NO doubts about:
 *   1. WHERE to look (files, directories, projects)
 *   2. WHAT to do (specific action, not vague verbs)
 *   3. HOW to decide between approaches (if multiple paths exist)
 *
 * When ambiguity is detected, this hook injects a stern directive that
 * requires Claude to ASK clarifying questions instead of guessing.
 *
 * Place in: ~/.claude/hooks/clarify-ambiguity.cjs
 * Register in: ~/.claude/settings.json under hooks.UserPromptSubmit
 */

const fs = require('fs');
const path = require('path');

// ── Ambiguity signal detectors ──────────────────────────────────────────────

/**
 * Each detector returns { ambiguous: bool, reason: string, severity: 'high'|'medium' }
 * High severity = MUST ask before acting
 * Medium severity = SHOULD verify before acting
 */

const DETECTORS = [
  // HIGH: Missing target — "fix it/this/that" without specifying what
  {
    name: 'missing-target',
    test(prompt) {
      const patterns = [
        /\b(fix|repair|correct)\s+(it|this|that|the issue|the bug|the problem|the error)\b/i,
        /\b(make|get)\s+(it|this|that)\s+(work|working|to work)\b/i,
        /\b(handle|deal with|take care of)\s+(it|this|that)\b/i,
        /\b(update|change|modify|adjust)\s+(it|this|that)\b(?!\s+(file|function|class|component|module|in|on|to))/i,
        /\b(same|similar)\s+(thing|issue|problem|error|bug)\b/i,
      ];
      for (const re of patterns) {
        const m = prompt.match(re);
        if (m) return { ambiguous: true, reason: `Vague reference: "${m[0]}" — no specific file/component/error named`, severity: 'high' };
      }
      return { ambiguous: false };
    },
  },

  // HIGH: User presents multiple options without choosing
  {
    name: 'undecided-options',
    test(prompt) {
      const patterns = [
        /\b(should|can|do)\s+(I|we|you)\s+.+(or|either).+(or|either).+/i,
        /\bwhich\s+(one|approach|way|method|option|path).+(better|best|should)/i,
        /\b(maybe|perhaps|possibly).+(or|either).+/i,
        /\b(not sure|undecided|torn between|on the fence)\b/i,
        /\bwhat(\s+do|\s+would|\'s)\s+(you|we)\s+(think|recommend|suggest)\b.+(or|vs|versus)/i,
      ];
      for (const re of patterns) {
        const m = prompt.match(re);
        if (m) return { ambiguous: true, reason: `Multiple options presented without a decision: user appears undecided between approaches`, severity: 'high' };
      }
      return { ambiguous: false };
    },
  },

  // HIGH: "as we discussed" / "like before" — lost context from prior session
  {
    name: 'lost-context',
    test(prompt) {
      const patterns = [
        /\b(as|like)\s+(we|I|you)\s+(discussed|talked about|mentioned|said|did|were doing)\b/i,
        /\b(from|since)\s+(before|last time|the last session|earlier|previously)\b/i,
        /\b(continue|carry on|pick up|resume)\s+(where|from)\s+(we|I)\s+(left off|stopped)\b/i,
        /\b(still|again|once more)\s+(the same|that same)\b/i,
        /\b(remember|recall)\s+(when|that|the)\b/i,
      ];
      for (const re of patterns) {
        const m = prompt.match(re);
        if (m) return { ambiguous: true, reason: `References prior conversation that may not be in current context — "${m[0]}"`, severity: 'high' };
      }
      return { ambiguous: false };
    },
  },

  // MEDIUM: No file paths or code locations mentioned in a code-change request
  {
    name: 'no-file-paths',
    test(prompt) {
      // Only flag if it looks like a code-change request
      const actionVerbs = /\b(add|create|write|implement|build|develop|code|program|change|modify|update|fix|repair|refactor|rewrite|remove|delete|replace|rename|move|extract|split|merge|optimize|improve|enhance|upgrade|downgrade|patch)\b/i;
      if (!actionVerbs.test(prompt)) return { ambiguous: false };

      // Check for file path indicators
      const hasFilePath = /(?:\/[a-zA-Z0-9._\-\/]+|[a-zA-Z]:\\[a-zA-Z0-9._\-\\]+|`[a-zA-Z0-9._\-\\\/]+`|"[a-zA-Z0-9._\-\\\/]+\.(?:js|ts|py|go|rs|java|rb|c|cpp|h|hpp|css|html|json|yaml|yml|toml|sh|bat|ps1|sql|md|txt)"|'[a-zA-Z0-9._\-\\\/]+\.(?:js|ts|py|go|rs|java|rb|c|cpp|h|hpp|css|html|json|yaml|yml|toml|sh|bat|ps1|sql|md|txt)')/.test(prompt);
      const hasFilePathLoose = /\b[a-zA-Z0-9_\-]+\.(?:jsx?|tsx?|py|go|rs|java|rb|c|cpp|h|hpp|css|scss|html|vue|svelte|json|yaml|yml|toml|sh|bat|ps1|sql|md|txt)\b/i.test(prompt);
      const hasComponentName = /\b(?:in|on|at|for|to|from|of)\s+(?:the\s+)?(?:file|function|class|component|module|package|route|endpoint|handler|middleware|service|controller|model|view|template|hook|util|helper|config)\b/i.test(prompt);
      const hasDirectoryHint = /\b(?:in|under|inside|within|at)\s+(?:the\s+)?[`"']?[a-zA-Z0-9_\-\\\/]+[`"']?\b/i.test(prompt);

      if (!hasFilePath && !hasFilePathLoose && !hasComponentName && !hasDirectoryHint) {
        return { ambiguous: true, reason: 'Code-change request with no file path, component, or directory mentioned — Claude may guess the wrong target', severity: 'medium' };
      }
      return { ambiguous: false };
    },
  },

  // MEDIUM: Vague optimization/improvement request without criteria
  {
    name: 'vague-optimization',
    test(prompt) {
      const patterns = [
        /\b(make|get)\s+(it|this|the code|the app|the system)\s+(faster|quicker|more efficient|better|improved|optimized)\b/i,
        /\b(optimize|improve|enhance)\s+(performance|speed|efficiency)\b(?!.+?(?:by|from|to|reduce|cut|ms|seconds|percent|%|\d))/i,
        /\b(make|render)\s+(it|this)\s+(prettier|nicer|cleaner|better looking)\b/i,
        /\b(refactor|clean up|tidy)\s+(this|the code|everything|the whole)\b(?!.+?(?:file|function|class|module|in|on))/i,
      ];
      for (const re of patterns) {
        const m = prompt.match(re);
        if (m) return { ambiguous: true, reason: `Vague improvement request without measurable criteria — "${m[0]}"`, severity: 'medium' };
      }
      return { ambiguous: false };
    },
  },

  // MEDIUM: Extremely short prompt (< 30 chars) that implies an action
  {
    name: 'too-short',
    test(prompt) {
      const stripped = prompt.replace(/\s+/g, ' ').trim();
      if (stripped.length < 30) {
        const looksLikeAction = /\b(do|run|go|fix|add|make|build|create|change|update|show|find|get|check|test|start|stop|deploy|push|commit|merge|review|read|open|edit|write|delete|remove|move|copy)\b/i.test(stripped);
        if (looksLikeAction) {
          return { ambiguous: true, reason: `Very short prompt (${stripped.length} chars) — likely missing context, constraints, or expected outcome`, severity: 'medium' };
        }
      }
      return { ambiguous: false };
    },
  },

  // LOW/MEDIUM: "just" / "simply" — often masks hidden complexity
  {
    name: 'oversimplified',
    test(prompt) {
      const patterns = [
        /\b(just|simply|merely|only)\s+(add|make|do|create|fix|change|update|remove|delete|modify|set up|configure|install|run|build|deploy|test)\b/i,
        /\b(quick|easy|simple|small|tiny|minor|trivial)\s+(fix|change|update|edit|patch|tweak|adjustment)\b/i,
      ];
      for (const re of patterns) {
        const m = prompt.match(re);
        if (m) return { ambiguous: true, reason: `Downplayed complexity: "${m[0]}" — the task may have hidden scope or side effects`, severity: 'medium' };
      }
      return { ambiguous: false };
    },
  },
];

// ── Main ─────────────────────────────────────────────────────────────────────

function main() {
  let input;
  try {
    const chunks = [];
    process.stdin.setEncoding('utf8');
    process.stdin.on('readable', function () {
      let chunk;
      while ((chunk = process.stdin.read()) !== null) {
        chunks.push(chunk);
      }
    });

    process.stdin.on('end', function () {
      try {
        input = JSON.parse(chunks.join(''));
      } catch (e) {
        // Can't parse — pass through
        process.stdout.write(JSON.stringify({
          hookSpecificOutput: {
            hookEventName: 'UserPromptSubmit',
            additionalContext: '',
          },
        }) + '\n');
        return;
      }

      const prompt = input.prompt || '';

      // Run all detectors
      const findings = [];
      for (const detector of DETECTORS) {
        const result = detector.test(prompt);
        if (result.ambiguous) {
          findings.push({ detector: detector.name, ...result });
        }
      }

      if (findings.length === 0) {
        // Clean prompt — no injection needed
        process.stdout.write(JSON.stringify({
          hookSpecificOutput: {
            hookEventName: 'UserPromptSubmit',
            additionalContext: '',
          },
        }) + '\n');
        return;
      }

      const highSeverity = findings.filter(f => f.severity === 'high');
      const mediumSeverity = findings.filter(f => f.severity === 'medium');

      // Build the injection
      const lines = [
        '',
        '---',
        '## ⚠️ CLARITY CHECK — READ BEFORE ACTING',
        '',
        'The user\'s prompt triggered ambiguity detection. Before you write any code or make any changes, you MUST evaluate whether you truly understand what is being asked.',
        '',
      ];

      if (highSeverity.length > 0) {
        lines.push('### 🚨 AMBIGUOUS INPUT — MUST clarify before acting:');
        for (const f of highSeverity) {
          lines.push('- ' + f.reason);
        }
        lines.push('');
        lines.push('Ask concise questions. Do NOT act until resolved. Caveman-style: short, direct, pick one path.');
        lines.push('');
      }

      if (mediumSeverity.length > 0) {
        lines.push('### ⚡ UNCLEAR INPUT — verify or assume:');
        for (const f of mediumSeverity) {
          lines.push('- ' + f.reason);
        }
        lines.push('');
        lines.push('Pick one: state assumption + proceed, or ask short clarifying question.');
        lines.push('');
      }

      lines.push('Understandable = no doubts where to look, what to do, which approach. 2+ paths + no pick → ASK.');
      lines.push('---');

      const additionalContext = lines.join('\n');

      process.stdout.write(JSON.stringify({
        hookSpecificOutput: {
          hookEventName: 'UserPromptSubmit',
          additionalContext: additionalContext,
        },
      }) + '\n');
    });
  } catch (e) {
    // Failsafe — pass through
    process.stdout.write(JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'UserPromptSubmit',
        additionalContext: '',
      },
    }) + '\n');
  }
}

main();
