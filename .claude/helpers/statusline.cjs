#!/usr/bin/env node
// Claude Code status line (Node — no jq dependency; git-bash on Windows has no jq).
// Layout:
//   <model> | effort:<x> | ctx:<n>% | 5h:<n>% 7d:<n>% | agents:<n> | +<adds>/-<dels>
//   | <repo> ⎇ <branch> ±<dirty> ↑<ahead>↓<behind> | ⚑ handoff | <activity>
// Segments render only when they carry signal (no agents -> no agents segment, clean
// tree -> no ±, medium effort -> hidden, ...).
//
// Same script lives in two places — keep them in sync:
//   .claude/helpers/statusline.cjs        (this repo, wired in .claude/settings.json)
//   ~/.claude/statusline-command.js       (user-global fallback for other repos)
'use strict';

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

// ── Read the status-line payload from stdin ─────────────────────────
let input = {};
try {
  const raw = fs.readFileSync(0, 'utf8');
  input = JSON.parse(raw);
} catch (_) { /* leave input as {} */ }

const cwd =
  (input.workspace && input.workspace.current_dir) || input.cwd || process.cwd();
const projectDir = (input.workspace && input.workspace.project_dir) || cwd;
const transcript = input.transcript_path || '';

// ── Model ───────────────────────────────────────────────────────────
const model = (input.model && input.model.display_name) || '';

// ── Effort — from payload first (most up-to-date), else settings files
const effort =
  (input.effort && input.effort.level) ||
  (() => {
    function readJson(p) {
      try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (_) { return null; }
    }
    const userHome = process.env.USERPROFILE || process.env.HOME || '';
    const candidates = [
      path.join(cwd, '.claude', 'settings.local.json'),
      path.join(cwd, '.claude', 'settings.json'),
      path.join(userHome, '.claude', 'settings.json'),
    ];
    for (const p of candidates) {
      const j = readJson(p);
      if (j && j.effortLevel) return String(j.effortLevel);
    }
    return '';
  })();

// ── Rate limits (session 5-hour + weekly 7-day) ─────────────────────
const rl = input.rate_limits || {};
const fiveHour = rl.five_hour ? Math.round(rl.five_hour.used_percentage) : null;
const sevenDay = rl.seven_day ? Math.round(rl.seven_day.used_percentage) : null;

// ── Context window % ────────────────────────────────────────────────
let ctxPct = null;
if (input.context_window) {
  const cw = input.context_window;
  const used =
    (cw.total_input_tokens || 0) ||
    ((cw.current_usage || {}).input_tokens || 0) +
    ((cw.current_usage || {}).cache_creation_input_tokens || 0) +
    ((cw.current_usage || {}).cache_read_input_tokens || 0);
  const limit = cw.context_window_size || (input.exceeds_200k_tokens ? 1000000 : 200000);
  if (used > 0 && limit > 0) ctxPct = Math.min(100, Math.round((used / limit) * 100));
}

// ── Lines added / removed this session ──────────────────────────────
const linesAdded = (input.cost && input.cost.total_lines_added) || 0;
const linesRemoved = (input.cost && input.cost.total_lines_removed) || 0;

// ── Walk the transcript for active agents + ctx fallback + activity ──
let activeAgents = 0;
let aiTitle = '';
let lastPrompt = '';

if (transcript && fs.existsSync(transcript)) {
  let lines = [];
  try { lines = fs.readFileSync(transcript, 'utf8').trim().split(/\r?\n/); } catch (_) {}

  const agentUses = [];
  const results = new Set();
  let usageFound = ctxPct !== null; // skip transcript scan if payload already has it

  for (let i = lines.length - 1; i >= 0; i--) {
    let o;
    try { o = JSON.parse(lines[i]); } catch (_) { continue; }

    if (!usageFound && o.type === 'assistant' && o.message && o.message.usage) {
      const u = o.message.usage;
      const used =
        (u.input_tokens || 0) +
        (u.cache_creation_input_tokens || 0) +
        (u.cache_read_input_tokens || 0);
      const limit = input.exceeds_200k_tokens ? 1000000 : 200000;
      ctxPct = Math.min(100, Math.round((used / limit) * 100));
      usageFound = true;
    }

    if (!aiTitle && o.type === 'ai-title' && o.aiTitle) aiTitle = o.aiTitle;
    if (!lastPrompt && o.type === 'last-prompt' && o.lastPrompt) lastPrompt = o.lastPrompt;
  }

  for (const l of lines) {
    let o;
    try { o = JSON.parse(l); } catch (_) { continue; }
    const msg = o.message;
    if (msg && Array.isArray(msg.content)) {
      for (const c of msg.content) {
        if (c.type === 'tool_use' && (c.name === 'Agent' || c.name === 'Task')) {
          agentUses.push(c.id);
        }
        if (c.type === 'tool_result' && c.tool_use_id) {
          results.add(c.tool_use_id);
        }
      }
    }
  }
  activeAgents = agentUses.filter((id) => !results.has(id)).length;
}

