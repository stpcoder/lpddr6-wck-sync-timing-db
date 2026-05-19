#!/usr/bin/env python3
"""Dependency-free browser UI for the LPDDR6 semantic timing DB."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from semantic_query import SemanticDB, TARGET_INPUTS, USER_METRICS, evaluate_target_parameter, run_sweep, target_symbol_rows


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
    .control-group {
      display: grid;
      gap: 9px;
      padding: 10px;
      border: 1px solid #edf0f5;
      border-radius: 7px;
      background: #fbfcfe;
    }
    .group-title {
      font-weight: 700;
      color: #0f172a;
      font-size: 13px;
    }
    .target-inputs {
      display: grid;
      grid-template-columns: 1fr;
      gap: 8px;
    }
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
    select[multiple] {
      min-height: 94px;
      padding: 5px;
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
      grid-template-rows: minmax(380px, 1fr) minmax(220px, .8fr);
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
    .tree-value {
      justify-self: end;
      font-weight: 700;
      color: #0f172a;
      background: #eef2ff;
      border: 1px solid #dbe3ff;
      border-radius: 999px;
      padding: 2px 8px;
      white-space: nowrap;
      max-width: 260px;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .target-summary {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: start;
      padding: 10px;
      border: 1px solid #bfdbfe;
      border-radius: 7px;
      background: #eff6ff;
      margin-bottom: 10px;
    }
    .target-result {
      font-size: 20px;
      font-weight: 750;
      color: #0f172a;
      white-space: nowrap;
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
    .graph-shell {
      margin-top: 10px;
      border: 1px solid #dbe3ef;
      border-radius: 8px;
      background:
        linear-gradient(90deg, rgba(148, 163, 184, 0.08) 1px, transparent 1px),
        linear-gradient(180deg, rgba(148, 163, 184, 0.08) 1px, transparent 1px),
        #fbfdff;
      background-size: 24px 24px;
      overflow: auto;
    }
    .graph-toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      align-items: center;
      margin-top: 10px;
      padding: 7px;
      border: 1px solid #edf0f5;
      border-radius: 8px;
      background: #fbfcfe;
    }
    .graph-toolbar button {
      width: auto;
      min-height: 28px;
      padding: 4px 9px;
      background: #fff;
      color: #0f172a;
      border-color: #cbd5e1;
    }
    .graph-toolbar .graph-toggle {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      min-height: 28px;
      padding: 4px 8px;
      border: 1px solid #dbe3ef;
      border-radius: 6px;
      background: #fff;
      color: #334155;
      font-size: 12px;
    }
    .graph-toggle input {
      width: auto;
      min-height: 0;
      margin: 0;
    }
    .graph-zoom-label {
      color: #64748b;
      font-size: 12px;
      font-variant-numeric: tabular-nums;
    }
    .graph-canvas {
      position: relative;
      min-width: 100%;
      min-height: 360px;
    }
    .graph-content {
      position: absolute;
      left: 0;
      top: 0;
      transform-origin: 0 0;
    }
    .graph-edges {
      position: absolute;
      inset: 0;
      pointer-events: none;
      overflow: visible;
    }
    .graph-edge {
      fill: none;
      stroke: #94a3b8;
      stroke-width: 1.7;
    }
    .graph-node-card {
      position: absolute;
      display: grid;
      grid-template-rows: auto auto minmax(0, 1fr);
      gap: 5px;
      width: 260px;
      height: 112px;
      padding: 9px 10px;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.96);
      box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08);
      cursor: grab;
      user-select: none;
    }
    .graph-node-card.dragging { cursor: grabbing; z-index: 5; }
    .graph-node-card.root {
      border-color: #2563eb;
      background: #eff6ff;
      box-shadow: 0 14px 30px rgba(37, 99, 235, 0.16);
    }
    .graph-node-card.leaf {
      border-color: #99f6e4;
      background: #f0fdfa;
    }
    .graph-node-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      align-items: start;
    }
    .graph-node-title {
      min-width: 0;
      color: #0f172a;
      font-weight: 760;
      line-height: 1.2;
      overflow-wrap: anywhere;
    }
    .graph-node-value {
      max-width: 112px;
      padding: 2px 7px;
      border: 1px solid #dbe3ff;
      border-radius: 999px;
      background: #eef2ff;
      color: #1e293b;
      font-size: 12px;
      font-weight: 750;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .graph-node-kind {
      color: #64748b;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }
    .graph-node-formula {
      max-height: 44px;
      overflow: hidden;
      color: #334155;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 11px;
      line-height: 1.3;
      overflow-wrap: anywhere;
    }
    .calc-table-wrap {
      margin-top: 10px;
      border: 1px solid #edf0f5;
      border-radius: 8px;
      overflow: auto;
    }
    .calc-depth {
      color: #64748b;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
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
      <div class="panel-title">Timing Calculator</div>
      <div class="controls">
        <div class="control-group">
          <div class="group-title">Timing Parameter</div>
          <label><span class="label-title">Target Parameter <span class="info" tabindex="0">i<span class="tip">알고 싶은 timing parameter를 고릅니다. 아래 leaf 조건만 입력하면 중간 parameter를 거쳐 target 값까지 계산됩니다.</span></span></span>
            <select id="targetSelect"></select>
          </label>
          <div class="target-inputs" id="targetInputs"></div>
          <button onclick="runTargetCalc()">계산 트리 업데이트</button>
        </div>
        <div class="control-group">
          <div class="group-title">Command Pair Window</div>
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
        <label><span class="label-title">Operating Data Rate Rows <span class="info" tabindex="0">i<span class="tip">비교할 operating data-rate 범위를 고릅니다. 선택한 범위는 내부 latency row와 tCK/WCK 계산에 공통으로 사용됩니다.</span></span></span>
          <select id="mr1" multiple size="6">
            <option value="00000">Up to 1067 Mbps</option>
            <option value="00001" selected>Up to 1600 Mbps</option>
            <option value="00010">Up to 2133 Mbps</option>
            <option value="00011">Up to 2750 Mbps</option>
            <option value="00100">Up to 3200 Mbps</option>
            <option value="00101">Up to 3750 Mbps</option>
            <option value="00110">Up to 4267 Mbps</option>
            <option value="00111">Up to 4800 Mbps</option>
            <option value="01000">Up to 5500 Mbps</option>
            <option value="01001">Up to 6400 Mbps</option>
            <option value="01010">Up to 7500 Mbps</option>
            <option value="01011">Up to 8533 Mbps</option>
            <option value="01100">Up to 9600 Mbps</option>
            <option value="01101">Up to 10667 Mbps</option>
          </select>
        </label>
        <div class="grid2">
          <label><span class="label-title">Data Rate Source <span class="info" tabindex="0">i<span class="tip">기본값은 위에서 고른 operating data-rate row의 upper rate를 사용합니다. 직접 입력은 table 검증용 예외 모드입니다.</span></span></span>
            <select id="matchSpeed"><option value="1">Use selected rows</option><option value="0">Use direct Mbps input</option></select>
          </label>
          <label><span class="label-title">Direct Data Rate (Mbps) <span class="info" tabindex="0">i<span class="tip">Data Rate Source를 직접 입력으로 바꾼 경우에만 사용합니다. 기본 모드에서는 선택 row 값이 사용됩니다.</span></span></span><input id="dataRate" value="9600" /></label>
        </div>
        <div class="grid2">
          <label><span class="label-title">Write Latency Set <span class="info" tabindex="0">i<span class="tip">WL lookup에서 Set A 또는 Set B 중 어떤 column을 사용할지 선택합니다.</span></span></span>
            <select id="wlSetB"><option value="0" selected>Set A</option><option value="1">Set B</option></select>
          </label>
          <label><span class="label-title">Dynamic Efficiency Mode <span class="info" tabindex="0">i<span class="tip">Latency table 및 일부 AC parameter selector에 들어가는 efficiency 조건입니다. 여러 조건을 동시에 선택하면 조합 표로 sweep합니다.</span></span></span>
            <select id="efficiency" multiple size="2"><option value="0" selected>Disabled</option><option value="1" selected>Enabled</option></select>
          </label>
        </div>
        <div class="grid3">
          <label><span class="label-title">DVFSL <span class="info" tabindex="0">i<span class="tip">Low-voltage DVFS timing family 선택 조건입니다. 여러 조건을 동시에 선택하면 조합 표로 sweep합니다.</span></span></span>
            <select id="dvfsl" multiple size="2"><option value="0" selected>Disabled</option><option value="1" selected>Enabled</option></select>
          </label>
          <label><span class="label-title">Write Link Protection <span class="info" tabindex="0">i<span class="tip">Write link protection enable 조건입니다. Latency selector와 write 관련 timing path에 영향을 줍니다.</span></span></span>
            <select id="writeLink" multiple size="2"><option value="0" selected>Disabled</option><option value="1" selected>Enabled</option></select>
          </label>
          <label><span class="label-title">Read Link Protection <span class="info" tabindex="0">i<span class="tip">Read link protection enable 조건입니다. Read latency selector에 영향을 줍니다.</span></span></span>
            <select id="readLink" multiple size="2"><option value="0" selected>Disabled</option><option value="1">Enabled</option></select>
          </label>
        </div>
        <label><span class="label-title">Timing Metrics <span class="info" tabindex="0">i<span class="tip">결과표에 표시할 값입니다. 예: RL, WL, tWTR_S, tWTR_L, tRTW, WR-&gt;RD min.</span></span></span><input id="outputs" value="RL,WL,tCK_ns,tWTR_S,tWTR_L,WR->RD min (diff BG),tRTW,tRTRRD,tWRWTR" /></label>
        <button onclick="runSweep()">조건 조합 표 만들기</button>
        </div>
      </div>
    </aside>
    <div class="content">
      <div class="top">
        <section>
          <div class="panel-title">Timing Parameter Tree</div>
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
const SPEED_LABELS = {
  '00000': 'Up to 1067 Mbps',
  '00001': 'Up to 1600 Mbps',
  '00010': 'Up to 2133 Mbps',
  '00011': 'Up to 2750 Mbps',
  '00100': 'Up to 3200 Mbps',
  '00101': 'Up to 3750 Mbps',
  '00110': 'Up to 4267 Mbps',
  '00111': 'Up to 4800 Mbps',
  '01000': 'Up to 5500 Mbps',
  '01001': 'Up to 6400 Mbps',
  '01010': 'Up to 7500 Mbps',
  '01011': 'Up to 8533 Mbps',
  '01100': 'Up to 9600 Mbps',
  '01101': 'Up to 10667 Mbps',
  '01110': 'Up to 11733 Mbps (TBD row)',
  '01111': 'Up to 12800 Mbps (TBD row)',
  '10000': 'Up to 14400 Mbps (TBD row)',
};
function selectedValues(id) {
  const el = qs(id);
  if (!el) return '';
  if (el.tagName === 'SELECT' && el.multiple) {
    const values = Array.from(el.selectedOptions).map(opt => opt.value);
    return values.length ? values.join(',') : el.value;
  }
  return el.value;
}
function speedLabel(code) {
  return SPEED_LABELS[code] || 'Unknown speed row';
}
function enabledText(value) {
  return String(value) === '1' ? 'Enabled' : 'Disabled';
}
function wlSetText(value) {
  return String(value) === '1' ? 'Set B' : 'Set A';
}

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
      'Operating Rate': speedLabel(row['MR1.OP[4:0]']),
      'Data Rate(Mbps)': row.data_rate_mbps,
      'WL Set': wlSetText(row['MR1.OP[5]']),
      'Efficiency': enabledText(row['MR1.OP[6]']),
      'DVFSL': enabledText(row['MR11.OP[4]']),
      'WR Link': enabledText(row['MR23.OP[0]']),
      'RD Link': enabledText(row['MR23.OP[2]']),
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
  if (!res.ok) {
    const text = await res.text();
    status('error');
    throw new Error(text);
  }
  const data = await res.json();
  status('ready');
  return data;
}
async function loadTargets() {
  const data = await getJson('/api/targets');
  const select = qs('targetSelect');
  select.innerHTML = data.rows.map(r =>
    `<option value="${escapeHtml(r.symbol)}">${escapeHtml(r.symbol)} · ${escapeHtml(r.label)}</option>`
  ).join('');
  select.value = data.rows.some(r => r.symbol === 'tRTRRD') ? 'tRTRRD' : data.rows[0].symbol;
  select.addEventListener('change', runTargetCalc);
}
function currentTargetInputValues() {
  const values = {};
  document.querySelectorAll('[data-target-input]').forEach(el => {
    values[el.getAttribute('data-target-input')] = el.value;
  });
  return values;
}
function scheduleTargetCalc() {
  clearTimeout(targetCalcTimer);
  targetCalcTimer = setTimeout(() => runTargetCalc(), 180);
}
function attachTargetInputAutoUpdate() {
  document.querySelectorAll('[data-target-input]').forEach(el => {
    el.addEventListener('change', scheduleTargetCalc);
  });
}
function renderTargetInputs(specs) {
  const previous = currentTargetInputValues();
  qs('targetInputs').innerHTML = (specs || []).map(spec => {
    const value = previous[spec.id] ?? spec.value ?? spec.default ?? '';
    const tip = escapeHtml(spec.description || '');
    if (spec.kind === 'bool') {
      const enabled = ['1', 'true', 'True', true].includes(value);
      return `<label><span class="label-title">${escapeHtml(spec.label)} <span class="info" tabindex="0">i<span class="tip">${tip}</span></span></span>
        <select data-target-input="${escapeHtml(spec.id)}">
          <option value="0"${enabled ? '' : ' selected'}>Disabled</option>
          <option value="1"${enabled ? ' selected' : ''}>Enabled</option>
        </select>
      </label>`;
    }
    const options = (spec.options || []).map(opt => {
      const selected = String(opt.value) === String(value) ? ' selected' : '';
      return `<option value="${escapeHtml(opt.value)}"${selected}>${escapeHtml(opt.label || opt.value)}</option>`;
    }).join('');
    return `<label><span class="label-title">${escapeHtml(spec.label)} <span class="info" tabindex="0">i<span class="tip">${tip}</span></span></span>
      <select data-target-input="${escapeHtml(spec.id)}">${options}</select>
    </label>`;
  }).join('');
  attachTargetInputAutoUpdate();
}
function nodeValueText(node) {
  if (node.value === null || node.value === undefined || node.value === '') return '';
  const unit = node.unit ? ` ${node.unit}` : '';
  return `${node.value}${unit}`;
}
function renderTargetTreeNode(node, isRoot=false) {
  const value = nodeValueText(node);
  const formula = node.formula && node.formula !== 'user selected leaf input'
    ? `<div class="tree-reason">${escapeHtml(node.formula)}</div>` : '';
  const children = node.children && node.children.length
    ? `<div class="tree-children">${node.children.map(child => renderTargetTreeNode(child)).join('')}</div>` : '';
  return `
    <div class="tree-node">
      <div class="tree-card${isRoot ? ' root' : ''}">
        <div class="tree-symbol">${escapeHtml(node.label || node.symbol)}</div>
        ${value ? `<div class="tree-value" title="${escapeHtml(value)}">${escapeHtml(value)}</div>` : '<div></div>'}
        <div class="tree-desc">${escapeHtml(node.description || '')}</div>
        ${formula}
      </div>
      ${children}
    </div>
  `;
}
const GRAPH_NODE_W = 260;
const GRAPH_NODE_H = 112;
const GRAPH_GAP_X = 30;
const GRAPH_GAP_Y = 98;
const GRAPH_PAD = 24;
const graphUiState = {
  scale: 1,
  manual: false,
  positions: {},
  lastGraph: null,
};
let targetCalcTimer = null;
function conciseFormula(node) {
  if (!node || !node.formula) return '';
  if (node.formula === 'user selected leaf input') return 'User selected';
  return node.formula;
}
function currentGraphKey() {
  return qs('targetSelect') ? qs('targetSelect').value : 'target';
}
function graphPositionBucket() {
  const key = currentGraphKey();
  if (!graphUiState.positions[key]) graphUiState.positions[key] = {};
  return graphUiState.positions[key];
}
function graphNodeKind(node, isRoot=false) {
  if (isRoot) return 'root';
  if (node.leaf) return 'leaf';
  return 'parameter';
}
function graphNodeKindLabel(node, isRoot=false) {
  if (isRoot) return 'target';
  if (node.leaf) return 'leaf input';
  return 'computed';
}
function layoutTargetGraph(root) {
  let cursor = 0;
  let maxDepth = 0;
  const nodes = [];
  const edges = [];
  function place(node, depth, path) {
    maxDepth = Math.max(maxDepth, depth);
    const id = path.length ? `n-${path.join('-')}` : 'n-root';
    const children = node.children || [];
    if (!children.length) {
      const placed = { id, node, x: cursor, y: depth * (GRAPH_NODE_H + GRAPH_GAP_Y), depth, isRoot: depth === 0 };
      cursor += GRAPH_NODE_W + GRAPH_GAP_X;
      nodes.push(placed);
      return placed;
    }
    const placedChildren = children.map((child, index) => place(child, depth + 1, path.concat(index)));
    const minX = Math.min(...placedChildren.map(child => child.x));
    const maxX = Math.max(...placedChildren.map(child => child.x + GRAPH_NODE_W));
    const x = minX + ((maxX - minX - GRAPH_NODE_W) / 2);
    const placed = { id, node, x, y: depth * (GRAPH_NODE_H + GRAPH_GAP_Y), depth, isRoot: depth === 0 };
    nodes.push(placed);
    placedChildren.forEach(child => edges.push({ from: placed, to: child }));
    return placed;
  }
  place(root, 0, []);
  const minX = Math.min(...nodes.map(node => node.x));
  const maxX = Math.max(...nodes.map(node => node.x + GRAPH_NODE_W));
  nodes.forEach(node => {
    node.x = node.x - minX + GRAPH_PAD;
    node.y = node.y + GRAPH_PAD;
  });
  if (graphUiState.manual) {
    const saved = graphPositionBucket();
    nodes.forEach(node => {
      if (saved[node.id]) {
        node.x = saved[node.id].x;
        node.y = saved[node.id].y;
      }
    });
  }
  const maxFinalX = Math.max(...nodes.map(node => node.x + GRAPH_NODE_W));
  const maxFinalY = Math.max(...nodes.map(node => node.y + GRAPH_NODE_H));
  return {
    nodes,
    edges,
    width: Math.max(760, maxX - minX + GRAPH_PAD * 2, maxFinalX + GRAPH_PAD),
    height: Math.max((maxDepth + 1) * GRAPH_NODE_H + maxDepth * GRAPH_GAP_Y + GRAPH_PAD * 2, maxFinalY + GRAPH_PAD),
  };
}
function edgePath(edge) {
  const x1 = edge.from.x + GRAPH_NODE_W / 2;
  const y1 = edge.from.y + GRAPH_NODE_H;
  const x2 = edge.to.x + GRAPH_NODE_W / 2;
  const y2 = edge.to.y;
  const mid = y1 + Math.max(28, (y2 - y1) / 2);
  return `M ${x1} ${y1} C ${x1} ${mid}, ${x2} ${mid}, ${x2} ${y2}`;
}
function renderGraphNode(placed) {
  const node = placed.node;
  const value = nodeValueText(node);
  const formula = conciseFormula(node);
  const kind = graphNodeKind(node, placed.isRoot);
  return `
    <div class="graph-node-card ${escapeHtml(kind)}" data-node-id="${escapeHtml(placed.id)}" style="left:${placed.x}px;top:${placed.y}px">
      <div class="graph-node-head">
        <div class="graph-node-title" title="${escapeHtml(node.symbol || '')}">${escapeHtml(node.label || node.symbol || '')}</div>
        ${value ? `<div class="graph-node-value" title="${escapeHtml(value)}">${escapeHtml(value)}</div>` : ''}
      </div>
      <div class="graph-node-kind">${escapeHtml(graphNodeKindLabel(node, placed.isRoot))}</div>
      <div class="graph-node-formula" title="${escapeHtml(formula)}">${escapeHtml(formula)}</div>
    </div>
  `;
}
function renderTargetGraph(root) {
  if (!root) return '<div class="hint">No graph data</div>';
  const graph = layoutTargetGraph(root);
  graphUiState.lastGraph = graph;
  const paths = graph.edges.map((edge, index) => `<path class="graph-edge" data-edge-index="${index}" marker-end="url(#arrow)" d="${edgePath(edge)}"></path>`).join('');
  const nodes = graph.nodes.map(renderGraphNode).join('');
  return `
    <div class="graph-toolbar">
      <button type="button" data-graph-action="zoom-out">-</button>
      <button type="button" data-graph-action="zoom-in">+</button>
      <button type="button" data-graph-action="fit">Fit</button>
      <button type="button" data-graph-action="reset-view">Reset View</button>
      <button type="button" data-graph-action="reset-layout">Reset Layout</button>
      <label class="graph-toggle"><input id="graphManual" type="checkbox"${graphUiState.manual ? ' checked' : ''}> Manual layout</label>
      <span class="graph-zoom-label" id="graphZoomLabel"></span>
    </div>
    <div class="graph-shell">
      <div class="graph-canvas" id="graphCanvas" style="width:${graph.width}px;height:${graph.height}px">
        <div class="graph-content" id="graphContent" style="width:${graph.width}px;height:${graph.height}px">
          <svg class="graph-edges" id="graphEdges" width="${graph.width}" height="${graph.height}" viewBox="0 0 ${graph.width} ${graph.height}">
            <defs>
              <marker id="arrow" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto">
                <path d="M0,0 L8,4.5 L0,9 Z" fill="#94a3b8"></path>
              </marker>
            </defs>
            ${paths}
          </svg>
          ${nodes}
        </div>
      </div>
    </div>
  `;
}
function graphBounds(graph) {
  if (!graph || !graph.nodes.length) return { width: 760, height: 360 };
  const width = Math.max(760, Math.max(...graph.nodes.map(node => node.x + GRAPH_NODE_W)) + GRAPH_PAD);
  const height = Math.max(360, Math.max(...graph.nodes.map(node => node.y + GRAPH_NODE_H)) + GRAPH_PAD);
  graph.width = width;
  graph.height = height;
  return { width, height };
}
function applyGraphTransform() {
  const graph = graphUiState.lastGraph;
  const content = qs('graphContent');
  const canvas = qs('graphCanvas');
  const edges = qs('graphEdges');
  if (!graph || !content || !canvas || !edges) return;
  const bounds = graphBounds(graph);
  content.style.width = `${bounds.width}px`;
  content.style.height = `${bounds.height}px`;
  content.style.transform = `scale(${graphUiState.scale})`;
  canvas.style.width = `${bounds.width * graphUiState.scale}px`;
  canvas.style.height = `${bounds.height * graphUiState.scale}px`;
  edges.setAttribute('width', bounds.width);
  edges.setAttribute('height', bounds.height);
  edges.setAttribute('viewBox', `0 0 ${bounds.width} ${bounds.height}`);
  const label = qs('graphZoomLabel');
  if (label) label.textContent = `${Math.round(graphUiState.scale * 100)}%`;
}
function refreshGraphEdges() {
  const graph = graphUiState.lastGraph;
  if (!graph) return;
  graph.edges.forEach((edge, index) => {
    const path = document.querySelector(`[data-edge-index="${index}"]`);
    if (path) path.setAttribute('d', edgePath(edge));
  });
  applyGraphTransform();
}
function setGraphScale(nextScale) {
  graphUiState.scale = Math.max(0.35, Math.min(1.8, nextScale));
  applyGraphTransform();
}
function fitGraph() {
  const graph = graphUiState.lastGraph;
  const shell = document.querySelector('.graph-shell');
  if (!graph || !shell) return;
  const bounds = graphBounds(graph);
  const scaleX = (shell.clientWidth - 24) / bounds.width;
  const scaleY = (shell.clientHeight - 24 || 360) / bounds.height;
  setGraphScale(Math.min(1, Math.max(0.35, Math.min(scaleX, scaleY))));
}
function resetGraphLayout() {
  delete graphUiState.positions[currentGraphKey()];
  graphUiState.manual = false;
  runTargetCalc();
}
function setManualLayout(enabled) {
  graphUiState.manual = enabled;
  const checkbox = qs('graphManual');
  if (checkbox) checkbox.checked = enabled;
}
function handleGraphToolbar(event) {
  const button = event.target.closest('[data-graph-action]');
  if (!button) return;
  const action = button.getAttribute('data-graph-action');
  if (action === 'zoom-in') setGraphScale(graphUiState.scale + 0.12);
  if (action === 'zoom-out') setGraphScale(graphUiState.scale - 0.12);
  if (action === 'fit') fitGraph();
  if (action === 'reset-view') setGraphScale(1);
  if (action === 'reset-layout') resetGraphLayout();
}
function startGraphNodeDrag(event) {
  const card = event.target.closest('.graph-node-card');
  const graph = graphUiState.lastGraph;
  if (!card || !graph || event.button !== 0) return;
  event.preventDefault();
  setManualLayout(true);
  const id = card.getAttribute('data-node-id');
  const node = graph.nodes.find(item => item.id === id);
  if (!node) return;
  card.classList.add('dragging');
  const startX = event.clientX;
  const startY = event.clientY;
  const nodeStartX = node.x;
  const nodeStartY = node.y;
  const saved = graphPositionBucket();
  function move(moveEvent) {
    const dx = (moveEvent.clientX - startX) / graphUiState.scale;
    const dy = (moveEvent.clientY - startY) / graphUiState.scale;
    node.x = Math.max(GRAPH_PAD, nodeStartX + dx);
    node.y = Math.max(GRAPH_PAD, nodeStartY + dy);
    saved[id] = { x: node.x, y: node.y };
    card.style.left = `${node.x}px`;
    card.style.top = `${node.y}px`;
    refreshGraphEdges();
  }
  function stop() {
    card.classList.remove('dragging');
    document.removeEventListener('pointermove', move);
    document.removeEventListener('pointerup', stop);
  }
  document.addEventListener('pointermove', move);
  document.addEventListener('pointerup', stop);
}
function mountGraphInteractions() {
  const toolbar = document.querySelector('.graph-toolbar');
  const canvas = qs('graphCanvas');
  if (toolbar) toolbar.addEventListener('click', handleGraphToolbar);
  const checkbox = qs('graphManual');
  if (checkbox) {
    checkbox.addEventListener('change', () => {
      graphUiState.manual = checkbox.checked;
      if (!graphUiState.manual) runTargetCalc();
    });
  }
  if (canvas) canvas.addEventListener('pointerdown', startGraphNodeDrag);
  applyGraphTransform();
}
function collectCalcRows(node, rows=[], depth=0) {
  if (!node) return rows;
  rows.push({
    Level: depth,
    Symbol: node.symbol || '',
    Name: node.label || node.symbol || '',
    Value: nodeValueText(node),
    Formula: conciseFormula(node),
    Source: node.source || '',
  });
  (node.children || []).forEach(child => collectCalcRows(child, rows, depth + 1));
  return rows;
}
function renderCalculationTable(root) {
  const rows = collectCalcRows(root).map(row => ({
    Level: `${'· '.repeat(row.Level)}${row.Level}`,
    Symbol: row.Symbol,
    Name: row.Name,
    Value: row.Value,
    Formula: row.Formula,
    Source: row.Source,
  }));
  return `<div class="calc-table-wrap">${table(rows)}</div>`;
}
function renderTargetResult(data) {
  const target = data.target || {};
  const value = target.value === null || target.value === undefined ? 'unresolved' : `${target.value}${target.unit ? ' ' + target.unit : ''}`;
  const warnings = data.warnings && data.warnings.length
    ? `<p class="warn">${escapeHtml(data.warnings.slice(0, 6).join('\\n'))}</p>` : '';
  qs('detail').innerHTML = `
    <div class="target-summary">
      <div>
        <div class="pill">${escapeHtml(target.symbol || '')}</div>
        <p>${escapeHtml(target.description || '')}</p>
        ${target.formula ? `<div class="formula">${escapeHtml(target.formula)}</div>` : ''}
      </div>
      <div class="target-result">${escapeHtml(value)}</div>
    </div>
    ${renderTargetGraph(data.tree)}
    <div class="subhead">Calculation References</div>
    ${renderCalculationTable(data.tree)}
    ${warnings}
  `;
  mountGraphInteractions();
}
async function runTargetCalc() {
  const params = new URLSearchParams({ target: qs('targetSelect').value || 'tRTRRD' });
  for (const [key, value] of Object.entries(currentTargetInputValues())) params.set(key, value);
  try {
    const data = await getJson('/api/target_eval?' + params.toString());
    renderTargetInputs(data.inputs);
    renderTargetResult(data);
  } catch (err) {
    qs('detail').innerHTML = `<p class="warn">${escapeHtml(err.message)}</p>`;
  }
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
  const mr1Ops = selectedValues('mr1').split(',').map(v => v.trim()).filter(Boolean);
  const dvfslOps = selectedValues('dvfsl').split(',').map(v => v.trim()).filter(Boolean);
  const tbdOps = mr1Ops.filter(v => TBD_MR1_OPS.has(v));
  const unknownOps = mr1Ops.filter(v => !SEEDED_MR1_OPS.has(v) && !TBD_MR1_OPS.has(v));
  const dvfslHighOps = dvfslOps.includes('1') ? mr1Ops.filter(v => !DVFSL_NUMERIC_MR1_OPS.has(v)) : [];
  if (tbdOps.length || unknownOps.length) {
    const messages = [];
    if (tbdOps.length) messages.push(`현재 DB에서 JEDEC TBD row라 계산 확정 불가: ${tbdOps.map(speedLabel).join(', ')}`);
    if (unknownOps.length) messages.push(`지원하지 않는 operating data-rate row가 선택되었습니다.`);
    qs('viewSweep').innerHTML = `<p class="warn">${escapeHtml(messages.join('\\n'))}</p>`;
    return;
  }
  if (dvfslHighOps.length) {
    qs('viewSweep').innerHTML = `<p class="warn">${escapeHtml(`현재 seed에서 DVFSL enabled numeric WCK2DQ LF_L 값은 1600 Mbps 이하 row만 확정되어 있습니다. ${dvfslHighOps.map(speedLabel).join(', ')} 조건은 DVFSL disabled로 계산하거나 operating row를 낮춰야 합니다.`)}</p>`;
    return;
  }
  const params = new URLSearchParams({
    current_cmd: qs('currentCmd').value,
    next_cmd: qs('nextCmd').value,
    bank_relation: qs('bankRelation').value,
    burst_length: qs('burstLength').value,
    gap: qs('gap').value,
    ws: qs('ws').value,
    mr1: selectedValues('mr1'),
    data_rate: qs('dataRate').value,
    match_mr1_speed_bin: qs('matchSpeed').value,
    wl_set_b: selectedValues('wlSetB'),
    outputs: qs('outputs').value,
    efficiency: selectedValues('efficiency'),
    dvfsl: selectedValues('dvfsl'),
    write_link: selectedValues('writeLink'),
    read_link: selectedValues('readLink'),
    max_rows: qs('maxRows').value,
  });
  const data = await getJson('/api/sweep?' + params.toString());
  qs('viewSweep').innerHTML = table(formatSweepRows(data.rows)) + (data.errors.length ? `<p class="warn">${escapeHtml(data.errors.slice(0, 8).join('\\n'))}</p>` : '');
}
window.addEventListener('load', async () => {
  await loadTargets();
  await runTargetCalc();
  await runSweep();
});
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        return

    def send_json(self, payload: dict, status_code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status_code)
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
        if parsed.path == "/api/targets":
            self.send_json({"rows": target_symbol_rows()})
            return
        if parsed.path == "/api/target_eval":
            target = params.get("target", ["tRTRRD"])[0]
            inputs = {key: params.get(key, [spec.get("default")])[0] for key, spec in TARGET_INPUTS.items()}
            try:
                self.send_json(evaluate_target_parameter(target, inputs, DB))
            except Exception as exc:
                self.send_json({"error": str(exc)}, status_code=400)
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
