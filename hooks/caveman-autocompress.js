#!/usr/bin/env node
// caveman-autocompress — SessionEnd hook
// Compresses memory .md files to caveman style.
// Backs up originals as .original.md before overwrite.

const fs = require('fs');
const path = require('path');
const os = require('os');

const CLAUDE_DIR = process.env.CLAUDE_CONFIG_DIR || path.join(os.homedir(), '.claude');
const PROJECTS_DIR = path.join(CLAUDE_DIR, 'projects');
const EXT = '.original.md';

// Basic caveman compression rules for prose
function compressProse(text) {
  return text
    // Drop filler words at start of sentences/lines
    .replace(/\b(just|really|basically|actually|simply|literally|essentially|honestly)\b/gi, '')
    // Drop pleasantries
    .replace(/\b(sure|certainly|of course|happy to|gladly|absolutely|definitely)\b/gi, '')
    // Drop hedging
    .replace(/\b(maybe|perhaps|probably|possibly|might|i think|i believe|i feel|it seems|kind of|sort of|a bit|a little)\b/gi, '')
    // Drop articles at line starts
    .replace(/^The\s+/gim, '')
    .replace(/^A\s+/gim, '')
    .replace(/^An\s+/gim, '')
    // Condense multiple spaces
    .replace(/ +/g, ' ')
    // Clip leading/trailing whitespace per line
    .split('\n').map(l => l.trim()).join('\n')
    .trim();
}

function isSourceFile(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  const sourceExts = new Set(['.py', '.js', '.ts', '.json', '.yaml', '.yml', '.toml', '.sh', '.bat', '.ps1', '.css', '.html', '.env']);
  return sourceExts.has(ext);
}

// Split markdown into code/non-code blocks, compress prose only
function compressMarkdown(content) {
  const lines = content.split('\n');
  const result = [];
  let inCodeBlock = false;
  let codeFence = '```';

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Toggle code block state
    if (/^```/.test(line.trim())) {
      if (!inCodeBlock) {
        codeFence = line.match(/^(```+)/)[1];
      }
      inCodeBlock = !inCodeBlock;
      result.push(line);
      continue;
    }

    if (inCodeBlock) {
      result.push(line); // preserve code exactly
    } else if (line.startsWith('---') && i < 3) {
      result.push(line); // preserve YAML frontmatter markers
    } else if (
      line.startsWith('#') ||
      line.startsWith('>') ||
      line.startsWith('|') ||
      line.startsWith('- [') ||
      line.match(/^[\-\*]\s/) ||
      line.match(/^\d+\.\s/) ||
      line.match(/^\[.*\]\(.*\)/) ||
      line.trim() === ''
    ) {
      result.push(line); // preserve headings, blockquotes, tables, lists, links, empty lines
    } else if (line.match(/^https?:\/\//) || line.match(/^[a-zA-Z]:\\/) || line.match(/^\//)) {
      result.push(line); // preserve URLs, paths, absolute paths
    } else {
      // Compress prose lines
      const compressed = compressProse(line);
      if (compressed) result.push(compressed);
      // Skip empty lines that resulted from compression
    }
  }

  return result.join('\n');
}

function findMemoryDirs(dir) {
  const results = [];
  try {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      const memoryDir = path.join(dir, entry.name, 'memory');
      if (fs.existsSync(memoryDir)) {
        results.push(memoryDir);
      }
    }
  } catch (e) {}
  return results;
}

function compressDir(memoryDir) {
  let files;
  try {
    files = fs.readdirSync(memoryDir);
  } catch (e) {
    return;
  }

  for (const file of files) {
    const filePath = path.join(memoryDir, file);
    let stat;
    try { stat = fs.statSync(filePath); } catch (e) { continue; }
    if (!stat.isFile()) continue;
    if (file.endsWith(EXT)) continue;
    if (path.extname(file) !== '.md') continue;
    if (isSourceFile(file)) continue;

    let content;
    try { content = fs.readFileSync(filePath, 'utf8'); } catch (e) { continue; }

    // Skip already-compressed files (short, no filler indicators)
    const wordCount = content.split(/\s+/).length;
    const lineCount = content.split('\n').length;
    if (wordCount < 10) continue; // already short

    // Create backup if not exists
    const backupPath = filePath.replace(/\.md$/, EXT);
    if (!fs.existsSync(backupPath)) {
      try {
        fs.copyFileSync(filePath, backupPath);
      } catch (e) { continue; }
    }

    const compressed = compressMarkdown(content);
    try {
      fs.writeFileSync(filePath, compressed, 'utf8');
    } catch (e) {}
  }
}

function main() {
  const memoryDirs = findMemoryDirs(PROJECTS_DIR);

  // Also check CLAUDE_DIR/memory directly
  const userMemoryDir = path.join(CLAUDE_DIR, 'memory');
  if (fs.existsSync(userMemoryDir)) {
    memoryDirs.push(userMemoryDir);
  }

  for (const dir of memoryDirs) {
    compressDir(dir);
  }
}

main();
process.stdout.write('OK');
