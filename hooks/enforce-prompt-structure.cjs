#!/usr/bin/env node
/**
 * enforce-prompt-structure.cjs — UserPromptSubmit hook
 *
 * Checks if a task-oriented user prompt follows a structured format.
 * If the prompt lacks structure (Context / Task / Constraints / Expected output),
 * injects the user's preferred template as a gentle reminder.
 *
 * Only activates for prompts that look like work requests (not casual chat).
 * The template shown is the user's preferred format.
 *
 * Place in: ~/.claude/hooks/enforce-prompt-structure.cjs
 * Register in: ~/.claude/settings.json under hooks.UserPromptSubmit
 */

const fs = require('fs');
const path = require('path');

// ── Configuration ────────────────────────────────────────────────────────────

// The preferred prompt template — injected when structure is missing.
// Customize this to match your preferred format.
var PREFERRED_TEMPLATE = [
  'Context: [project, files, background]',
  'Task: [what to do]',
  'Constraints: [rules, limits, what NOT to do]',
  'Expected: [what success looks like]',
].join('\n');

// Minimum prompt length to even consider (skip very short prompts)
var MIN_LENGTH = 25;

// ── Structure detection ──────────────────────────────────────────────────────

/**
 * Checks if the prompt already has recognizable structure.
 * Returns { hasStructure: bool, missing: string[] }
 */
