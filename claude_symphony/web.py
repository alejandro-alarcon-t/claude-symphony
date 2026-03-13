"""Optional web dashboard and API (requires fastapi + uvicorn)."""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .orchestrator import Orchestrator

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse, JSONResponse
except ImportError:
    raise ImportError("Install web extras: pip install claude-symphony[web]")

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claude Symphony</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:        #080808;
    --surface:   #0f0f0f;
    --border:    #1c1c1c;
    --border-hi: #2a2a2a;
    --text:      #e8e8e0;
    --muted:     #555550;
    --dim:       #333330;
    --amber:     #e8b84b;
    --amber-dim: #6b5220;
    --green:     #4cba6e;
    --red:       #d95f52;
    --blue:      #5b9cf6;
    --font:      'IBM Plex Mono', monospace;
  }

  html, body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    font-size: 13px;
    line-height: 1.5;
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
  }

  /* Subtle grid background */
  body::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image:
      linear-gradient(var(--border) 1px, transparent 1px),
      linear-gradient(90deg, var(--border) 1px, transparent 1px);
    background-size: 40px 40px;
    opacity: 0.35;
    pointer-events: none;
    z-index: 0;
  }

  .shell {
    position: relative;
    z-index: 1;
    max-width: 1280px;
    margin: 0 auto;
    padding: 0 24px 60px;
  }

  /* ── Header ── */
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 28px 0 24px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 32px;
  }

  .logo {
    display: flex;
    align-items: baseline;
    gap: 12px;
  }

  .logo-name {
    font-size: 22px;
    font-weight: 600;
    letter-spacing: -0.5px;
    color: var(--text);
  }

  .logo-tag {
    font-size: 11px;
    font-weight: 300;
    color: var(--muted);
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 24px;
  }

  .status-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 8px var(--green);
    animation: pulse-green 2.5s ease-in-out infinite;
  }

  .status-dot.idle {
    background: var(--muted);
    box-shadow: none;
    animation: none;
  }

  @keyframes pulse-green {
    0%, 100% { opacity: 1; box-shadow: 0 0 6px var(--green); }
    50%       { opacity: 0.5; box-shadow: 0 0 12px var(--green); }
  }

  .timestamp {
    font-size: 11px;
    color: var(--muted);
    font-weight: 300;
    letter-spacing: 0.04em;
  }

  /* ── Metrics row ── */
  .metrics {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1px;
    background: var(--border);
    border: 1px solid var(--border);
    margin-bottom: 32px;
  }

  .metric {
    background: var(--surface);
    padding: 20px 24px;
    position: relative;
    overflow: hidden;
  }

  .metric::after {
    content: '';
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 2px;
    background: var(--border-hi);
    transition: background 0.3s;
  }

  .metric.active::after {
    background: var(--amber);
  }

  .metric-label {
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 8px;
  }

  .metric-value {
    font-size: 32px;
    font-weight: 600;
    color: var(--text);
    line-height: 1;
    letter-spacing: -1px;
    transition: color 0.3s;
  }

  .metric.active .metric-value {
    color: var(--amber);
  }

  .metric-sub {
    font-size: 11px;
    color: var(--muted);
    margin-top: 6px;
    font-weight: 300;
  }

  /* ── Section headers ── */
  .section-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
  }

  .section-title {
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--muted);
  }

  .section-line {
    flex: 1;
    height: 1px;
    background: var(--border);
  }

  .section-count {
    font-size: 10px;
    color: var(--dim);
    font-weight: 300;
  }

  /* Search box */
  .search-input {
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text);
    font-family: var(--font);
    font-size: 11px;
    padding: 4px 12px;
    width: 200px;
    outline: none;
    transition: border-color 0.15s;
  }
  .search-input:focus { border-color: var(--amber-dim); }
  .search-input::placeholder { color: var(--dim); }

  /* ── Agent cards ── */
  .agents {
    display: flex;
    flex-direction: column;
    gap: 1px;
    background: var(--border);
    border: 1px solid var(--border);
    margin-bottom: 32px;
  }

  .agent-card {
    background: var(--surface);
    padding: 18px 24px;
    display: grid;
    grid-template-columns: 100px 1fr auto;
    gap: 16px;
    align-items: start;
    cursor: pointer;
    transition: background 0.15s;
    border-left: 2px solid transparent;
  }

  .agent-card:hover {
    background: #141414;
  }

  .agent-card.selected {
    border-left-color: var(--amber);
    background: #121210;
  }

  .agent-id {
    font-size: 13px;
    font-weight: 600;
    color: var(--amber);
    letter-spacing: 0.02em;
  }

  .agent-title {
    font-size: 12px;
    font-weight: 400;
    color: var(--text);
    margin-bottom: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 620px;
  }

  .agent-status-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
  }

  .agent-state {
    font-size: 11px;
    color: var(--muted);
    font-weight: 300;
  }

  .status-pill {
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding: 2px 8px;
    border-radius: 2px;
  }

  .status-pill.streaming {
    background: rgba(232, 184, 75, 0.12);
    color: var(--amber);
    border: 1px solid var(--amber-dim);
  }

  .status-pill.streaming::before {
    content: '\\25B6 ';
    animation: blink 1.2s step-end infinite;
  }

  @keyframes blink {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0; }
  }

  .status-pill.paused {
    background: rgba(85,85,80,0.15);
    color: var(--muted);
    border: 1px solid var(--border-hi);
  }

  .status-pill.succeeded  { background: rgba(76,186,110,.1); color: var(--green); border: 1px solid rgba(76,186,110,.25); }
  .status-pill.failed     { background: rgba(217,95,82,.1);  color: var(--red);   border: 1px solid rgba(217,95,82,.25); }
  .status-pill.retrying   { background: rgba(91,156,246,.1); color: var(--blue);  border: 1px solid rgba(91,156,246,.25); }
  .status-pill.pending    { background: transparent;          color: var(--muted); border: 1px solid var(--border-hi); }
  .status-pill.gate       { background: rgba(232, 184, 75, 0.08); color: var(--amber-dim); border: 1px solid var(--amber-dim); }

  .agent-msg {
    font-size: 12px;
    color: var(--muted);
    font-weight: 300;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 620px;
  }

  .agent-meta {
    text-align: right;
    white-space: nowrap;
  }

  .agent-controls {
    display: flex;
    gap: 4px;
    margin-bottom: 6px;
    justify-content: flex-end;
  }

  .agent-control {
    padding: 2px 8px;
    border: 1px solid var(--amber-dim);
    background: rgba(232,184,75,0.08);
    color: var(--amber);
    font-family: var(--font);
    font-size: 11px;
    cursor: pointer;
    transition: background 0.15s;
  }
  .agent-control:hover { background: rgba(232,184,75,0.2); }
  .agent-control.stop { border-color: rgba(217,95,82,0.25); background: rgba(217,95,82,0.1); color: var(--red); }
  .agent-control.stop:hover { background: rgba(217,95,82,0.2); }

  .agent-tokens {
    font-size: 12px;
    color: var(--text);
    font-weight: 500;
    margin-bottom: 3px;
  }

  .agent-turns {
    font-size: 11px;
    color: var(--muted);
    font-weight: 300;
  }

  /* ── Empty state ── */
  .empty {
    background: var(--surface);
    border: 1px solid var(--border);
    padding: 48px 24px;
    text-align: center;
    margin-bottom: 32px;
  }

  .empty-title {
    font-size: 13px;
    color: var(--dim);
    margin-bottom: 6px;
    font-weight: 300;
    letter-spacing: 0.06em;
  }

  .empty-sub {
    font-size: 11px;
    color: var(--border-hi);
    font-weight: 300;
  }

  /* ── Detail panel ── */
  .detail-panel {
    background: #0a0a0a;
    border-top: 1px solid var(--border);
    padding: 16px 24px 20px;
    max-height: 420px;
    overflow-y: auto;
    animation: slideDown 0.2s ease-out;
  }
  @keyframes slideDown {
    from { max-height: 0; opacity: 0; padding-top: 0; padding-bottom: 0; }
    to   { max-height: 420px; opacity: 1; }
  }

  .detail-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 16px;
  }
  .detail-label {
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .detail-line { flex: 1; height: 1px; background: var(--border); }
  .detail-close {
    background: none;
    border: 1px solid var(--border);
    color: var(--muted);
    font-size: 12px;
    cursor: pointer;
    padding: 2px 8px;
    font-family: var(--font);
  }
  .detail-close:hover { color: var(--text); border-color: var(--border-hi); }

  /* Context section */
  .detail-context {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--border);
  }
  .ctx-item {
    font-size: 11px;
    color: var(--muted);
    font-weight: 300;
  }
  .ctx-item a { color: var(--blue); text-decoration: none; }
  .ctx-item a:hover { text-decoration: underline; }
  .ctx-label-pill {
    display: inline-block;
    font-size: 9px;
    padding: 1px 6px;
    background: rgba(91,156,246,0.1);
    color: var(--blue);
    border: 1px solid rgba(91,156,246,0.2);
    margin-left: 4px;
  }

  /* Log entries */
  .detail-log { max-height: 300px; overflow-y: auto; }
  .log-entry { display: flex; gap: 12px; padding: 6px 0; align-items: start; border-bottom: 1px solid rgba(28,28,28,0.5); }
  .log-entry:last-child { border-bottom: none; }
  .log-ts { width: 60px; color: var(--dim); font-size: 11px; flex-shrink: 0; padding-top: 1px; }
  .log-badge {
    min-width: 88px;
    text-align: center;
    font-size: 10px;
    font-weight: 500;
    padding: 3px 8px;
    flex-shrink: 0;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .log-badge.thinking { background: rgba(232,184,75,0.08); color: var(--amber); border: 1px solid var(--amber-dim); }
  .log-badge.tool_use { background: rgba(91,156,246,0.1); color: var(--blue); border: 1px solid rgba(91,156,246,0.25); }
  .log-badge.tool_result, .log-badge.result { background: rgba(76,186,110,0.1); color: var(--green); border: 1px solid rgba(76,186,110,0.25); }
  .log-badge.error { background: rgba(217,95,82,0.1); color: var(--red); border: 1px solid rgba(217,95,82,0.25); }
  .log-msg {
    flex: 1;
    font-size: 12px;
    color: var(--text);
    font-weight: 300;
    line-height: 1.4;
    cursor: pointer;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }
  .log-msg.expanded { -webkit-line-clamp: unset; display: block; }

  /* ── Modal ── */
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
    animation: fadeIn 0.15s ease-out;
  }
  @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
  .modal-box {
    background: var(--surface);
    border: 1px solid var(--border-hi);
    padding: 24px 32px;
    max-width: 420px;
    width: 100%;
  }
  .modal-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; }
  .modal-body { font-size: 12px; color: var(--muted); margin-bottom: 20px; line-height: 1.5; }
  .modal-actions { display: flex; justify-content: flex-end; gap: 8px; }
  .modal-btn {
    padding: 6px 16px;
    font-family: var(--font);
    font-size: 11px;
    cursor: pointer;
    border: 1px solid var(--border-hi);
    background: var(--surface);
    color: var(--text);
    transition: background 0.15s;
  }
  .modal-btn:hover { background: #1a1a1a; }
  .modal-btn.confirm { border-color: rgba(217,95,82,0.4); color: var(--red); }
  .modal-btn.confirm:hover { background: rgba(217,95,82,0.15); }

  /* ── Shortcuts overlay ── */
  .shortcuts-box {
    background: var(--surface);
    border: 1px solid var(--border-hi);
    padding: 32px;
    max-width: 380px;
    width: 100%;
  }
  .shortcuts-title {
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 20px;
  }
  .shortcuts-grid { display: flex; flex-direction: column; gap: 10px; }
  .shortcut { display: flex; align-items: center; gap: 16px; }
  .shortcut kbd {
    display: inline-block;
    min-width: 28px;
    text-align: center;
    padding: 2px 8px;
    font-family: var(--font);
    font-size: 11px;
    background: rgba(232,184,75,0.08);
    border: 1px solid var(--amber-dim);
    color: var(--amber);
  }
  .shortcut span { font-size: 12px; color: var(--muted); font-weight: 300; }

  /* ── Footer ── */
  footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 0 0;
    border-top: 1px solid var(--border);
    margin-top: 32px;
  }

  .footer-left {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 11px;
    color: var(--dim);
    font-weight: 300;
  }

  .footer-right {
    font-size: 11px;
    color: var(--dim);
    font-weight: 300;
  }

  .conn-badge {
    display: inline-block;
    font-size: 9px;
    padding: 1px 6px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .conn-badge.ws { background: rgba(76,186,110,0.1); color: var(--green); border: 1px solid rgba(76,186,110,0.25); }
  .conn-badge.poll { background: rgba(91,156,246,0.1); color: var(--blue); border: 1px solid rgba(91,156,246,0.25); }
  .conn-badge.error { background: rgba(217,95,82,0.1); color: var(--red); border: 1px solid rgba(217,95,82,0.25); }
</style>
</head>
<body>
<div class="shell">

  <header>
    <div class="logo">
      <span class="logo-name">CLAUDE SYMPHONY</span>
      <span class="logo-tag">Claude Code Orchestrator</span>
    </div>
    <div class="header-right">
      <div id="status-dot" class="status-dot idle"></div>
      <span id="ts" class="timestamp">&mdash;</span>
    </div>
  </header>

  <div class="metrics">
    <div class="metric" id="m-running">
      <div class="metric-label">Running</div>
      <div class="metric-value" id="v-running">&mdash;</div>
      <div class="metric-sub">active agents</div>
    </div>
    <div class="metric" id="m-gates">
      <div class="metric-label">Gates</div>
      <div class="metric-value" id="v-gates">&mdash;</div>
      <div class="metric-sub">awaiting review</div>
    </div>
    <div class="metric" id="m-tokens">
      <div class="metric-label">Tokens</div>
      <div class="metric-value" id="v-tokens">&mdash;</div>
      <div class="metric-sub" id="v-tokens-sub">total consumed</div>
    </div>
    <div class="metric" id="m-runtime">
      <div class="metric-label">Runtime</div>
      <div class="metric-value" id="v-runtime">&mdash;</div>
      <div class="metric-sub">cumulative seconds</div>
    </div>
  </div>

  <div class="section-header">
    <span class="section-title">Active Agents</span>
    <input type="text" id="search-input" class="search-input" placeholder="Search agents..." />
    <div class="section-line"></div>
    <span class="section-count" id="agent-count">0</span>
  </div>

  <div id="agents-container"></div>

  <div id="confirm-modal" class="modal-overlay" style="display:none">
    <div class="modal-box">
      <div class="modal-title">Stop agent?</div>
      <div class="modal-body" id="modal-msg">Stop this agent? The issue will remain in its current Linear state.</div>
      <div class="modal-actions">
        <button class="modal-btn cancel" onclick="Controls.closeModal()">Cancel</button>
        <button class="modal-btn confirm" id="modal-confirm">Stop</button>
      </div>
    </div>
  </div>

  <div id="shortcuts-overlay" class="modal-overlay" style="display:none">
    <div class="shortcuts-box">
      <div class="shortcuts-title">KEYBOARD SHORTCUTS</div>
      <div class="shortcuts-grid">
        <div class="shortcut"><kbd>j</kbd><span>Next agent</span></div>
        <div class="shortcut"><kbd>k</kbd><span>Previous agent</span></div>
        <div class="shortcut"><kbd>Enter</kbd><span>Expand / collapse</span></div>
        <div class="shortcut"><kbd>p</kbd><span>Pause / resume</span></div>
        <div class="shortcut"><kbd>s</kbd><span>Stop agent</span></div>
        <div class="shortcut"><kbd>Esc</kbd><span>Close panel</span></div>
        <div class="shortcut"><kbd>r</kbd><span>Force refresh</span></div>
        <div class="shortcut"><kbd>/</kbd><span>Focus search</span></div>
        <div class="shortcut"><kbd>?</kbd><span>This help</span></div>
      </div>
    </div>
  </div>

  <footer>
    <div class="footer-left">
      <span id="conn-badge" class="conn-badge poll">POLL</span>
      <span id="footer-sync">&mdash;</span>
    </div>
    <span class="footer-right" id="footer-gen">&mdash;</span>
  </footer>

</div>

<script>
(function() {
  'use strict';

  // ── Utilities ──
  function esc(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function fmt(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000)    return (n / 1000).toFixed(1) + 'K';
    return String(n);
  }

  function fmtSecs(s) {
    if (s < 60)   return Math.round(s) + 's';
    if (s < 3600) return Math.floor(s / 60) + 'm ' + Math.round(s % 60) + 's';
    return Math.floor(s / 3600) + 'h ' + Math.floor((s % 3600) / 60) + 'm';
  }

  function fmtTime(isoStr) {
    if (!isoStr) return '';
    try {
      var d = new Date(isoStr);
      return d.toLocaleTimeString('en-US', { hour12: false });
    } catch(e) { return ''; }
  }

  function statusOrder(s) {
    var order = { streaming: 0, paused: 1, gate: 2, retrying: 3, succeeded: 4, failed: 5, pending: 6 };
    return order[s] !== undefined ? order[s] : 7;
  }

  function updateConnBadge(type) {
    var badge = document.getElementById('conn-badge');
    if (!badge) return;
    badge.className = 'conn-badge ' + type;
    badge.textContent = type === 'ws' ? 'WS' : type === 'error' ? 'ERR' : 'POLL';
  }

  // ── State Module ──
  var State = (function() {
    var currentData = null;
    var ws = null;
    var pollInterval = null;
    var selectedIssueId = null;
    var selectedIndex = -1;
    var searchQuery = '';

    function connectWS() {
      var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      try {
        ws = new WebSocket(proto + '//' + location.host + '/ws');
        ws.onopen = function() { stopPolling(); updateConnBadge('ws'); };
        ws.onmessage = function(e) {
          var msg = JSON.parse(e.data);
          if (msg.type === 'snapshot') {
            currentData = msg.data;
            render();
          }
          if (msg.type === 'event' && msg.issue_id === selectedIssueId) {
            Detail.appendEvent(msg.event);
          }
        };
        ws.onclose = function() { ws = null; startPolling(); updateConnBadge('poll'); };
        ws.onerror = function() { if (ws) ws.close(); };
      } catch(e) {
        startPolling();
      }
    }

    function startPolling() {
      if (!pollInterval) pollInterval = setInterval(refresh, 3000);
    }

    function stopPolling() {
      if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
    }

    function refresh() {
      fetch('/api/v1/state')
        .then(function(res) { return res.json(); })
        .then(function(data) {
          currentData = data;
          render();
        })
        .catch(function() { updateConnBadge('error'); });
    }

    function subscribe(issueId) {
      if (ws && ws.readyState === 1) ws.send(JSON.stringify({ subscribe: issueId }));
    }

    function unsubscribe(issueId) {
      if (ws && ws.readyState === 1) ws.send(JSON.stringify({ unsubscribe: issueId }));
    }

    return {
      connectWS: connectWS,
      refresh: refresh,
      subscribe: subscribe,
      unsubscribe: unsubscribe,
      startPolling: startPolling,
      getData: function() { return currentData; },
      getSelectedIssueId: function() { return selectedIssueId; },
      setSelectedIssueId: function(v) { selectedIssueId = v; },
      getSelectedIndex: function() { return selectedIndex; },
      setSelectedIndex: function(v) { selectedIndex = v; },
      getSearchQuery: function() { return searchQuery; },
      setSearchQuery: function(v) { searchQuery = v; }
    };
  })();

  // ── Cards Module ──
  var Cards = (function() {
    function getAllAgents(data) {
      if (!data) return [];
      var all = [];

      (data.running || []).forEach(function(r) {
        all.push({
          issue_id: r.issue_id,
          issue_identifier: r.issue_identifier || '',
          issue_title: r.issue_title || '',
          issue_url: r.issue_url || '',
          issue_labels: r.issue_labels || [],
          session_id: r.session_id || null,
          turn_count: r.turn_count || 0,
          status: r.status || 'streaming',
          last_event: r.last_event || '',
          last_message: r.last_message || '',
          started_at: r.started_at || '',
          last_event_at: r.last_event_at || '',
          tokens: r.tokens || { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
          state_name: r.state_name || '',
          event_count: r.event_count || 0,
          pid: r.pid || null,
          workspace_path: r.workspace_path || '',
          _sort: 'running'
        });
      });

      (data.retrying || []).forEach(function(r) {
        all.push({
          issue_id: r.issue_id,
          issue_identifier: r.issue_identifier || '',
          issue_title: r.issue_title || '',
          issue_url: r.issue_url || '',
          issue_labels: [],
          session_id: null,
          turn_count: r.attempt || 0,
          status: 'retrying',
          last_event: '',
          last_message: r.error || 'waiting to retry...',
          started_at: '',
          last_event_at: '',
          tokens: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
          state_name: '',
          event_count: 0,
          pid: null,
          workspace_path: '',
          _sort: 'retrying'
        });
      });

      (data.gates || []).forEach(function(g) {
        all.push({
          issue_id: g.issue_id,
          issue_identifier: g.issue_identifier || '',
          issue_title: g.issue_title || '',
          issue_url: g.issue_url || '',
          issue_labels: [],
          session_id: null,
          turn_count: g.run || 0,
          status: 'gate',
          last_event: '',
          last_message: 'Awaiting human review',
          started_at: '',
          last_event_at: '',
          tokens: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
          state_name: g.gate_state || '',
          event_count: 0,
          pid: null,
          workspace_path: '',
          _sort: 'gate'
        });
      });

      // Apply search filter
      var q = State.getSearchQuery().toLowerCase();
      if (q) {
        all = all.filter(function(a) {
          return a.issue_identifier.toLowerCase().indexOf(q) !== -1 ||
                 a.issue_title.toLowerCase().indexOf(q) !== -1;
        });
      }

      // Sort by status priority
      all.sort(function(a, b) {
        return statusOrder(a.status) - statusOrder(b.status);
      });

      return all;
    }

    function buildControlsHTML(agent) {
      var s = agent.status;
      var id = agent.issue_id;
      var ident = esc(agent.issue_identifier);
      var html = '<div class="agent-controls">';
      if (s === 'streaming') {
        html += '<button class="agent-control pause" data-action="pause" data-id="' + esc(id) + '" title="Pause">&#9208;</button>';
        html += '<button class="agent-control stop" data-action="stop" data-id="' + esc(id) + '" data-ident="' + ident + '" title="Stop">&#9209;</button>';
      } else if (s === 'paused') {
        html += '<button class="agent-control pause" data-action="resume" data-id="' + esc(id) + '" title="Resume">&#9654;</button>';
        html += '<button class="agent-control stop" data-action="stop" data-id="' + esc(id) + '" data-ident="' + ident + '" title="Stop">&#9209;</button>';
      } else if (s === 'retrying') {
        html += '<button class="agent-control stop" data-action="stop" data-id="' + esc(id) + '" data-ident="' + ident + '" title="Stop">&#9209;</button>';
      }
      html += '</div>';
      return html;
    }

    function statusPillHTML(status) {
      var cls = ['streaming','succeeded','failed','retrying','pending','gate','paused'].indexOf(status) !== -1 ? status : 'pending';
      var label;
      if (status === 'streaming') label = 'live';
      else if (status === 'gate') label = 'awaiting gate';
      else if (status === 'paused') label = 'paused';
      else label = status;
      return '<span class="status-pill ' + cls + '">' + esc(label) + '</span>';
    }

    function updateCard(card, a, index) {
      card.setAttribute('data-status', a.status);
      card.setAttribute('data-index', String(index));

      var idEl = card.querySelector('.agent-id');
      if (idEl) idEl.textContent = a.issue_identifier;

      var titleEl = card.querySelector('.agent-title');
      if (titleEl) titleEl.textContent = a.issue_title;

      var statusRow = card.querySelector('.agent-status-row');
      if (statusRow) statusRow.innerHTML = statusPillHTML(a.status) + (a.state_name ? '<span class="agent-state">' + esc(a.state_name) + '</span>' : '');

      var msgEl = card.querySelector('.agent-msg');
      if (msgEl) msgEl.textContent = a.last_message || '\u2014';

      var ctrlEl = card.querySelector('.agent-controls');
      if (ctrlEl) ctrlEl.outerHTML = buildControlsHTML(a);

      var tokEl = card.querySelector('.agent-tokens');
      if (tokEl) tokEl.textContent = fmt(a.tokens.total_tokens || 0) + ' tok';

      var turnEl = card.querySelector('.agent-turns');
      if (turnEl) turnEl.textContent = 'turn ' + (a.turn_count || 0);
    }

    function buildCardHTML(a, index, selected) {
      var sel = selected ? ' selected' : '';
      var stateSpan = a.state_name ? '<span class="agent-state">' + esc(a.state_name) + '</span>' : '';
      return '<div class="agent-card' + sel + '" data-issue-id="' + esc(a.issue_id) + '" data-status="' + esc(a.status) + '" data-index="' + index + '">' +
        '<div class="agent-left">' +
          '<div class="agent-id">' + esc(a.issue_identifier) + '</div>' +
        '</div>' +
        '<div class="agent-center">' +
          '<div class="agent-title">' + esc(a.issue_title) + '</div>' +
          '<div class="agent-status-row">' +
            statusPillHTML(a.status) +
            stateSpan +
          '</div>' +
          '<div class="agent-msg">' + esc(a.last_message || '\u2014') + '</div>' +
        '</div>' +
        '<div class="agent-meta">' +
          buildControlsHTML(a) +
          '<div class="agent-tokens">' + fmt(a.tokens.total_tokens || 0) + ' tok</div>' +
          '<div class="agent-turns">turn ' + (a.turn_count || 0) + '</div>' +
        '</div>' +
      '</div>' +
      '<div class="detail-panel" data-issue-id="' + esc(a.issue_id) + '" style="display:none"></div>';
    }

    function renderAll(data) {
      var agents = getAllAgents(data);
      var container = document.getElementById('agents-container');
      document.getElementById('agent-count').textContent = agents.length;

      if (agents.length === 0) {
        container.innerHTML =
          '<div class="empty">' +
            '<div class="empty-title">No active agents</div>' +
            '<div class="empty-sub">Move a Linear issue to Todo or In Progress to start</div>' +
          '</div>';
        return;
      }

      var selectedId = State.getSelectedIssueId();
      var wrapper = container.querySelector('.agents');

      // First render: build everything from scratch
      if (!wrapper) {
        var rows = '';
        for (var i = 0; i < agents.length; i++) {
          rows += buildCardHTML(agents[i], i, agents[i].issue_id === selectedId);
        }
        container.innerHTML = '<div class="agents">' + rows + '</div>';
        if (selectedId) {
          var panel = container.querySelector('.detail-panel[data-issue-id="' + selectedId + '"]');
          if (panel && Detail.getLastHTML()) {
            panel.innerHTML = Detail.getLastHTML();
            panel.style.display = 'block';
          }
        }
        return;
      }

      // Incremental update: patch existing cards in-place
      var existingCards = wrapper.querySelectorAll('.agent-card');
      var existingMap = {};
      for (var j = 0; j < existingCards.length; j++) {
        var eid = existingCards[j].getAttribute('data-issue-id');
        existingMap[eid] = existingCards[j];
      }

      var newIds = {};
      for (var k = 0; k < agents.length; k++) {
        newIds[agents[k].issue_id] = true;
      }

      // Remove cards no longer present (card + its detail-panel sibling)
      for (var eid2 in existingMap) {
        if (!newIds[eid2]) {
          var cardToRemove = existingMap[eid2];
          var panelSibling = cardToRemove.nextElementSibling;
          if (panelSibling && panelSibling.classList.contains('detail-panel')) {
            wrapper.removeChild(panelSibling);
          }
          wrapper.removeChild(cardToRemove);
        }
      }

      // Update existing or insert new cards
      for (var m = 0; m < agents.length; m++) {
        var a = agents[m];
        var card = existingMap[a.issue_id];
        if (card) {
          // Update in-place — no innerHTML replacement, preserves dropdown state
          updateCard(card, a, m);
        } else {
          // New agent — append
          var tmp = document.createElement('div');
          tmp.innerHTML = buildCardHTML(a, m, a.issue_id === selectedId);
          while (tmp.firstChild) {
            wrapper.appendChild(tmp.firstChild);
          }
        }
      }
    }

    return { renderAll: renderAll, getAllAgents: getAllAgents };
  })();

  // ── Detail Module ──
  var Detail = (function() {
    var lastHTML = '';
    var lastIssueId = null;

    function getLastHTML() { return lastHTML; }

    function buildContextHTML(agent) {
      var html = '<div class="detail-context">';
      if (agent.issue_url) {
        html += '<div class="ctx-item"><a href="' + esc(agent.issue_url) + '" target="_blank" rel="noopener">' + esc(agent.issue_identifier) + ' on Linear</a></div>';
      }
      if (agent.issue_labels && agent.issue_labels.length > 0) {
        html += '<div class="ctx-item">Labels:';
        agent.issue_labels.forEach(function(l) {
          html += '<span class="ctx-label-pill">' + esc(l) + '</span>';
        });
        html += '</div>';
      }
      if (agent.state_name) {
        html += '<div class="ctx-item">State: ' + esc(agent.state_name);
        if (agent.turn_count) html += ' &middot; run ' + agent.turn_count;
        html += '</div>';
      }
      if (agent.session_id) {
        html += '<div class="ctx-item">Session: ' + esc(agent.session_id.substring(0, 12)) + '&hellip;</div>';
      }
      if (agent.workspace_path) {
        html += '<div class="ctx-item">Workspace: ' + esc(agent.workspace_path) + '</div>';
      }
      html += '</div>';
      return html;
    }

    function buildLogEntryHTML(evt) {
      var ts = fmtTime(evt.timestamp);
      var evtType = evt.event_type || 'thinking';
      var badgeCls = evtType;
      var msg = evt.summary || evt.detail || '';
      if (evt.tool_name) msg = evt.tool_name + ': ' + msg;
      return '<div class="log-entry">' +
        '<span class="log-ts">' + esc(ts) + '</span>' +
        '<span class="log-badge ' + esc(badgeCls) + '">' + esc(evtType) + '</span>' +
        '<span class="log-msg">' + esc(msg) + '</span>' +
      '</div>';
    }

    function expand(issueId) {
      // Collapse current if same
      if (lastIssueId === issueId) {
        collapse();
        return;
      }

      // Collapse previous
      collapse();

      lastIssueId = issueId;
      State.setSelectedIssueId(issueId);

      // Find agent data
      var data = State.getData();
      var agents = Cards.getAllAgents(data);
      var agent = null;
      for (var i = 0; i < agents.length; i++) {
        if (agents[i].issue_id === issueId) { agent = agents[i]; break; }
      }
      if (!agent) return;

      // Mark card as selected
      var cards = document.querySelectorAll('.agent-card');
      cards.forEach(function(c) { c.classList.remove('selected'); });
      var card = document.querySelector('.agent-card[data-issue-id="' + issueId + '"]');
      if (card) card.classList.add('selected');

      // Build panel skeleton
      var panel = document.querySelector('.detail-panel[data-issue-id="' + issueId + '"]');
      if (!panel) return;

      var html =
        '<div class="detail-header">' +
          '<span class="detail-label">ACTIVITY LOG</span>' +
          '<div class="detail-line"></div>' +
          '<button class="detail-close" data-action="close-detail">&times;</button>' +
        '</div>' +
        buildContextHTML(agent) +
        '<div class="detail-log" id="detail-log-' + esc(issueId) + '">' +
          '<div class="log-entry"><span class="log-ts"></span><span class="log-badge thinking">LOADING</span><span class="log-msg">Fetching events...</span></div>' +
        '</div>';

      panel.innerHTML = html;
      panel.style.display = 'block';
      lastHTML = html;

      // Subscribe to WS events
      State.subscribe(issueId);

      // Fetch events
      fetch('/api/v1/events/' + encodeURIComponent(issueId) + '?limit=50')
        .then(function(res) { return res.json(); })
        .then(function(events) {
          var logEl = document.getElementById('detail-log-' + issueId);
          if (!logEl) return;
          if (!events || events.length === 0) {
            logEl.innerHTML = '<div class="log-entry"><span class="log-ts"></span><span class="log-badge thinking">INFO</span><span class="log-msg">No events yet</span></div>';
          } else {
            var logHTML = '';
            events.forEach(function(evt) {
              logHTML += buildLogEntryHTML(evt);
            });
            logEl.innerHTML = logHTML;
            logEl.scrollTop = logEl.scrollHeight;
          }
          lastHTML = panel.innerHTML;
        })
        .catch(function() {
          var logEl = document.getElementById('detail-log-' + issueId);
          if (logEl) logEl.innerHTML = '<div class="log-entry"><span class="log-ts"></span><span class="log-badge error">ERROR</span><span class="log-msg">Failed to fetch events</span></div>';
        });
    }

    function collapse() {
      if (lastIssueId) {
        State.unsubscribe(lastIssueId);
        var panel = document.querySelector('.detail-panel[data-issue-id="' + lastIssueId + '"]');
        if (panel) { panel.style.display = 'none'; panel.innerHTML = ''; }
      }
      var cards = document.querySelectorAll('.agent-card');
      cards.forEach(function(c) { c.classList.remove('selected'); });
      lastIssueId = null;
      lastHTML = '';
      State.setSelectedIssueId(null);
    }

    function appendEvent(event) {
      if (!lastIssueId) return;
      var logEl = document.getElementById('detail-log-' + lastIssueId);
      if (!logEl) return;
      logEl.insertAdjacentHTML('beforeend', buildLogEntryHTML(event));
      logEl.scrollTop = logEl.scrollHeight;
      lastHTML = logEl.parentElement.innerHTML;
    }

    return { expand: expand, collapse: collapse, appendEvent: appendEvent, getLastHTML: getLastHTML };
  })();

  // ── Controls Module ──
  var Controls = (function() {
    var pendingStopId = null;

    function pauseAgent(issueId) {
      fetch('/api/v1/' + encodeURIComponent(issueId) + '/pause', { method: 'POST' })
        .then(function() { State.refresh(); });
    }

    function resumeAgent(issueId) {
      fetch('/api/v1/' + encodeURIComponent(issueId) + '/resume', { method: 'POST' })
        .then(function() { State.refresh(); });
    }

    function requestStop(issueId, identifier) {
      pendingStopId = issueId;
      var modal = document.getElementById('confirm-modal');
      var msg = document.getElementById('modal-msg');
      msg.textContent = 'Stop agent for ' + (identifier || issueId) + '? The issue will remain in its current Linear state.';
      modal.style.display = 'flex';
      document.getElementById('modal-confirm').onclick = function() {
        confirmStop();
      };
    }

    function confirmStop() {
      if (!pendingStopId) return;
      fetch('/api/v1/' + encodeURIComponent(pendingStopId) + '/stop', { method: 'POST' })
        .then(function() { closeModal(); State.refresh(); });
    }

    function closeModal() {
      pendingStopId = null;
      document.getElementById('confirm-modal').style.display = 'none';
    }

    return {
      pauseAgent: pauseAgent,
      resumeAgent: resumeAgent,
      requestStop: requestStop,
      confirmStop: confirmStop,
      closeModal: closeModal
    };
  })();

  // Make Controls available globally for inline onclick
  window.Controls = Controls;

  // ── Keyboard Module ──
  var Keyboard = (function() {
    function init() {
      document.addEventListener('keydown', function(e) {
        // Don't handle when typing in search
        if (e.target.tagName === 'INPUT') {
          if (e.key === 'Escape') { e.target.blur(); e.target.value = ''; State.setSearchQuery(''); render(); }
          return;
        }
        // Don't handle with modifier keys (except shift for ?)
        if (e.ctrlKey || e.altKey || e.metaKey) return;

        switch(e.key) {
          case 'j': moveSelection(1); break;
          case 'k': moveSelection(-1); break;
          case 'Enter':
          case ' ':
            toggleExpand();
            e.preventDefault();
            break;
          case 'p': togglePause(); break;
          case 's': requestStopSelected(); break;
          case 'Escape': handleEscape(); break;
          case 'r': State.refresh(); break;
          case '?': toggleShortcuts(); break;
          case '/': focusSearch(); e.preventDefault(); break;
        }
      });
    }

    function moveSelection(dir) {
      var data = State.getData();
      if (!data) return;
      var agents = Cards.getAllAgents(data);
      if (agents.length === 0) return;
      var idx = State.getSelectedIndex();
      idx += dir;
      if (idx < 0) idx = 0;
      if (idx >= agents.length) idx = agents.length - 1;
      State.setSelectedIndex(idx);
      var agent = agents[idx];
      // Highlight card
      var cards = document.querySelectorAll('.agent-card');
      cards.forEach(function(c) { c.classList.remove('selected'); });
      var card = document.querySelector('.agent-card[data-index="' + idx + '"]');
      if (card) {
        card.classList.add('selected');
        card.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }

    function toggleExpand() {
      var idx = State.getSelectedIndex();
      var data = State.getData();
      if (!data || idx < 0) return;
      var agents = Cards.getAllAgents(data);
      if (idx >= agents.length) return;
      Detail.expand(agents[idx].issue_id);
    }

    function togglePause() {
      var idx = State.getSelectedIndex();
      var data = State.getData();
      if (!data || idx < 0) return;
      var agents = Cards.getAllAgents(data);
      if (idx >= agents.length) return;
      var agent = agents[idx];
      if (agent.status === 'streaming') Controls.pauseAgent(agent.issue_id);
      else if (agent.status === 'paused') Controls.resumeAgent(agent.issue_id);
    }

    function requestStopSelected() {
      var idx = State.getSelectedIndex();
      var data = State.getData();
      if (!data || idx < 0) return;
      var agents = Cards.getAllAgents(data);
      if (idx >= agents.length) return;
      var agent = agents[idx];
      if (agent.status === 'streaming' || agent.status === 'paused' || agent.status === 'retrying') {
        Controls.requestStop(agent.issue_id, agent.issue_identifier);
      }
    }

    function handleEscape() {
      // Close shortcuts overlay first
      var shortcuts = document.getElementById('shortcuts-overlay');
      if (shortcuts.style.display !== 'none') {
        shortcuts.style.display = 'none';
        return;
      }
      // Close modal
      var modal = document.getElementById('confirm-modal');
      if (modal.style.display !== 'none') {
        Controls.closeModal();
        return;
      }
      // Collapse detail
      Detail.collapse();
      State.setSelectedIndex(-1);
    }

    function toggleShortcuts() {
      var overlay = document.getElementById('shortcuts-overlay');
      overlay.style.display = overlay.style.display === 'none' ? 'flex' : 'none';
    }

    function focusSearch() {
      var input = document.getElementById('search-input');
      if (input) input.focus();
    }

    return { init: init };
  })();

  // ── Notify Module ──
  var Notify = (function() {
    var permission = false;
    var knownGates = {};

    function init() {
      if ('Notification' in window) {
        Notification.requestPermission().then(function(p) {
          permission = (p === 'granted');
        });
      }
    }

    function checkGates(data) {
      if (!permission || document.hasFocus()) return;
      var gates = data.gates || [];
      for (var i = 0; i < gates.length; i++) {
        var g = gates[i];
        if (!knownGates[g.issue_id]) {
          knownGates[g.issue_id] = true;
          new Notification(g.issue_identifier + ' awaiting review', {
            body: 'Gate: ' + (g.gate_state || 'review')
          });
        }
      }
    }

    return { init: init, checkGates: checkGates };
  })();

  // ── Render ──
  function render() {
    var data = State.getData();
    if (!data) return;

    var running  = (data.counts && data.counts.running)  || 0;
    var gates    = (data.counts && data.counts.gates)     || 0;
    var active   = running > 0;

    // Metrics
    document.getElementById('v-running').textContent = running;
    document.getElementById('v-gates').textContent   = gates;
    document.getElementById('v-tokens').textContent  = fmt((data.totals && data.totals.total_tokens) || 0);
    document.getElementById('v-runtime').textContent = fmtSecs((data.totals && data.totals.seconds_running) || 0);

    // Token sub with breakdown
    var inTok  = (data.totals && data.totals.input_tokens)  || 0;
    var outTok = (data.totals && data.totals.output_tokens) || 0;
    document.getElementById('v-tokens-sub').textContent = fmt(inTok) + ' in / ' + fmt(outTok) + ' out';

    // Active states for metrics
    document.getElementById('m-running').className = 'metric' + (active ? ' active' : '');
    document.getElementById('m-gates').className   = 'metric' + (gates > 0 ? ' active' : '');
    document.getElementById('m-tokens').className  = 'metric' + (((data.totals && data.totals.total_tokens) || 0) > 0 ? ' active' : '');

    // Status dot
    var dot = document.getElementById('status-dot');
    dot.className = 'status-dot' + (active ? '' : ' idle');

    // Timestamp
    var now = new Date();
    var timeStr = now.toLocaleTimeString('en-US', { hour12: false });
    document.getElementById('ts').textContent = timeStr + ' local';
    document.getElementById('footer-sync').textContent = 'last sync ' + timeStr;
    document.getElementById('footer-gen').textContent = data.generated_at || '';

    // Render agents
    Cards.renderAll(data);

    // Check for gate notifications
    Notify.checkGates(data);
  }

  // ── Event Delegation ──
  document.getElementById('agents-container').addEventListener('click', function(e) {
    // Handle control buttons
    var btn = e.target.closest('[data-action]');
    if (btn) {
      e.stopPropagation();
      var action = btn.getAttribute('data-action');
      var id = btn.getAttribute('data-id');
      var ident = btn.getAttribute('data-ident');
      if (action === 'pause') Controls.pauseAgent(id);
      else if (action === 'resume') Controls.resumeAgent(id);
      else if (action === 'stop') Controls.requestStop(id, ident);
      else if (action === 'close-detail') Detail.collapse();
      return;
    }

    // Handle detail close button
    var closeBtn = e.target.closest('.detail-close');
    if (closeBtn) {
      e.stopPropagation();
      Detail.collapse();
      return;
    }

    // Handle log message expand/collapse
    var logMsg = e.target.closest('.log-msg');
    if (logMsg) {
      logMsg.classList.toggle('expanded');
      return;
    }

    // Handle card click -> expand/collapse detail
    var card = e.target.closest('.agent-card');
    if (card) {
      var issueId = card.getAttribute('data-issue-id');
      var idx = parseInt(card.getAttribute('data-index'), 10);
      State.setSelectedIndex(idx);
      Detail.expand(issueId);
    }
  });

  // Search input
  document.getElementById('search-input').addEventListener('input', function(e) {
    State.setSearchQuery(e.target.value);
    render();
  });

  // Close modals on overlay click
  document.getElementById('confirm-modal').addEventListener('click', function(e) {
    if (e.target === this) Controls.closeModal();
  });
  document.getElementById('shortcuts-overlay').addEventListener('click', function(e) {
    if (e.target === this) this.style.display = 'none';
  });

  // ── Init ──
  Keyboard.init();
  Notify.init();
  State.connectWS();
  // Fallback polling starts automatically if WS fails
  State.startPolling();
  State.refresh();
})();
</script>
</body>
</html>
"""

def create_app(orchestrator: "Orchestrator") -> FastAPI:
    from contextlib import asynccontextmanager

    # WebSocket client management (scoped to this app instance)
    ws_clients: set[WebSocket] = set()
    ws_subscriptions: dict[WebSocket, str | None] = {}
    last_broadcast = {"t": 0.0}

    async def broadcast_snapshot() -> None:
        """Broadcast state snapshot to all connected WebSocket clients."""
        now = time.monotonic()
        if now - last_broadcast["t"] < 0.5:  # Max 2 updates/sec
            return
        last_broadcast["t"] = now
        snapshot = orchestrator.get_state_snapshot()
        msg = json.dumps({"type": "snapshot", "data": snapshot})
        dead: set[WebSocket] = set()
        for client in list(ws_clients):
            try:
                await client.send_text(msg)
            except Exception:
                dead.add(client)
        for d in dead:
            ws_clients.discard(d)
            ws_subscriptions.pop(d, None)

    async def _broadcast_loop() -> None:
        """Background task that periodically broadcasts state to WS clients."""
        while True:
            await asyncio.sleep(1.5)
            if ws_clients:
                try:
                    await broadcast_snapshot()
                except Exception:
                    pass

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # noqa: ARG001
        task = asyncio.create_task(_broadcast_loop())
        yield
        task.cancel()

    app = FastAPI(title="Claude Symphony", version="0.2.0", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    async def dashboard() -> HTMLResponse:
        return HTMLResponse(DASHBOARD_HTML)

    @app.get("/api/v1/state")
    async def api_state() -> JSONResponse:
        return JSONResponse(orchestrator.get_state_snapshot())

    @app.get("/api/v1/events/{issue_id}")
    async def api_events(issue_id: str, limit: int = 50) -> JSONResponse:
        events = orchestrator.get_events(issue_id, limit=limit)
        return JSONResponse(events)

    @app.get("/api/v1/{issue_identifier}")
    async def api_issue(issue_identifier: str) -> JSONResponse:
        snap = orchestrator.get_state_snapshot()
        for r in snap["running"]:
            if r["issue_identifier"] == issue_identifier:
                return JSONResponse(r)
        for r in snap["retrying"]:
            if r.get("issue_identifier") == issue_identifier:
                return JSONResponse(r)
        for g in snap.get("gates", []):
            if g.get("issue_identifier") == issue_identifier:
                return JSONResponse(g)
        err = {
            "error": {
                "code": "issue_not_found",
                "message": f"Unknown: {issue_identifier}",
            }
        }
        return JSONResponse(err, status_code=404)

    @app.post("/api/v1/{issue_id}/pause")
    async def api_pause(issue_id: str) -> JSONResponse:
        result = await orchestrator.pause_agent(issue_id)
        return JSONResponse({"ok": result})

    @app.post("/api/v1/{issue_id}/resume")
    async def api_resume(issue_id: str) -> JSONResponse:
        result = await orchestrator.resume_agent(issue_id)
        return JSONResponse({"ok": result})

    @app.post("/api/v1/{issue_id}/stop")
    async def api_stop(issue_id: str) -> JSONResponse:
        result = await orchestrator.stop_agent(issue_id)
        return JSONResponse({"ok": result})

    @app.post("/api/v1/refresh")
    async def api_refresh() -> JSONResponse:
        asyncio.create_task(orchestrator._tick())
        return JSONResponse({"ok": True})

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        ws_clients.add(websocket)
        # Send initial snapshot
        try:
            snapshot = orchestrator.get_state_snapshot()
            await websocket.send_json({"type": "snapshot", "data": snapshot})
        except Exception:
            ws_clients.discard(websocket)
            return
        try:
            while True:
                data = await websocket.receive_json()
                if data.get("subscribe"):
                    ws_subscriptions[websocket] = data["subscribe"]
                elif data.get("unsubscribe"):
                    ws_subscriptions.pop(websocket, None)
        except WebSocketDisconnect:
            ws_clients.discard(websocket)
            ws_subscriptions.pop(websocket, None)
        except Exception:
            ws_clients.discard(websocket)
            ws_subscriptions.pop(websocket, None)

    return app
