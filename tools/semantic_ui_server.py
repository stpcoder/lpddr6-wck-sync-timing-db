#!/usr/bin/env python3
"""Dependency-free browser UI for the LPDDR6 semantic timing DB."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from semantic_query import SemanticDB, USER_METRICS, run_sweep


ROOT = Path(__file__).resolve().parents[1]
DB = SemanticDB()


def parse_list(params: dict[str, list[str]], key: str, default: str) -> list[str]:
    text = params.get(key, [default])[0]
    return [item.strip() for item in text.split(",") if item.strip()]


def parse_int_list(params: dict[str, list[str]], key: str, default: str) -> list[int]:
    return [int(item) for item in parse_list(params, key, default)]


def parse_float_list(params: dict[str, list[str]], key: str, default: str) -> list[float]:
    return [float(item) for item in parse_list(params, key, default)]


def public_rows(rows: list[dict]) -> list[dict]:
    return [{k: v for k, v in row.items() if not k.startswith("_")} for row in rows]


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>LPDDR6 Timing Semantic DB</title>
  <style>
    :root {
      --bg: #f6f7f9;
      --panel: #ffffff;
      --line: #d8dde5;
      --text: #111827;
      --muted: #5b6472;
      --accent: #2563eb;
      --accent-soft: #dbeafe;
      --warn: #b45309;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 13px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      height: 52px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 18px;
      border-bottom: 1px solid var(--line);
      background: #fff;
    }
    header h1 { margin: 0; font-size: 17px; font-weight: 650; letter-spacing: 0; }
    header .status { color: var(--muted); font-size: 12px; }
    main {
      display: grid;
      grid-template-columns: 380px 1fr;
      gap: 12px;
      padding: 12px;
      height: calc(100vh - 52px);
    }
    aside, section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }
    aside { display: flex; flex-direction: column; min-height: 0; }
    .panel-title {
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      font-weight: 650;
      background: #fbfcfe;
    }
    .controls { padding: 12px; display: grid; gap: 10px; overflow: auto; }
    label { display: grid; gap: 4px; color: var(--muted); font-size: 12px; }
    .label-title {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      min-width: 0;
    }
    .info {
      position: relative;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 15px;
      height: 15px;
      border-radius: 50%;
      background: #eef2f7;
      border: 1px solid #cbd5e1;
      color: #475569;
      font-size: 10px;
      font-weight: 700;
      line-height: 1;
      cursor: help;
      flex: 0 0 auto;
    }
    .tip {
      display: none;
      position: absolute;
      left: 0;
      top: 20px;
      z-index: 20;
      width: 260px;
      padding: 8px 9px;
      border: 1px solid #cbd5e1;
      border-radius: 7px;
      background: #111827;
      color: #fff;
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.18);
      font-size: 12px;
      font-weight: 400;
      line-height: 1.45;
      white-space: normal;
    }
    .info:hover .tip,
    .info:focus .tip { display: block; }
    input, select, button {
      width: 100%;
      min-height: 32px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 6px 8px;
      background: #fff;
      color: var(--text);
      font: inherit;
    }
    button {
      cursor: pointer;
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
      font-weight: 650;
    }
    button.secondary {
      background: #fff;
      color: var(--text);
      border-color: var(--line);
    }
    .content {
      display: grid;
      grid-template-rows: 300px minmax(0, 1fr);
      gap: 12px;
      min-width: 0;
    }
    .top {
      display: grid;
      grid-template-columns: 1fr;
      gap: 12px;
      min-width: 0;
    }
    .bottom {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      min-width: 0;
      min-height: 0;
    }
    .card-body { padding: 10px 12px; overflow: auto; height: calc(100% - 40px); }
    .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
    .divider { width:100%; border:0; border-top:1px solid var(--line); margin: 4px 0; }
    table { width: 100%; border-collapse: collapse; white-space: nowrap; font-size: 12px; }
    th, td { border-bottom: 1px solid #eef1f5; padding: 6px 8px; text-align: left; }
    th { position: sticky; top: 0; background: #f8fafc; z-index: 1; font-weight: 650; }
    tr:hover td { background: #f9fbff; }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 3px 7px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: #1d4ed8;
      font-weight: 650;
      font-size: 12px;
    }
    .muted { color: var(--muted); }
    .warn { color: var(--warn); font-weight: 650; }
    .subhead {
      margin: 12px 0 6px;
      font-weight: 650;
    }
    .formula {
      margin: 8px 0;
      padding: 8px;
      background: #f8fafc;
      border: 1px solid #edf0f5;
      border-radius: 6px;
      white-space: pre-wrap;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
    }
    .hint {
      padding: 8px;
      border: 1px solid #edf0f5;
      border-radius: 6px;
      background: #fbfcfe;
      color: var(--muted);
      font-size: 12px;
    }
    .chips {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin: 8px 0;
    }
    .chip {
      padding: 3px 7px;
      border: 1px solid #dbe3ef;
      border-radius: 999px;
      background: #fff;
      font-size: 12px;
      color: #334155;
    }
    .edges { display: grid; gap: 6px; }
    .edge {
      display: grid;
      grid-template-columns: minmax(100px, 1fr) 22px minmax(100px, 1fr) minmax(90px, .8fr);
      gap: 8px;
      align-items: center;
      padding: 6px 8px;
      border: 1px solid #edf0f5;
      border-radius: 6px;
      background: #fbfcfe;
    }
    .edge span { overflow: hidden; text-overflow: ellipsis; }
    .tree {
      display: grid;
      gap: 8px;
      margin-top: 8px;
    }
    .tree-node {
      display: grid;
      gap: 6px;
    }
    .tree-card {
      display: grid;
      grid-template-columns: minmax(120px, auto) 1fr;
      gap: 8px;
      align-items: start;
      padding: 7px 9px;
      border: 1px solid #dbe3ef;
      border-radius: 7px;
      background: #fff;
    }
    .tree-card.root {
      border-color: #93c5fd;
      background: #eff6ff;
    }
    .tree-symbol {
      font-weight: 700;
      color: #0f172a;
      overflow-wrap: anywhere;
    }
    .tree-desc {
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .tree-reason {
      grid-column: 1 / -1;
      color: #334155;
      font-size: 12px;
      padding-top: 2px;
    }
    .tree-children {
      margin-left: 18px;
      padding-left: 12px;
      border-left: 2px solid #e2e8f0;
      display: grid;
      gap: 7px;
    }
    .tree-empty {
      color: var(--muted);
      font-size: 12px;
      padding: 5px 0 0 2px;
    }
    .tabs {
      display: flex;
      gap: 6px;
      padding: 8px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfe;
    }
    .tabs button {
      width: auto;
      min-height: 28px;
      padding: 4px 10px;
      background: #fff;
      color: var(--text);
      border-color: var(--line);
    }
    .tabs button.active { background: var(--accent); color: #fff; border-color: var(--accent); }
    .hidden { display: none; }
  </style>
</head>
<body>
  <header>
    <h1>LPDDR6 Timing Semantic DB</h1>
    <div class="status" id="status">ready</div>
  </header>
  <main>
    <aside>
      <div class="panel-title">WCK Sync-Off Timing 계산</div>
      <div class="controls">
        <div class="grid2">
          <label><span class="label-title">Current CMD <span class="info" tabindex="0">i<span class="tip">먼저 수행된 command입니다. 예: WR 다음 RD가 들어오는 조건이면 Current CMD는 WR입니다.</span></span></span>
            <select id="currentCmd">
              <option>WR</option><option>RD</option><option>MRR</option><option>WFF</option><option>RFF</option><option>RDC</option><option>META_WR</option><option>META_RD</option>
            </select>
          </label>
          <label><span class="label-title">Next CMD <span class="info" tabindex="0">i<span class="tip">Current CMD 이후에 넣고 싶은 command입니다. 이 pair 기준으로 필요한 최소 간격을 계산합니다.</span></span></span>
            <select id="nextCmd">
              <option>RD</option><option>WR</option><option>MRR</option><option>WFF</option><option>RFF</option><option>RDC</option><option>META_WR</option><option>META_RD</option>
            </select>
          </label>
        </div>
        <label><span class="label-title">Bank Relation <span class="info" tabindex="0">i<span class="tip">두 command가 같은 BG인지, 다른 BG인지, 같은 bank인지에 따라 tWTR_S/L, tRTW, BL/n 적용 경로가 달라집니다.</span></span></span>
          <select id="bankRelation">
            <option value="different_bank_different_bg">Different bank / Different BG</option>
            <option value="different_bank_same_bg">Different bank / Same BG</option>
            <option value="same_bank_same_bg">Same bank / Same BG</option>
          </select>
        </label>
        <div class="grid2">
          <label><span class="label-title">Burst <span class="info" tabindex="0">i<span class="tip">BL24/BL48 조건입니다. BL/n_min, BL/n_max 및 command gap 계산에 영향을 줍니다.</span></span></span>
            <select id="burstLength"><option>BL24</option><option>BL48</option></select>
          </label>
          <label><span class="label-title">CMD 간격 입력 (nCK) <span class="info" tabindex="0">i<span class="tip">실제로 넣는다고 가정할 command 간격입니다. 결과표의 min_nck보다 작으면 too-early로 판정됩니다.</span></span></span><input id="gap" type="number" value="24" min="0" max="300" /></label>
        </div>
        <div class="grid2">
          <label><span class="label-title">WS Operand <span class="info" tabindex="0">i<span class="tip">WS bit/operand 조건입니다. WCK sync-off 관련 command operand 조건을 확인할 때 사용합니다.</span></span></span>
            <select id="ws"><option value="1">WS=H / 1</option><option value="0">WS=L / 0</option></select>
          </label>
        </div>
        <input id="maxRows" type="hidden" value="500" />
        <hr class="divider" />
        <label><span class="label-title">MR1.OP[4:0] 값 <span class="info" tabindex="0">i<span class="tip">JEDEC MR1의 speed bin field입니다. 기본 모드에서는 이 값으로 data rate와 tCK를 자동 선택합니다. 여러 값 비교는 쉼표로 입력합니다.</span></span></span><input id="mr1" value="00001" /></label>
        <div class="grid2">
          <label><span class="label-title">Data Rate 결정 방식 <span class="info" tabindex="0">i<span class="tip">일반 계산은 MR1.OP[4:0] 기준을 사용합니다. 직접 입력은 table 검증이나 임시 분석용입니다.</span></span></span>
            <select id="matchSpeed"><option value="1">MR1.OP[4:0] 기준</option><option value="0">직접 입력</option></select>
          </label>
          <label><span class="label-title">Data Rate 직접 입력 (Mbps) <span class="info" tabindex="0">i<span class="tip">Data Rate 결정 방식을 직접 입력으로 바꾼 경우에만 사용합니다. MR1 기준 모드에서는 무시됩니다.</span></span></span><input id="dataRate" value="9600" /></label>
        </div>
        <div class="grid2">
          <label><span class="label-title">MR1.OP[5] WLS 값 <span class="info" tabindex="0">i<span class="tip">Write Latency Set 선택 bit입니다. WL lookup table 선택에 영향을 줍니다.</span></span></span><input id="wlSetB" value="0" /></label>
          <label><span class="label-title">MR1.OP[6] DEFF 값 <span class="info" tabindex="0">i<span class="tip">Dynamic Efficiency Mode control입니다. latency table 및 일부 AC parameter selector에 영향을 줄 수 있습니다.</span></span></span><input id="efficiency" value="0,1" /></label>
        </div>
        <div class="grid3">
          <label><span class="label-title">MR11.OP[4] DVFSL 값 <span class="info" tabindex="0">i<span class="tip">DVFSL enable 조건입니다. selected latency table과 tRTW/tWTR 관련 조건에 영향을 줍니다.</span></span></span><input id="dvfsl" value="0,1" /></label>
          <label><span class="label-title">MR23.OP[0] Write Link 값 <span class="info" tabindex="0">i<span class="tip">Write Link Protection enable 조건입니다. latency table selector 및 write 관련 timing path에 영향을 줍니다.</span></span></span><input id="writeLink" value="0,1" /></label>
          <label><span class="label-title">MR23.OP[2] Read Link 값 <span class="info" tabindex="0">i<span class="tip">Read Link Protection enable 조건입니다. read latency table selector에 영향을 줍니다.</span></span></span><input id="readLink" value="0" /></label>
        </div>
        <label><span class="label-title">Timing Metrics <span class="info" tabindex="0">i<span class="tip">결과표에 표시할 값입니다. 예: RL, WL, tWTR_S, tWTR_L, tRTW, WR-&gt;RD min.</span></span></span><input id="outputs" value="RL,WL,tCK_ns,tWTR_S,tWTR_L,WR->RD min (diff BG),tRTW" /></label>
        <button onclick="runSweep()">조건 조합 표 만들기</button>
        <hr class="divider" />
        <label><span class="label-title">Symbol Search <span class="info" tabindex="0">i<span class="tip">계산 결과값의 근거를 추적할 때 사용합니다. 예: RL을 검색하면 MR/조건에서 RL까지의 구성 경로를 보여줍니다.</span></span></span><input id="symbolSearch" value="RL" /></label>
        <button class="secondary" onclick="loadSymbols()">심볼 찾기</button>
        <label><span class="label-title">Selected Symbol <span class="info" tabindex="0">i<span class="tip">구성 graph를 보고 싶은 symbol입니다. 계산표 실행과는 독립입니다.</span></span></span><select id="symbolSelect"></select></label>
        <button class="secondary" onclick="loadDetail()">선택 Symbol 구성 보기</button>
      </div>
    </aside>
    <div class="content">
      <div class="top">
        <section>
          <div class="panel-title">선택 Symbol 구성</div>
          <div class="card-body" id="detail"></div>
        </section>
      </div>
      <section class="bottom">
        <div class="panel-title"><span class="label-title">계산 결과표 <span class="info" tabindex="0">i<span class="tip">선택한 CMD pair와 MR/조건 조합별로 필요한 최소 CMD 간격과 주요 timing 계산값을 보여줍니다.</span></span></span></div>
        <div class="card-body" id="viewSweep"></div>
      </section>
    </div>
  </main>
<script>
const qs = (id) => document.getElementById(id);
const status = (text) => { qs("status").textContent = text; };
const SEEDED_MR1_OPS = new Set(['00000','00001','00010','00011','00100','00101','00110','00111','01000','01001','01010','01011','01100','01101']);
const TBD_MR1_OPS = new Set(['01110','01111','10000']);
const DVFSL_NUMERIC_MR1_OPS = new Set(['00000','00001']);

function table(rows) {
  if (!rows || rows.length === 0) return '<div class="muted">No rows</div>';
  const cols = Object.keys(rows[0]);
  const head = cols.map(c => `<th>${escapeHtml(c)}</th>`).join('');
  const body = rows.map(r => '<tr>' + cols.map(c => `<td>${escapeHtml(r[c])}</td>`).join('') + '</tr>').join('');
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}
const INTERNAL_RESULT_KEYS = new Set([
  'scenario_id', 'current_cmd', 'next_cmd', 'bank_relation', 'burst_length',
  'requested_gap_nck', 'ws_operand', 'data_rate_mbps', 'MR1.OP[4:0]',
  'MR1.OP[5]', 'MR1.OP[6]', 'MR11.OP[4]', 'MR23.OP[0]', 'MR23.OP[2]',
  'result_state', 'min_nck', 'max_nck', 'rule_id', 'warning_count'
]);
const RESULT_KEY_LABELS = {
  tCK_ns: 'tCK(ns)',
  tWCK_ns: 'tWCK(ns)',
  'WR->RD min (diff BG)': 'WR->RD Min(diff BG)',
  'WR->RD min (same BG)': 'WR->RD Min(same BG)',
  'RD sync-off deadline': 'RD Sync-Off Limit',
  'WR sync-off deadline': 'WR Sync-Off Limit',
  'tWCK2DQO max': 'tWCK2DQO Max',
};
function resultKeyLabel(key) {
  return RESULT_KEY_LABELS[key] || key;
}
function formatBank(value) {
  const labels = {
    different_bank_different_bg: 'Diff Bank / Diff BG',
    different_bank_same_bg: 'Diff Bank / Same BG',
    same_bank_same_bg: 'Same Bank / Same BG',
  };
  return labels[value] || value || '';
}
function formatState(value) {
  const labels = {
    allowed_with_new_sync: '가능',
    allowed_without_new_sync: '가능',
    too_early_with_new_sync: 'Too Early',
    too_early_without_new_sync: 'Too Early',
    too_late_with_new_sync: 'Too Late',
    too_late_without_new_sync: 'Too Late',
    not_allowed_with_new_sync: '불가',
    not_allowed_without_new_sync: '불가',
    requires_new_ws1_after_sync_off: 'WS=1 필요',
    allowed_wsoe: '가능',
    too_early_wsoe: 'Too Early',
    too_late_wsoe: 'Too Late',
  };
  return labels[value] || value || '';
}
function formatSweepRows(rows) {
  return (rows || []).map(row => {
    const out = {
      'CMD': `${row.current_cmd || ''} -> ${row.next_cmd || ''}`,
      'Bank/BG': formatBank(row.bank_relation),
      'BL': row.burst_length,
      'MR1[4:0]': row['MR1.OP[4:0]'],
      'DR(Mbps)': row.data_rate_mbps,
      'WLS': row['MR1.OP[5]'],
      'DEFF': row['MR1.OP[6]'],
      'DVFSL': row['MR11.OP[4]'],
      'WR Link': row['MR23.OP[0]'],
      'RD Link': row['MR23.OP[2]'],
      '입력 Gap': row.requested_gap_nck,
      '필요 Min': row.min_nck,
      '판정': formatState(row.result_state),
    };
    if (row.max_nck !== null && row.max_nck !== undefined && row.max_nck !== '') {
      out['허용 Max'] = row.max_nck;
    }
    for (const [key, value] of Object.entries(row)) {
      if (INTERNAL_RESULT_KEYS.has(key)) continue;
      out[resultKeyLabel(key)] = value;
    }
    return out;
  });
}
function escapeHtml(value) {
  if (value === null || value === undefined) return '';
  return String(value).replace(/[&<>"']/g, (m) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
}
async function getJson(url) {
  status('loading');
  const res = await fetch(url);
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  status('ready');
  return data;
}
async function loadSymbols() {
  const data = await getJson('/api/symbols?search=' + encodeURIComponent(qs('symbolSearch').value));
  const select = qs('symbolSelect');
  select.innerHTML = data.rows.map(r => `<option>${escapeHtml(r.symbol_id)}</option>`).join('');
  if (data.rows.some(r => r.symbol_id === 'RL')) select.value = 'RL';
  else if (data.rows.some(r => r.symbol_id === 'WR_TO_RD_DIFF')) select.value = 'WR_TO_RD_DIFF';
}
function renderChips(items) {
  if (!items || items.length === 0) return '';
  return '<div class="chips">' + items.map(item => `<span class="chip">${escapeHtml(item)}</span>`).join('') + '</div>';
}
function renderEdges(edges, emptyText) {
  if (!edges || edges.length === 0) return `<div class="hint">${escapeHtml(emptyText)}</div>`;
  return '<div class="edges">' + edges.map(e =>
    `<div class="edge">
      <span title="${escapeHtml(e.from_symbol)}">${escapeHtml(e.from_symbol)}</span>
      <b>→</b>
      <span title="${escapeHtml(e.to_symbol)}">${escapeHtml(e.to_symbol)}</span>
      <small class="muted" title="${escapeHtml(e.note || '')}">${escapeHtml(edgeReason(e))}</small>
    </div>`
  ).join('') + '</div>';
}
const FRIENDLY_SYMBOLS = {
  latency_table_id: 'Latency Table 선택 조건',
  read_dbi_enabled: 'Read DBI Enable',
  efficiency_mode_enabled: 'Efficiency Mode Enable',
  dvfsl_enabled: 'DVFSL Enable',
  write_link_protection_enabled: 'Write Link Protection Enable',
  read_link_protection_enabled: 'Read Link Protection Enable',
  BLN_MIN: 'BL/n min',
  BLN_MAX: 'BL/n max',
};
const COLLAPSED_SYMBOLS = new Set(['latency_table_id']);
function symbolTitle(symbol) {
  return FRIENDLY_SYMBOLS[symbol] || symbol;
}
function symbolDescription(symbol, nodes) {
  if (symbol === 'latency_table_id') return '아래 조건 조합으로 RL/WL lookup table이 선택됩니다.';
  const node = nodes && nodes[symbol] ? nodes[symbol] : {};
  return node.description_ko || node.source_ref || '';
}
function edgeReason(edge) {
  if (edge.rule_id === 'MR1_LATENCY_TABLE') return 'Latency table 선택에 사용';
  if (edge.rule_id === 'MR1_LATENCY_VALUES') return `${edge.to_symbol} 값을 table에서 선택`;
  if (edge.edge_type === 'decode') return 'MR bit 해석';
  if (edge.edge_type === 'selector') return '조건 선택';
  if (edge.edge_type === 'convert') return '단위 변환';
  if (edge.edge_type === 'formula') return '계산식 입력';
  return edge.description_ko || '구성 관계';
}
function incomingIndex(edges) {
  const incoming = {};
  const seen = new Set();
  for (const edge of edges || []) {
    const key = `${edge.from_symbol}->${edge.to_symbol}:${edge.rule_id}:${edge.key_role}`;
    if (seen.has(key)) continue;
    seen.add(key);
    if (!incoming[edge.to_symbol]) incoming[edge.to_symbol] = [];
    incoming[edge.to_symbol].push(edge);
  }
  for (const key of Object.keys(incoming)) {
    incoming[key].sort((a, b) => {
      const ap = COLLAPSED_SYMBOLS.has(a.from_symbol) ? 0 : 1;
      const bp = COLLAPSED_SYMBOLS.has(b.from_symbol) ? 0 : 1;
      return ap - bp || a.from_symbol.localeCompare(b.from_symbol);
    });
  }
  return incoming;
}
function renderTreeNode(symbol, incoming, nodes, path, viaEdge, isRoot=false) {
  const desc = symbolDescription(symbol, nodes);
  const childEdges = (incoming[symbol] || []).filter(edge => !path.includes(edge.from_symbol));
  const cardClass = isRoot ? 'tree-card root' : 'tree-card';
  const reason = viaEdge ? `<div class="tree-reason">${escapeHtml(edgeReason(viaEdge))}</div>` : '';
  const children = childEdges.length
    ? `<div class="tree-children">${childEdges.map(edge => renderTreeNode(edge.from_symbol, incoming, nodes, [...path, symbol], edge)).join('')}</div>`
    : '';
  return `
    <div class="tree-node">
      <div class="${cardClass}">
        <div class="tree-symbol">${escapeHtml(symbolTitle(symbol))}</div>
        <div class="tree-desc">${escapeHtml(desc)}</div>
        ${reason}
      </div>
      ${children}
    </div>
  `;
}
function renderDependencyTree(symbol, edges, nodes) {
  if (!edges || edges.length === 0) return '<div class="hint">등록된 구성 dependency가 없습니다.</div>';
  return `<div class="tree">${renderTreeNode(symbol, incomingIndex(edges), nodes || {}, [], null, true)}</div>`;
}
async function loadDetail() {
  const symbol = qs('symbolSelect').value || 'WR_TO_RD_DIFF';
  const data = await getJson(`/api/detail?symbol=${encodeURIComponent(symbol)}&depth=4`);
  const node = data.node || {};
  const formula = data.formula || {};
  qs('detail').innerHTML = `
    <div class="pill">${escapeHtml(symbol)}</div>
    <p>${escapeHtml(node.description_ko || '')}</p>
    ${formula.formula ? `<div class="subhead">계산식</div><div class="formula">${escapeHtml(formula.formula)}</div>` : ''}
    ${formula.dependencies ? `<div class="subhead">직접 구성 Symbol</div>${renderChips(formula.dependencies)}` : ''}
    <div class="subhead">${escapeHtml(symbol)} 구성 Tree</div>
    ${renderDependencyTree(symbol, data.upstream_edges, data.nodes)}
  `;
}
async function runSweep() {
  const mr1Ops = qs('mr1').value.split(',').map(v => v.trim()).filter(Boolean);
  const dvfslOps = qs('dvfsl').value.split(',').map(v => v.trim()).filter(Boolean);
  const tbdOps = mr1Ops.filter(v => TBD_MR1_OPS.has(v));
  const unknownOps = mr1Ops.filter(v => !SEEDED_MR1_OPS.has(v) && !TBD_MR1_OPS.has(v));
  const dvfslHighOps = dvfslOps.includes('1') ? mr1Ops.filter(v => !DVFSL_NUMERIC_MR1_OPS.has(v)) : [];
  if (tbdOps.length || unknownOps.length) {
    const messages = [];
    if (tbdOps.length) messages.push(`현재 DB에서 JEDEC TBD row라 계산 확정 불가: ${tbdOps.join(', ')}`);
    if (unknownOps.length) messages.push(`MR1.OP[4:0] speed-bin 목록에 없음: ${unknownOps.join(', ')}`);
    qs('viewSweep').innerHTML = `<p class="warn">${escapeHtml(messages.join('\\n'))}</p>`;
    return;
  }
  if (dvfslHighOps.length) {
    qs('viewSweep').innerHTML = `<p class="warn">${escapeHtml(`DVFSL=1의 현재 numeric WCK2DQ LF_L 범위는 MR1.OP[4:0] 00000/00001입니다. 고속 MR1(${dvfslHighOps.join(', ')})은 DVFSL=0으로 계산하거나 MR1 값을 00000/00001로 제한하세요.`)}</p>`;
    return;
  }
  const params = new URLSearchParams({
    current_cmd: qs('currentCmd').value,
    next_cmd: qs('nextCmd').value,
    bank_relation: qs('bankRelation').value,
    burst_length: qs('burstLength').value,
    gap: qs('gap').value,
    ws: qs('ws').value,
    mr1: qs('mr1').value,
    data_rate: qs('dataRate').value,
    match_mr1_speed_bin: qs('matchSpeed').value,
    wl_set_b: qs('wlSetB').value,
    outputs: qs('outputs').value,
    efficiency: qs('efficiency').value,
    dvfsl: qs('dvfsl').value,
    write_link: qs('writeLink').value,
    read_link: qs('readLink').value,
    max_rows: qs('maxRows').value,
  });
  const data = await getJson('/api/sweep?' + params.toString());
  qs('viewSweep').innerHTML = table(formatSweepRows(data.rows)) + (data.errors.length ? `<p class="warn">${escapeHtml(data.errors.slice(0, 8).join('\\n'))}</p>` : '');
}
window.addEventListener('load', async () => {
  await loadSymbols();
  await loadDetail();
  await runSweep();
});
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        return

    def send_json(self, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self) -> None:
        body = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if parsed.path == "/":
            self.send_html()
            return
        if parsed.path == "/api/symbols":
            rows = DB.symbols(params.get("search", [""])[0])
            self.send_json({"rows": rows})
            return
        if parsed.path == "/api/detail":
            symbol = params.get("symbol", ["WR_TO_RD_DIFF"])[0]
            depth = int(params.get("depth", ["4"])[0])
            detail = DB.symbol_detail(symbol, depth)
            involved_symbols = {symbol}
            for edge in detail["upstream_edges"] + detail["downstream_edges"]:
                involved_symbols.add(edge["from_symbol"])
                involved_symbols.add(edge["to_symbol"])
            nodes = {sid: DB.node_by_id[sid] for sid in involved_symbols if sid in DB.node_by_id}
            self.send_json(
                {
                    "node": detail["node"],
                    "formula": detail["formula"],
                    "upstream_edges": detail["upstream_edges"],
                    "downstream_edges": detail["downstream_edges"],
                    "nodes": nodes,
                    "tables_that_output_symbol": detail["tables_that_output_symbol"],
                    "tables_that_key_symbol": detail["tables_that_key_symbol"],
                }
            )
            return
        if parsed.path == "/api/coverage":
            self.send_json({"rows": DB.coverage})
            return
        if parsed.path == "/api/sweep":
            rows, errors = run_sweep(
                current_cmd=params.get("current_cmd", ["WR"])[0],
                next_cmd=params.get("next_cmd", ["RD"])[0],
                bank_relation=params.get("bank_relation", ["different_bank_different_bg"])[0],
                burst_length=params.get("burst_length", ["BL24"])[0],
                requested_gap_nck=int(params.get("gap", ["24"])[0]),
                ws_operand=int(params.get("ws", ["1"])[0]),
                mr1_ops=parse_list(params, "mr1", "00001"),
                data_rates=parse_float_list(params, "data_rate", "9600"),
                match_mr1_speed_bin=params.get("match_mr1_speed_bin", ["1"])[0] != "0",
                wl_set_b_values=parse_int_list(params, "wl_set_b", "0"),
                efficiency_values=parse_int_list(params, "efficiency", "0,1"),
                dvfsl_values=parse_int_list(params, "dvfsl", "0,1"),
                write_link_values=parse_int_list(params, "write_link", "0,1"),
                read_link_values=parse_int_list(params, "read_link", "0"),
                output_symbols=parse_list(params, "outputs", "RL,WL,tCK_ns,tWTR_S,tWTR_L,WR->RD min (diff BG),tRTW"),
                max_rows=int(params.get("max_rows", ["500"])[0]),
            )
            self.send_json({"rows": public_rows(rows), "errors": errors})
            return
        self.send_response(404)
        self.end_headers()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"LPDDR6 semantic UI: http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