// ── Activity: prefer ai-title, else session_name, else last prompt ───
let activity = aiTitle || input.session_name || lastPrompt || '';
activity = activity.replace(/\s+/g, ' ').trim();
if (activity.length > 48) activity = activity.slice(0, 47) + '…';

// ── Git: branch + ahead/behind + dirty counts (one porcelain call) ───
const git = { branch: '', ahead: 0, behind: 0, changed: 0, untracked: 0, ok: false };
try {
  const out = execFileSync(
    'git',
    ['--no-optional-locks', 'status', '--porcelain=v2', '--branch'],
    { cwd, stdio: ['ignore', 'pipe', 'ignore'], timeout: 1500 }
  ).toString();
  git.ok = true;
  for (const line of out.split('\n')) {
    if (line.startsWith('# branch.head ')) git.branch = line.slice(14).trim();
    else if (line.startsWith('# branch.ab ')) {
      const m = line.match(/\+(\d+) -(\d+)/);
      if (m) { git.ahead = +m[1]; git.behind = +m[2]; }
    } else if (/^[12u] /.test(line)) git.changed++;
    else if (line.startsWith('? ')) git.untracked++;
  }
} catch (_) {}

// ── Pending handoff flag (see docs/howto/claude-workflow.md) ─────────
const handoffPending = fs.existsSync(path.join(projectDir, 'var', 'handoff-pending'));

// ── Colour helpers ──────────────────────────────────────────────────
const dim   = (s) => `\x1b[2m${s}\x1b[0m`;
const bold  = (s) => `\x1b[1m${s}\x1b[0m`;
const cyan  = (s) => `\x1b[36m${s}\x1b[0m`;
const green = (s) => `\x1b[32m${s}\x1b[0m`;
const amber = (s) => `\x1b[33m${s}\x1b[0m`;
const red   = (s) => `\x1b[31m${s}\x1b[0m`;
// nexora-ui signature accents (truecolor; fine in Windows Terminal)
const indigo = (s) => `\x1b[38;2;99;102;241m${s}\x1b[0m`;
const violet = (s) => `\x1b[38;2;139;92;246m${s}\x1b[0m`;

function pctColor(pct, s) {
  if (pct >= 85) return red(s);
  if (pct >= 60) return amber(s);
  return green(s);
}

// ── Assemble ────────────────────────────────────────────────────────
const sep = dim(' │ ');
const parts = [];

if (model) parts.push(bold(violet(model)));

if (effort && effort !== 'medium') parts.push(dim(`effort:${effort}`));

if (ctxPct !== null) parts.push(pctColor(ctxPct, `ctx:${ctxPct}%`));

const limits = [];
if (fiveHour !== null) limits.push(pctColor(fiveHour, `5h:${fiveHour}%`));
if (sevenDay !== null) limits.push(pctColor(sevenDay, `7d:${sevenDay}%`));
if (limits.length) parts.push(limits.join(' '));

if (activeAgents > 0) parts.push(cyan(`agents:${activeAgents}`));

if (linesAdded > 0 || linesRemoved > 0) {
  parts.push(`${green(`+${linesAdded}`)}${dim('/')}${red(`-${linesRemoved}`)}`);
}

if (git.ok && git.branch) {
  const bits = [dim(path.basename(projectDir)), indigo(`⎇ ${git.branch}`)];
  const dirty = git.changed + git.untracked;
  if (dirty > 0) bits.push(amber(`±${dirty}`));
  if (git.ahead > 0) bits.push(cyan(`↑${git.ahead}`));
  if (git.behind > 0) bits.push(amber(`↓${git.behind}`));
  parts.push(bits.join(' '));
}

if (handoffPending) parts.push(violet('⚑ handoff'));

if (activity) parts.push(dim(activity));

process.stdout.write(parts.join(sep));
