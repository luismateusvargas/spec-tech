#!/usr/bin/env node
/**
 * learning-inject.cjs — UserPromptSubmit hook
 *
 * Injects relevant past learnings into the AI context based on the
 * user's prompt. Queries the JSON learning store for:
 * - Past spec errors related to the current task domain
 * - Past decisions related to the current task domain
 * - Deferred opportunities that match the current context
 *
 * Data file: ~/.claude/hooks/learnings.json
 *
 * Place: ~/.claude/hooks/learning-inject.cjs
 * Register: settings.json → hooks.UserPromptSubmit
 */

'use strict';

const fs = require('fs');
const path = require('path');

// ─── Configuration ───────────────────────────────────────────────────────────

const HOME = process.env.HOME || process.env.USERPROFILE || require('os').homedir();
const DATA_FILE = path.join(HOME, '.claude', 'hooks', 'learnings.json');
const CWD = process.env.CLAUDE_PROJECT_DIR || process.cwd();
const MAX_ENTRIES = 5;  // max learnings to inject (keep context small)

// ─── Helpers ──────────────────────────────────────────────────────────────────

function readStdin() {
    return new Promise((resolve, reject) => {
        let data = '';
        process.stdin.setEncoding('utf8');
        process.stdin.on('data', chunk => { data += chunk; });
        process.stdin.on('end', () => {
            try { resolve(JSON.parse(data)); }
            catch (e) { reject(new Error('Failed to parse stdin JSON: ' + e.message)); }
        });
        process.stdin.on('error', reject);
    });
}

function loadStore() {
    try {
        if (fs.existsSync(DATA_FILE)) {
            const raw = fs.readFileSync(DATA_FILE, 'utf8');
            return JSON.parse(raw);
        }
    } catch (e) { /* no store yet, corrupt file */ }
    return { learnings: [], decision_log: [] };
}

/**
 * Extract domain keywords from user prompt.
 * Maps common words to SDD domain areas.
 */
function extractKeywords(prompt) {
    const domainMap = {
        'auth': ['auth', 'login', 'logout', 'token', 'jwt', 'session', 'oauth', 'password', 'credential'],
        'payments': ['payment', 'stripe', 'billing', 'invoice', 'charge', 'refund', 'checkout'],
        'database': ['database', 'sql', 'postgres', 'sqlite', 'mongo', 'migration', 'schema', 'model', 'orm'],
        'api': ['api', 'endpoint', 'route', 'rest', 'graphql', 'request', 'response', 'http'],
        'deployment': ['deploy', 'docker', 'kubernetes', 'ci/cd', 'pipeline', 'production', 'staging', 'server'],
        'security': ['security', 'vulnerability', 'cve', 'injection', 'xss', 'csrf', 'encrypt', 'hash', 'ssl', 'tls'],
        'testing': ['test', 'spec', 'mock', 'stub', 'coverage', 'assertion', 'unit test', 'integration'],
        'performance': ['performance', 'slow', 'optimize', 'cache', 'latency', 'throughput', 'bottleneck'],
        'messaging': ['rabbitmq', 'kafka', 'queue', 'message', 'event', 'pubsub', 'publish', 'subscribe', 'consumer'],
    };

    const keywords = new Set();
    const lower = prompt.toLowerCase();

    for (const [domain, terms] of Object.entries(domainMap)) {
        for (const term of terms) {
            if (lower.includes(term)) {
                keywords.add(domain);
                break;
            }
        }
    }

    return keywords;
}

function getProjectName() {
    try {
        const basename = path.basename(CWD);
        return basename;
    } catch (e) {
        return '';
    }
}

/**
 * Score a learning entry for relevance to the current prompt.
 * Returns 0-1 relevance score.
 */
function scoreRelevance(entry, keywords, projectName) {
    let score = 0;

    // Same project = boost
    if (entry.project && entry.project.includes(projectName)) {
        score += 0.3;
    }

    // Category matches prompt intent
    const lowerPrompt = (entry.title + ' ' + entry.description).toLowerCase();

    // Spec errors/incomplete → high relevance when working on specs
    if (entry.category === 'spec_error' || entry.category === 'spec_incomplete') {
        if (lowerPrompt.includes('spec') || lowerPrompt.includes('implement')) {
            score += 0.2;
        }
    }

    // Decision entries are always somewhat relevant
    if (entry.category === 'decision') {
        score += 0.15;
    }

    // Recent entries are more relevant (last 7 days)
    if (entry.created_at) {
        const age = Date.now() - new Date(entry.created_at).getTime();
        if (age < 7 * 24 * 60 * 60 * 1000) {
            score += 0.2;
        } else if (age < 30 * 24 * 60 * 60 * 1000) {
            score += 0.1;
        }
    }

    // Deferred/accepted opportunities are relevant
    if (entry.resolution === 'deferred') {
        score += 0.1;
    }

    // Tag/keyword match
    if (entry.tags) {
        for (const tag of entry.tags) {
            if (keywords.has(tag.toLowerCase())) score += 0.15;
        }
    }

    return Math.min(score, 1.0);
}

