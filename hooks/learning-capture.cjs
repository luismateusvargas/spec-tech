#!/usr/bin/env node
/**
 * learning-capture.cjs — PostToolUse hook (matcher: Edit|Write)
 *
 * Auto-captures learnings from spec updates, CHALLENGE resolutions,
 * and implementation activity into the JSON learning store.
 *
 * Monitors for patterns that indicate learning opportunities:
 * - Spec file edits (track decision rationale changes)
 * - Guardian CHALLENGE verdicts being resolved
 * - Implementation patterns worth recording
 *
 * Data file: ~/.claude/hooks/learnings.json
 * Schema: matches learnings-schema.sql (SQLite target)
 *
 * Place: ~/.claude/hooks/learning-capture.cjs
 * Register: settings.json → hooks.PostToolUse, matcher: "Edit|Write"
 */

'use strict';

const fs = require('fs');
const path = require('path');

// ─── Configuration ───────────────────────────────────────────────────────────

const HOME = process.env.HOME || process.env.USERPROFILE || require('os').homedir();
const DATA_FILE = path.join(HOME, '.claude', 'hooks', 'learnings.json');
const MIN_CONTENT_LENGTH = 50;  // ignore tiny edits (typo fixes, etc.)

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
    } catch (e) { /* corrupt file, start fresh */ }
    return { learnings: [], decision_log: [] };
}

function saveStore(store) {
    const dir = path.dirname(DATA_FILE);
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
    }
    fs.writeFileSync(DATA_FILE, JSON.stringify(store, null, 2), 'utf8');
}

function generateId() {
    return 'LRN-' + Date.now().toString(36).toUpperCase() + '-' +
           Math.random().toString(36).substring(2, 6).toUpperCase();
}

function extractProject(filePath) {
    // Extract project root from file path
    const normalized = filePath.replace(/\\/g, '/');
    const parts = normalized.split('/');
    // Look for known project markers
    for (let i = parts.length - 1; i >= 0; i--) {
        const dir = parts.slice(0, i + 1).join('/');
        const hasClaude = fs.existsSync(path.join(dir, '.claude'));
        const hasSpecs = fs.existsSync(path.join(dir, 'specs'));
        if (hasClaude || hasSpecs) return dir;
    }
    return path.dirname(filePath); // fallback
}

function detectCategory(content, filePath) {
    const fname = path.basename(filePath).toLowerCase();

    // CHALLENGE resolution in spec files
    if (fname.endsWith('.yaml') || fname.endsWith('.yml')) {
        if (content.includes('CHALLENGE') && content.includes('SPEC_FACTUALLY_WRONG')) {
            return 'spec_error';
        }
        if (content.includes('CHALLENGE') && content.includes('SPEC_INCOMPLETE')) {
            return 'spec_incomplete';
        }
    }

    // Spec changes
    if (fname.endsWith('.spec.yaml') || fname.endsWith('.constitution.yaml')) {
        if (content.includes('rationale:') || content.includes('decisions:')) {
            return 'decision';
        }
    }

    // Implementation patterns
    if (fname.endsWith('.py') || fname.endsWith('.js') || fname.endsWith('.ts')) {
        if (content.includes('TODO') || content.includes('FIXME') || content.includes('HACK')) {
            return 'implementation';
        }
    }

    return null; // no actionable learning detected
}

function extractEvidence(content, filePath) {
    const evidence = [];
    const lines = content.split('\n');

    // Extract file references from the content
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const fileMatch = line.match(/(?:File|file|Evidence):\s*([^\s:]+:\d+)/);
        if (fileMatch) {
            evidence.push({
                file: fileMatch[1],
                line: i + 1,
                summary: line.substring(0, 200)
            });
        }
    }

    // If no explicit references, use the changed file itself
    if (evidence.length === 0) {
        evidence.push({
            file: filePath,
            line: 1,
            summary: 'Auto-captured from file modification'
        });
    }

    return evidence;
}

// ─── Main Capture Logic ──────────────────────────────────────────────────────

async function capture() {
    try {
        const payload = await readStdin();
        const toolName = payload.tool_name;
        const toolInput = payload.tool_input || {};
        const toolResponse = payload.tool_response || {};

        // Only process successful operations
        if (toolResponse.exitCode !== undefined && toolResponse.exitCode !== 0) {
            return { hookSpecificOutput: { hookEventName: 'PostToolUse', additionalContext: '' } };
        }

        const filePath = toolInput.file_path || '';
        if (!filePath) {
            return { hookSpecificOutput: { hookEventName: 'PostToolUse', additionalContext: '' } };
        }

        // Get the changed content
        let content = '';
        if (toolName === 'Write') {
            content = toolInput.content || '';
        } else if (toolName === 'Edit') {
            content = toolInput.new_string || '';
        }

        if (!content || content.length < MIN_CONTENT_LENGTH) {
            return { hookSpecificOutput: { hookEventName: 'PostToolUse', additionalContext: '' } };
        }

        // Detect if this edit has learnable content
        const category = detectCategory(content, filePath);
        if (!category) {
            return { hookSpecificOutput: { hookEventName: 'PostToolUse', additionalContext: '' } };
        }

        // Build learning entry
        const project = extractProject(filePath);
        const evidence = extractEvidence(content, filePath);
        const title = category === 'spec_error'
            ? 'Spec was factually wrong: ' + path.basename(filePath)
            : category === 'spec_incomplete'
                ? 'Spec was incomplete: ' + path.basename(filePath)
                : category === 'decision'
                    ? 'Decision recorded in: ' + path.basename(filePath)
                    : 'Implementation note: ' + path.basename(filePath);

        const entry = {
            id: generateId(),
            category: category,
            subcategory: '',
            title: title,
            description: content.substring(0, 500),
            project: project,
            spec_file: filePath,
            task_id: '',
            challenge_id: '',
            evidence: evidence,
            rationale: '',
            alternatives: [],
            resolution: 'experimental',
            source: 'auto',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            tags: []
        };

        // Save
        const store = loadStore();
        store.learnings.push(entry);

        // Keep only last 500 entries to prevent unbounded growth
        if (store.learnings.length > 500) {
            store.learnings = store.learnings.slice(-500);
        }

        saveStore(store);

        // Report to stderr for debugging only (stdout is for protocol)
        if (process.env.DEBUG_LEARNINGS) {
            process.stderr.write('[learning-capture] Captured: ' + entry.id + ' — ' + entry.title + '\n');
        }

        return {
            hookSpecificOutput: {
                hookEventName: 'PostToolUse',
                additionalContext: ''
            }
        };

    } catch (e) {
        // Never crash — hooks must be silent on failure
        if (process.env.DEBUG_LEARNINGS) {
            process.stderr.write('[learning-capture] ERROR: ' + e.message + '\n');
        }
        return {
            hookSpecificOutput: {
                hookEventName: 'PostToolUse',
                additionalContext: ''
            }
        };
    }
}

// ─── Execute ──────────────────────────────────────────────────────────────────

capture().then(result => {
    process.stdout.write(JSON.stringify(result) + '\n');
    process.exit(0);
}).catch(() => {
    process.stdout.write(JSON.stringify({
        hookSpecificOutput: { hookEventName: 'PostToolUse', additionalContext: '' }
    }) + '\n');
    process.exit(0);
});