function analyzeStructure(prompt) {
  const missing = [];

  // Section headers (like "Context:", "Task:", "## Context", etc.)
  const hasContext = /\b(?:Context|Background|Setup|Environment|Where|Project):?\s*\S/i.test(prompt) ||
                     /\b(?:in|under|inside|at)\s+(?:the\s+)?(?:project|repo|directory|folder|file)\b/i.test(prompt) ||
                     /\b(?:working on|working in|working with)\b/i.test(prompt);

  const hasTask = /\b(?:Task|Goal|Objective|Action|What|Request|Need):?\s*\S/i.test(prompt) ||
                  /\b(?:I (?:want|need|would like)|please|could you|can you)\b/i.test(prompt);

  const hasConstraints = /\b(?:Constraints?|Limitations?|Rules?|Restrictions?|Do NOT|Don't|Avoid|Scope|Boundaries?|Notes?):?\s*\S/i.test(prompt) ||
                         /\b(?:don't|do not|never|avoid|without|except|only if|must not|shouldn't)\b/i.test(prompt);

  const hasExpected = /\b(?:Expected|Output|Result|Success|Deliverable|Outcome|Verify|Check|Acceptance):?\s*\S/i.test(prompt) ||
                      /\b(?:should (?:produce|output|return|result|generate|create|show|display))\b/i.test(prompt) ||
                      /\b(?:when (?:done|finished|complete)|I expect|the result should)\b/i.test(prompt);

  if (!hasContext) missing.push('Context');
  if (!hasTask) missing.push('Task');
  if (!hasConstraints) missing.push('Constraints');
  if (!hasExpected) missing.push('Expected');

  // If 3+ sections are present, consider it structured
  const presentCount = [hasContext, hasTask, hasConstraints, hasExpected].filter(Boolean).length;
  const hasStructure = presentCount >= 3;

  return { hasStructure, missing, presentCount };
}

/**
 * Determines if this prompt is a "work request" that should have structure.
 * Casual questions, simple commands, and short requests are exempt.
 */
function isWorkRequest(prompt) {
  const stripped = prompt.replace(/\s+/g, ' ').trim();

  // Too short — probably not a work request needing structure
  if (stripped.length < MIN_LENGTH) return false;

  // Casual conversation starters
  const casualPatterns = [
    /^(hi|hey|hello|yo|sup|good morning|good afternoon|good evening|howdy)\b/i,
    /^(thanks|thank you|thx|ty|appreciate it|awesome|great|nice|perfect|amazing)\b/i,
    /^(what is|what's|what are|how does|how do|how is|how are|can you explain|explain|tell me about|tell me what)\b/i,
    /^(yes|no|yep|nope|ok|okay|sure|alright|fine|agreed|sounds good|go ahead|proceed)\b/i,
    /^(I see|got it|understood|makes sense|fair enough|I understand)\b/i,
    /^(good|great|nice|awesome|perfect|amazing|excellent|well done|good job)\b/i,
    /^(what do you think|wdyt|thoughts|opinions|any ideas)\b/i,
    /^(who|when|where|why|which) /i,  // Pure information questions
  ];

  for (const pattern of casualPatterns) {
    if (pattern.test(stripped)) return false;
  }

  // Work request indicators
  const workPatterns = [
    /\b(add|create|write|implement|build|develop|code|program)\b/i,
    /\b(change|modify|update|fix|repair|refactor|rewrite|remove|delete|replace|rename)\b/i,
    /\b(move|extract|split|merge|optimize|improve|enhance|upgrade|downgrade|patch)\b/i,
    /\b(install|configure|set up|deploy|publish|release|ship|launch)\b/i,
    /\b(review|audit|check|inspect|examine|analyze|investigate|debug|troubleshoot)\b/i,
    /\b(test|validate|verify|ensure|make sure)\b/i,
    /\b(design|architect|plan|structure|organize|layout)\b/i,
    /\b(convert|migrate|port|transform|translate|adapt)\b/i,
    /\b(generate|scaffold|bootstrap|initialize|start a new)\b/i,
    /\b(document|comment|annotate|explain the code|write docs)\b/i,
    /\b(search|find|locate|grep|look for|hunt)\b/i,
    /\b(integrate|connect|wire|hook up|plug in|link)\b/i,
    /\b(handle|support|accommodate|deal with)\b/i,
    /^[`"'].+\.(?:jsx?|tsx?|py|go|rs|java|rb|c|cpp|h|hpp|css|scss|html|vue|svelte|sql|yaml|yml)[`"']/i,  // Starts with a file path
  ];

  for (const pattern of workPatterns) {
    if (pattern.test(stripped)) return true;
  }

  // Default: if it's long and not casual, treat as work request
  if (stripped.length > 200) return true;

  return false;
}

// ── Main ─────────────────────────────────────────────────────────────────────

function main() {
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
      let input;
      try {
        input = JSON.parse(chunks.join(''));
      } catch (e) {
        process.stdout.write(JSON.stringify({
          hookSpecificOutput: {
            hookEventName: 'UserPromptSubmit',
            additionalContext: '',
          },
        }) + '\n');
        return;
      }

      const prompt = input.prompt || '';

      // Only analyze work requests
      if (!isWorkRequest(prompt)) {
        process.stdout.write(JSON.stringify({
          hookSpecificOutput: {
            hookEventName: 'UserPromptSubmit',
            additionalContext: '',
          },
        }) + '\n');
        return;
      }

      const { hasStructure, missing, presentCount } = analyzeStructure(prompt);

      if (hasStructure) {
        // Well-structured — no injection needed
        process.stdout.write(JSON.stringify({
          hookSpecificOutput: {
            hookEventName: 'UserPromptSubmit',
            additionalContext: '',
          },
        }) + '\n');
        return;
      }

      // Structure is missing — inject template reminder
      var presentNote = presentCount > 0
        ? 'Prompt has ' + presentCount + '/4 elements. Missing: ' + missing.join(', ')
        : 'No structure elements found.';

      var additionalContext = [
        '',
        '---',
        '## PROMPT STRUCTURE — missing context',
        '',
        presentNote,
        '',
        'Preferred format:',
        '```',
        PREFERRED_TEMPLATE,
        '```',
        '',
        'If missing parts obvious → state assumption + proceed. If unclear → ask concisely.',
        'Structured prompts = fewer rounds = less token waste.',
        '---',
      ].join('\n');

      process.stdout.write(JSON.stringify({
        hookSpecificOutput: {
          hookEventName: 'UserPromptSubmit',
          additionalContext: additionalContext,
        },
      }) + '\n');
    });
  } catch (e) {
    process.stdout.write(JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'UserPromptSubmit',
        additionalContext: '',
      },
    }) + '\n');
  }
}

main();