function formatEntry(entry, index) {
    const date = entry.created_at ? entry.created_at.substring(0, 10) : 'unknown';
    const categoryLabel = {
        'spec_error': '⚠️  SPEC ERROR',
        'spec_incomplete': '⚠️  SPEC INCOMPLETE',
        'implementation': '💡 IMPLEMENTATION NOTE',
        'discovery': '🔍 DISCOVERY',
        'decision': '📋 DECISION',
        'failure': '❌ FAILURE',
    }[entry.category] || entry.category.toUpperCase();

    let lines = [];
    lines.push(`**${index}. ${categoryLabel}** — ${entry.title} (${date})`);

    if (entry.description) {
        lines.push(`   ${entry.description.substring(0, 200)}`);
    }
    if (entry.rationale) {
        lines.push(`   Rationale: ${entry.rationale.substring(0, 150)}`);
    }
    if (entry.evidence && entry.evidence.length > 0 && typeof entry.evidence[0] === 'object') {
        lines.push(`   Evidence: ${entry.evidence[0].file}`);
    }
    if (entry.resolution) {
        lines.push(`   Resolution: ${entry.resolution}`);
    }
    lines.push('');

    return lines.join('\n');
}

// ─── Main Inject Logic ───────────────────────────────────────────────────────

async function inject() {
    try {
        const payload = await readStdin();
        const prompt = payload.prompt || '';

        // Skip injection for very short prompts (don't waste context)
        if (prompt.length < 20) {
            return {
                hookSpecificOutput: {
                    hookEventName: 'UserPromptSubmit',
                    additionalContext: ''
                }
            };
        }

        const store = loadStore();
        if (store.learnings.length === 0) {
            return {
                hookSpecificOutput: {
                    hookEventName: 'UserPromptSubmit',
                    additionalContext: ''
                }
            };
        }

        const keywords = extractKeywords(prompt);
        const projectName = getProjectName();

        // Score and rank learnings
        const ranked = store.learnings
            .map(entry => ({ entry, score: scoreRelevance(entry, keywords, projectName) }))
            .filter(r => r.score > 0.15)  // minimum relevance threshold
            .sort((a, b) => b.score - a.score)
            .slice(0, MAX_ENTRIES);

        if (ranked.length === 0) {
            return {
                hookSpecificOutput: {
                    hookEventName: 'UserPromptSubmit',
                    additionalContext: ''
                }
            };
        }

        // Format the injection
        let context = '\n---\n';
        context += '## 🧠 SDD LEARNING STORE — Relevant Past Context\n\n';
        context += '> These are learnings from previous sessions that may be relevant to your current task.\n';
        context += '> Use this context to avoid repeating past mistakes. Not instructions — information.\n\n';

        ranked.forEach((r, i) => {
            context += formatEntry(r.entry, i + 1);
        });

        context += '---\n';

        return {
            hookSpecificOutput: {
                hookEventName: 'UserPromptSubmit',
                additionalContext: context
            }
        };

    } catch (e) {
        // Never crash — hooks must be silent on failure
        if (process.env.DEBUG_LEARNINGS) {
            process.stderr.write('[learning-inject] ERROR: ' + e.message + '\n');
        }
        return {
            hookSpecificOutput: {
                hookEventName: 'UserPromptSubmit',
                additionalContext: ''
            }
        };
    }
}

// ─── Execute ──────────────────────────────────────────────────────────────────

inject().then(result => {
    process.stdout.write(JSON.stringify(result) + '\n');
    process.exit(0);
}).catch(() => {
    process.stdout.write(JSON.stringify({
        hookSpecificOutput: { hookEventName: 'UserPromptSubmit', additionalContext: '' }
    }) + '\n');
    process.exit(0);
});
