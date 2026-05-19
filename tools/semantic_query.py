#!/usr/bin/env python3
"""Semantic query helpers for the LPDDR6 timing graph.

The UI and CLI use this module as a thin semantic layer over the CSV/JSON
database plus the seeded evaluator. It intentionally keeps the first query
surface narrow: symbol exploration, dependency expansion, and scenario sweeps
for the current WCK Sync-Off timing path.
"""

from __future__ import annotations

import copy
import csv
import json
import math
from collections import defaultdict
from itertools import product
from pathlib import Path
from typing import Any

from evaluate_lpddr6_timing_seed import Evaluator


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
GRAPH = DATA / "graph"
FORMULAS = DATA / "formulas"
SCENARIOS = ROOT / "scenarios"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class SemanticDB:
    def __init__(self) -> None:
        self.nodes = read_csv(GRAPH / "lpddr6_symbol_nodes.csv")
        self.edges = read_csv(GRAPH / "lpddr6_dependency_edges.csv")
        self.table_keys = read_csv(GRAPH / "lpddr6_table_keys.csv")
        self.coverage = read_csv(DATA / "coverage" / "lpddr6_wck_sync_graph_coverage.csv")
        self.formulas = read_json(FORMULAS / "lpddr6_formula_registry.json")["expressions"]
        self.node_by_id = {row["symbol_id"]: row for row in self.nodes}
        self.upstream = self._index_edges("to_symbol")
        self.downstream = self._index_edges("from_symbol")

    def _index_edges(self, key: str) -> dict[str, list[dict[str, str]]]:
        out: dict[str, list[dict[str, str]]] = defaultdict(list)
        for edge in self.edges:
            out[edge[key]].append(edge)
        return out

    def symbols(self, text: str = "", kinds: list[str] | None = None) -> list[dict[str, str]]:
        text = text.lower().strip()
        kind_set = set(kinds or [])
        rows = []
        for node in self.nodes:
            haystack = " ".join(node.values()).lower()
            if text and text not in haystack:
                continue
            if kind_set and node["kind"] not in kind_set:
                continue
            rows.append(node)
        return rows

    def formula_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for formula_id, entry in self.formulas.items():
            rows.append(
                {
                    "formula_id": formula_id,
                    "unit": entry.get("unit", ""),
                    "source": entry.get("source", ""),
                    "formula": entry.get("formula", ""),
                    "dependencies": "|".join(entry.get("dependencies", [])),
                    "resolver": entry.get("resolver", ""),
                    "description_ko": entry.get("description_ko", ""),
                }
            )
        return rows

    def collect_edges(self, target: str, direction: str = "upstream", depth: int = 4) -> list[dict[str, str]]:
        index = self.upstream if direction == "upstream" else self.downstream
        next_key = "from_symbol" if direction == "upstream" else "to_symbol"
        seen: set[tuple[str, str]] = set()

        def walk(symbol: str, remaining: int) -> list[dict[str, str]]:
            if remaining < 0:
                return []
            rows: list[dict[str, str]] = []
            for edge in index.get(symbol, []):
                key = (edge["from_symbol"], edge["to_symbol"])
                if key in seen:
                    continue
                seen.add(key)
                rows.append(edge)
                rows.extend(walk(edge[next_key], remaining - 1))
            return rows

        return walk(target, depth)

    def symbol_detail(self, symbol: str, depth: int = 4) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "node": self.node_by_id.get(symbol),
            "formula": self.formulas.get(symbol),
            "upstream_edges": self.collect_edges(symbol, "upstream", depth),
            "downstream_edges": self.collect_edges(symbol, "downstream", depth),
            "tables_that_output_symbol": [
                row for row in self.table_keys if symbol in row["output_symbols"].split("|")
            ],
            "tables_that_key_symbol": [
                row for row in self.table_keys if symbol in row["key_symbols"].split("|")
            ],
        }

    def graphviz_dot(self, symbol: str, direction: str = "upstream", depth: int = 3) -> str:
        edges = self.collect_edges(symbol, direction, depth)
        lines = ["digraph G {", "rankdir=LR;", 'node [shape=box, style="rounded,filled", fillcolor="#f8fafc"];']
        lines.append(f'"{symbol}" [fillcolor="#dbeafe"];')
        for edge in edges:
            label = f"{edge['edge_type']}\\n{edge['rule_id']}"
            lines.append(f'"{edge["from_symbol"]}" -> "{edge["to_symbol"]}" [label="{label}"];')
        lines.append("}")
        return "\n".join(lines)


DEFAULT_SCENARIO = "sample_write_to_read_diff_bg.json"
USER_METRICS = [
    {"label": "RL", "symbol": "RL", "description": "Read Latency"},
    {"label": "WL", "symbol": "WL", "description": "Write Latency"},
    {"label": "tCK_ns", "symbol": "tCK_ns", "description": "CK period in ns"},
    {"label": "tWCK_ns", "symbol": "tWCK_ns", "description": "WCK period in ns"},
    {"label": "BL/n", "symbol": "BLN", "description": "Effective burst command spacing"},
    {"label": "BL/n_min", "symbol": "BLN_MIN", "description": "Minimum burst data transfer time"},
    {"label": "BL/n_max", "symbol": "BLN_MAX", "description": "Column array cycle limit"},
    {"label": "tWTR_S", "symbol": "tWTR_S_nCK", "description": "Write-to-read different BG timing"},
    {"label": "tWTR_L", "symbol": "tWTR_L_nCK", "description": "Write-to-read same BG timing"},
    {"label": "tRTW", "symbol": "tRTW_FINAL", "description": "Final read-to-write timing used for command decisions"},
    {"label": "WR->RD min (diff BG)", "symbol": "WR_TO_RD_DIFF", "description": "WL + BL/n_min + tWTR_S"},
    {"label": "WR->RD min (same BG)", "symbol": "WR_TO_RD_SAME", "description": "WL + BL/n_max + tWTR_L"},
    {"label": "RD sync-off deadline", "symbol": "R_DEADLINE", "description": "RL + BL/n_min + tWCKPST"},
    {"label": "WR sync-off deadline", "symbol": "W_DEADLINE", "description": "WL + BL/n_min + tWCKPST"},
    {"label": "tWCK2DQO max", "symbol": "tWCK2DQO_EFFECTIVE_MAX_ps", "description": "Selected WCK to DQ output max offset"},
    {"label": "tRPST", "symbol": "tRPST_nCK", "description": "RDQS postamble converted to nCK"},
    {"label": "tWCKPST", "symbol": "tWCKPST_nCK_RD", "description": "WCK postamble converted to nCK"},
    {"label": "tWRWTR", "symbol": "tWRWTR", "description": "Write/training Table398 Note1 guard"},
    {"label": "tRTRRD", "symbol": "tRTRRD", "description": "Read/training Table398 Note3 guard"},
]
METRIC_BY_LABEL = {row["label"]: row for row in USER_METRICS}
METRIC_BY_SYMBOL = {row["symbol"]: row for row in USER_METRICS}

MR1_SPEED_BIN_ROWS = read_csv(DATA / "timing" / "lpddr6_mr1_speed_bins.csv")
MR1_SPEED_TO_RATE = {
    row["mr1_op"]: int(float(row["data_rate_upper_mbps_inclusive"]))
    for row in MR1_SPEED_BIN_ROWS
}
MR1_SEEDED_OPS = [row["mr1_op"] for row in MR1_SPEED_BIN_ROWS if row["status"] == "seeded"]
MR1_TBD_OPS = [row["mr1_op"] for row in MR1_SPEED_BIN_ROWS if row["status"] != "seeded"]

FORMULA_REGISTRY = read_json(FORMULAS / "lpddr6_formula_registry.json")["expressions"]
NT_ODT_READ_ROWS = read_csv(DATA / "timing" / "lpddr6_nt_odt_read_t331_t336.csv")


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "enabled", "enable", "on", "hf"}


def int_bool(value: Any) -> int:
    return 1 if bool_value(value) else 0


def speed_option(row: dict[str, str]) -> dict[str, Any]:
    upper = int(float(row["data_rate_upper_mbps_inclusive"]))
    lower = int(float(row["data_rate_lower_mbps_exclusive"]))
    label = f"Up to {upper} Mbps  ({lower} < data rate <= {upper})"
    return {
        "value": row["mr1_op"],
        "label": label,
        "data_rate_mbps": upper,
        "status": row["status"],
    }


SPEED_BIN_OPTIONS = [speed_option(row) for row in MR1_SPEED_BIN_ROWS if row["status"] == "seeded"]
SPEED_BY_OP = {row["value"]: row for row in SPEED_BIN_OPTIONS}

TARGET_INPUTS: dict[str, dict[str, Any]] = {
    "speed_bin": {
        "label": "Operating Data Rate",
        "description": "동작 data-rate 범위를 고르면 내부적으로 latency speed row와 CK/WCK 주기가 함께 정해집니다.",
        "kind": "select",
        "default": "01100",
        "options": SPEED_BIN_OPTIONS,
    },
    "bank_relation": {
        "label": "Bank/BG Relation",
        "description": "Same BG 여부가 BL/n_max, tWTR_L/S, tRTW 경로를 바꿉니다.",
        "kind": "select",
        "default": "different_bank_different_bg",
        "options": [
            {"value": "different_bank_different_bg", "label": "Different bank / Different BG"},
            {"value": "different_bank_same_bg", "label": "Different bank / Same BG"},
            {"value": "same_bank_same_bg", "label": "Same bank / Same BG"},
        ],
    },
    "burst_length": {
        "label": "Burst Length",
        "description": "BL24/BL48에 따라 BL/n_min, BL/n_max, ODT latency path가 달라질 수 있습니다.",
        "kind": "select",
        "default": "BL24",
        "options": [{"value": "BL24", "label": "BL24"}, {"value": "BL48", "label": "BL48"}],
    },
    "read_dbi_enabled": {
        "label": "Read DBI",
        "description": "Read DBI enable 여부입니다. RL table 선택에 들어갑니다.",
        "kind": "bool",
        "default": False,
        "mr_effect": "MR3.OP[0]",
    },
    "efficiency_mode_enabled": {
        "label": "Dynamic Efficiency Mode",
        "description": "Dynamic Efficiency Mode enable 여부입니다. Latency/tWTR table 선택에 들어갑니다.",
        "kind": "bool",
        "default": False,
        "mr_effect": "MR1.OP[6]",
    },
    "dvfsl_enabled": {
        "label": "DVFSL",
        "description": "Low-voltage DVFS mode enable 여부입니다.",
        "kind": "bool",
        "default": False,
        "mr_effect": "MR11.OP[4]",
    },
    "write_link_protection_enabled": {
        "label": "Write Link Protection",
        "description": "Write link protection enable 여부입니다. Latency/tWTR selector에 들어갑니다.",
        "kind": "bool",
        "default": False,
        "mr_effect": "MR23.OP[0]",
    },
    "read_link_protection_enabled": {
        "label": "Read Link Protection",
        "description": "Read link protection enable 여부입니다. RL table 선택에 들어갑니다.",
        "kind": "bool",
        "default": False,
        "mr_effect": "MR23.OP[2]",
    },
    "wl_set_b": {
        "label": "Write Latency Set",
        "description": "Write Latency Set A/B 선택입니다. WL lookup column을 바꿉니다.",
        "kind": "select",
        "default": "0",
        "mr_effect": "MR1.OP[5]",
        "options": [{"value": "0", "label": "Set A"}, {"value": "1", "label": "Set B"}],
    },
    "wck_frequency_mode": {
        "label": "WCK Frequency Mode",
        "description": "WCK LF/HF family 선택입니다. WCK2DQ 및 일부 WCK/RDQS 변환 parameter에 사용됩니다.",
        "kind": "select",
        "default": "HF",
        "mr_effect": "MR11.OP[6]",
        "options": [{"value": "HF", "label": "HF"}, {"value": "LF", "label": "LF"}],
    },
    "dq_odt_enabled": {
        "label": "DQ ODT",
        "description": "Target DQ ODT enable 여부입니다. Enabled이면 tRTW ODT-on path를 사용합니다.",
        "kind": "bool",
        "default": False,
        "mr_effect": "MR19.OP[2:0]",
    },
    "dq_nt_odt_enabled": {
        "label": "DQ NT-ODT",
        "description": "Read non-target DQ ODT enable 여부입니다. NT-ODT note path에 영향을 줍니다.",
        "kind": "bool",
        "default": False,
        "mr_effect": "MR20.OP[2:0]",
    },
    "dq_wr_nt_odt_enabled": {
        "label": "DQ WR NT-ODT",
        "description": "Write non-target DQ ODT enable 여부입니다. NT-ODT note path에 영향을 줍니다.",
        "kind": "bool",
        "default": False,
        "mr_effect": "MR20.OP[5:3]",
    },
    "rdqs_enabled": {
        "label": "RDQS",
        "description": "RDQS output enable 여부입니다. Disabled이면 RDQS pre/post timing은 0으로 처리됩니다.",
        "kind": "bool",
        "default": True,
        "mr_effect": "MR22.OP[1:0]",
    },
    "rdqs_ratio": {
        "label": "RDQS Ratio",
        "description": "RDQS 1:1 또는 2:1 ratio 선택입니다. RDQS postamble nCK 변환에 들어갑니다.",
        "kind": "select",
        "default": "1to1",
        "mr_effect": "MR10.OP[1]",
        "options": [{"value": "1to1", "label": "1:1"}, {"value": "2to1", "label": "2:1"}],
    },
    "rdqs_postamble_mode": {
        "label": "RDQS Postamble Mode",
        "description": "RDQS postamble static/toggle 선택입니다.",
        "kind": "select",
        "default": "static",
        "mr_effect": "MR10.OP[5]",
        "options": [{"value": "static", "label": "Static"}, {"value": "toggle", "label": "Toggle"}],
    },
    "rdqs_postamble_length": {
        "label": "RDQS Postamble Length",
        "description": "RDQS postamble 길이입니다.",
        "kind": "select",
        "default": "00",
        "mr_effect": "MR10.OP[7:6]",
        "options": [
            {"value": "00", "label": "0.5 Unit"},
            {"value": "01", "label": "2.5 Unit"},
            {"value": "10", "label": "4.5 Unit"},
        ],
    },
    "wck_postamble_length": {
        "label": "WCK Postamble Length",
        "description": "WCK postamble 길이입니다. WCK Sync-Off deadline에 들어갑니다.",
        "kind": "select",
        "default": "01",
        "mr_effect": "MR22.OP[7:6]",
        "options": [
            {"value": "00", "label": "2.5 tWCK"},
            {"value": "01", "label": "4.5 tWCK"},
            {"value": "10", "label": "6.5 tWCK"},
        ],
    },
    "dfeq_enabled": {
        "label": "DFE Equalization",
        "description": "DFE equalization quantity가 non-zero인 조건입니다. tRTW note +1 조건으로 들어갑니다.",
        "kind": "bool",
        "default": False,
        "mr_effect": "MR70..MR75 DFE quantity",
    },
    "per_pin_dfe_enabled": {
        "label": "Per-pin DFE",
        "description": "Per-pin DFE enable note 조건입니다. tRTW note +1 조건으로 들어갑니다.",
        "kind": "bool",
        "default": False,
        "mr_effect": "MR41.OP[0]",
    },
    "read_nt_odt_target": {
        "label": "Read NT-ODT Target",
        "description": "Read NT-ODT async-on max를 DQ path로 볼지 RDQS path로 볼지 선택합니다.",
        "kind": "select",
        "default": "DQ",
        "options": [{"value": "DQ", "label": "DQ"}, {"value": "RDQS", "label": "RDQS"}],
    },
    "rdqs_preshift_enabled": {
        "label": "RDQS Pre-shift",
        "description": "RDQS를 2 tWCK만큼 early drive하는 pre-shift 조건입니다. 8533 Mbps 초과 고속 영역에서만 허용됩니다.",
        "kind": "bool",
        "default": False,
        "mr_effect": "MR10.OP[0]",
    },
    "rdqs_preamble_group": {
        "label": "RDQS Preamble Group",
        "description": "RDQS preamble 길이 그룹입니다. Read NT-ODT RDQS path selector에 들어갑니다.",
        "kind": "select",
        "default": "000_or_001",
        "mr_effect": "MR10.OP[4:2]",
        "options": [
            {"value": "000_or_001", "label": "4 tWCK total group"},
            {"value": "010_or_011", "label": "8 tWCK total group, >8533 Mbps only"},
        ],
    },
}


FRIENDLY_SYMBOL_META: dict[str, dict[str, str]] = {
    "data_rate_mbps": {
        "label": "Data Rate",
        "description": "Operating data rate. leaf에서 선택한 speed bin의 upper rate를 사용합니다.",
        "formula": "selected Operating Data Rate",
    },
    "ck_mhz": {
        "label": "CK Frequency",
        "description": "LPDDR6 CK frequency",
        "formula": "data_rate_mbps / 4",
    },
    "wck_mhz": {
        "label": "WCK Frequency",
        "description": "LPDDR6 WCK frequency",
        "formula": "data_rate_mbps / 2",
    },
    "tCK_ns": {"label": "tCK", "description": "CK 1 cycle time", "formula": "1000 / CK(MHz)"},
    "tWCK_ns": {"label": "tWCK", "description": "WCK 1 cycle time", "formula": "1000 / WCK(MHz)"},
    "same_bg": {"label": "Same BG", "description": "Bank/BG relation에서 decode한 same BG 여부", "formula": "bank_relation"},
    "same_bank": {"label": "Same Bank", "description": "Bank/BG relation에서 decode한 same bank 여부", "formula": "bank_relation"},
    "RL": {"label": "RL", "description": "Read Latency", "formula": "latency table lookup"},
    "WL": {"label": "WL", "description": "Write Latency", "formula": "latency table lookup + WL Set"},
    "BLN": {"label": "BL/n", "description": "Effective burst command spacing", "formula": "BL/n table lookup"},
    "BLN_MIN": {"label": "BL/n min", "description": "Minimum burst data transfer time", "formula": "BL/n table lookup"},
    "BLN_MAX": {"label": "BL/n max", "description": "Column array cycle limit", "formula": "BL/n table lookup"},
    "tWTR_S_nCK": {"label": "tWTR_S", "description": "Write-to-read different BG timing", "formula": "max(ceil(ns_floor/tCK), nCK_floor)"},
    "tWTR_L_nCK": {"label": "tWTR_L", "description": "Write-to-read same BG timing", "formula": "max(ceil(ns_floor/tCK), nCK_floor)"},
    "tWCK2DQO_EFFECTIVE_MAX_ps": {"label": "tWCK2DQO max", "description": "WCK to DQ output maximum offset", "formula": "WCK2DQ table lookup"},
    "tRPST_nCK": {"label": "tRPST", "description": "RDQS postamble converted to nCK", "formula": "floor(tRPST/tCK)"},
    "tWCKPST_nCK_RD": {"label": "tWCKPST", "description": "WCK postamble converted to nCK", "formula": "floor(tWCKPST/tCK)"},
    "ODTLon": {"label": "ODTLon", "description": "ODT on latency", "formula": "ODT table lookup, often WL based"},
    "tODTon_MIN_nCK_RD": {"label": "tODTon min", "description": "ODT turn-on minimum converted to nCK", "formula": "floor(tODTon_min/tCK)"},
    "tODTon_MAX_ns": {"label": "tODTon max", "description": "DQ ODT turn-on maximum async time", "formula": "ODT async table lookup"},
    "tODTon_MAX_nCK_RU": {"label": "tODTon max", "description": "DQ ODT turn-on maximum converted to nCK guard", "formula": "ceil(tODTon_MAX_ns / tCK)"},
    "tODT_RDon_MAX_ns": {"label": "tODT_RDon max", "description": "Read NT-ODT turn-on maximum async time", "formula": "Read NT-ODT async table lookup"},
    "tODT_RDon_MAX_nCK_RU": {"label": "tODT_RDon max", "description": "Read NT-ODT turn-on maximum converted to nCK guard", "formula": "ceil(tODT_RDon_MAX_ns / tCK)"},
    "dq_odt_effective_enabled": {"label": "DQ ODT Effective", "description": "DQ ODT가 timing path에 실제 적용되는 조건", "formula": "DQ ODT enabled and DVFSQ off"},
    "dq_nt_odt_effective_enabled": {"label": "DQ NT-ODT Effective", "description": "Read non-target ODT가 실제 적용되는 조건", "formula": "DQ NT-ODT enabled and DVFSQ off"},
    "dq_wr_nt_odt_effective_enabled": {"label": "DQ WR NT-ODT Effective", "description": "Write non-target ODT가 실제 적용되는 조건", "formula": "DQ WR NT-ODT enabled and DVFSQ off"},
    "tRTW_BASE": {"label": "tRTW base", "description": "Read-to-write base command gap", "formula": "selected Table389/390 path"},
    "dfeq_enabled": {"label": "DFE Equalization", "description": "DFE equalization quantity non-zero note condition", "formula": "DFE quantity enabled"},
    "per_pin_dfe_enabled": {"label": "Per-pin DFE", "description": "Per-pin DFE note condition", "formula": "per-pin DFE enabled"},
    "tRTW_FINAL": {"label": "tRTW", "description": "Read-to-write final command gap after note adders and even rounding", "formula": "even(tRTW_base + note adders)"},
}


SYMBOL_DEPENDENCIES: dict[str, list[str]] = {
    "data_rate_mbps": ["speed_bin"],
    "ck_mhz": ["data_rate_mbps"],
    "wck_mhz": ["data_rate_mbps"],
    "tCK_ns": ["ck_mhz"],
    "tWCK_ns": ["wck_mhz"],
    "same_bg": ["bank_relation"],
    "same_bank": ["bank_relation"],
    "RL": [
        "speed_bin",
        "read_dbi_enabled",
        "efficiency_mode_enabled",
        "dvfsl_enabled",
        "write_link_protection_enabled",
        "read_link_protection_enabled",
    ],
    "WL": [
        "speed_bin",
        "wl_set_b",
        "read_dbi_enabled",
        "efficiency_mode_enabled",
        "dvfsl_enabled",
        "write_link_protection_enabled",
        "read_link_protection_enabled",
    ],
    "BLN": ["data_rate_mbps", "bank_relation", "burst_length"],
    "BLN_MIN": ["data_rate_mbps", "burst_length"],
    "BLN_MAX": ["data_rate_mbps", "same_bg", "burst_length"],
    "tWTR_S_nCK": ["dvfsl_enabled", "write_link_protection_enabled", "efficiency_mode_enabled", "tCK_ns"],
    "tWTR_L_nCK": ["dvfsl_enabled", "write_link_protection_enabled", "efficiency_mode_enabled", "tCK_ns"],
    "tWCK2DQO_EFFECTIVE_MAX_ps": ["wck_frequency_mode", "dvfsl_enabled", "data_rate_mbps"],
    "tRPST_nCK": ["rdqs_enabled", "rdqs_ratio", "rdqs_postamble_mode", "rdqs_postamble_length", "tCK_ns", "tWCK_ns"],
    "tWCKPST_nCK_RD": ["wck_postamble_length", "tCK_ns", "tWCK_ns"],
    "ODTLon": ["dq_odt_enabled", "WL", "data_rate_mbps"],
    "tODTon_MIN_nCK_RD": ["dq_odt_enabled", "tCK_ns", "data_rate_mbps"],
    "tODTon_MAX_ns": ["dq_odt_enabled", "data_rate_mbps"],
    "tODTon_MAX_nCK_RU": ["tODTon_MAX_ns", "tCK_ns"],
    "tODT_RDon_MAX_ns": ["dq_nt_odt_enabled", "read_nt_odt_target", "rdqs_enabled", "rdqs_preshift_enabled", "rdqs_preamble_group", "data_rate_mbps"],
    "tODT_RDon_MAX_nCK_RU": ["tODT_RDon_MAX_ns", "tCK_ns"],
    "dq_odt_effective_enabled": ["dq_odt_enabled"],
    "dq_nt_odt_effective_enabled": ["dq_nt_odt_enabled"],
    "dq_wr_nt_odt_effective_enabled": ["dq_wr_nt_odt_enabled"],
    "tRTW_BASE": ["RL", "WL", "BLN_MIN", "BLN_MAX", "tWCK2DQO_EFFECTIVE_MAX_ps", "tCK_ns", "dq_odt_enabled", "tRPST_nCK", "ODTLon", "tODTon_MIN_nCK_RD"],
    "tRTW_FINAL": ["tRTW_BASE", "dfeq_enabled", "per_pin_dfe_enabled"],
}


TARGET_SYMBOLS = [
    "tRTRRD",
    "tWRWTR",
    "WR_TO_RD_DIFF",
    "WR_TO_RD_SAME",
    "tRTW_FINAL",
    "RL",
    "WL",
    "BLN_MAX",
    "BLN_MIN",
    "tWTR_S_nCK",
    "tWTR_L_nCK",
    "tWCK2DQO_EFFECTIVE_MAX_ps",
    "ODTLon",
    "tODTon_MIN_nCK_RD",
    "tODTon_MAX_ns",
    "tODTon_MAX_nCK_RU",
    "tODT_RDon_MAX_ns",
    "tODT_RDon_MAX_nCK_RU",
    "tWCKPST_nCK_RD",
    "R_DEADLINE",
    "W_DEADLINE",
    "WFF_TO_RFF_MIN",
]


def default_target_inputs() -> dict[str, Any]:
    return {key: copy.deepcopy(value["default"]) for key, value in TARGET_INPUTS.items()}


def resolve_metric(name: str) -> dict[str, str]:
    if name in METRIC_BY_LABEL:
        return METRIC_BY_LABEL[name]
    if name in METRIC_BY_SYMBOL:
        return METRIC_BY_SYMBOL[name]
    return {"label": name, "symbol": name, "description": name}


def base_scenario() -> dict[str, Any]:
    return read_json(SCENARIOS / DEFAULT_SCENARIO)


def scenario_from_inputs(
    *,
    current_cmd: str,
    next_cmd: str,
    bank_relation: str,
    burst_length: str,
    requested_gap_nck: int,
    ws_operand: int,
    data_rate_mbps: float,
    mr1_op: str,
    wl_set_b: int,
    efficiency: int,
    dvfsl: int,
    write_link: int,
    read_link: int,
) -> dict[str, Any]:
    scenario = copy.deepcopy(base_scenario())
    scenario.update(
        {
            "scenario_id": "ui_query",
            "current_cmd": current_cmd,
            "next_cmd": next_cmd,
            "bank_relation": bank_relation,
            "burst_length": burst_length,
            "requested_gap_nck": int(requested_gap_nck),
            "ws_operand": int(ws_operand),
            "data_rate_mbps": float(data_rate_mbps),
        }
    )
    mr = scenario["MR"]
    mr["MR1.OP[4:0]"] = mr1_op
    mr["MR1.OP[5]"] = int(wl_set_b)
    mr["MR1.OP[6]"] = int(efficiency)
    mr["MR11.OP[4]"] = int(dvfsl)
    if int(dvfsl):
        mr["MR11.OP[6]"] = 0
    mr["MR23.OP[0]"] = int(write_link)
    mr["MR23.OP[1]"] = 0
    mr["MR23.OP[2]"] = int(read_link)
    return scenario


def target_scenario_from_inputs(inputs: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    values = default_target_inputs()
    if inputs:
        for key, value in inputs.items():
            if key in values and value not in (None, ""):
                values[key] = value

    warnings: list[str] = []
    speed_bin = str(values["speed_bin"])
    if speed_bin not in SPEED_BY_OP:
        raise ValueError(f"Unsupported or unseeded operating speed selection: {speed_bin}")
    data_rate = SPEED_BY_OP[speed_bin]["data_rate_mbps"]

    scenario = copy.deepcopy(base_scenario())
    scenario.update(
        {
            "scenario_id": "target_parameter_query",
            "current_cmd": "WR",
            "next_cmd": "RD",
            "bank_relation": str(values["bank_relation"]),
            "burst_length": str(values["burst_length"]),
            "requested_gap_nck": 0,
            "ws_operand": 1,
            "data_rate_mbps": float(data_rate),
        }
    )
    mr = scenario["MR"]
    mr["MR1.OP[4:0]"] = speed_bin
    mr["MR1.OP[5]"] = int(str(values["wl_set_b"]))
    mr["MR1.OP[6]"] = int_bool(values["efficiency_mode_enabled"])
    mr["MR3.OP[0]"] = int_bool(values["read_dbi_enabled"])
    mr["MR11.OP[4]"] = int_bool(values["dvfsl_enabled"])
    mr["MR11.OP[5]"] = 0
    mr["MR11.OP[6]"] = 1 if str(values["wck_frequency_mode"]).upper() == "HF" else 0
    if int_bool(values["dvfsl_enabled"]) and mr["MR11.OP[6]"]:
        warnings.append("DVFSL enabled path uses LF_L timing family in the current seed; WCK Frequency Mode was forced to LF.")
        mr["MR11.OP[6]"] = 0
        values["wck_frequency_mode"] = "LF"
    mr["MR19.OP[2:0]"] = "001" if int_bool(values["dq_odt_enabled"]) else "000"
    mr["MR20.OP[2:0]"] = "001" if int_bool(values["dq_nt_odt_enabled"]) else "000"
    mr["MR20.OP[5:3]"] = "001" if int_bool(values["dq_wr_nt_odt_enabled"]) else "000"
    mr["MR22.OP[1:0]"] = "01" if int_bool(values["rdqs_enabled"]) else "00"
    mr["MR22.OP[7:6]"] = str(values["wck_postamble_length"])
    mr["MR23.OP[0]"] = int_bool(values["write_link_protection_enabled"])
    mr["MR23.OP[1]"] = 0
    mr["MR23.OP[2]"] = int_bool(values["read_link_protection_enabled"])
    mr["MR41.OP[0]"] = int_bool(values["per_pin_dfe_enabled"])
    mr["MR70.OP[2:0]"] = "001" if int_bool(values["dfeq_enabled"]) else "000"
    mr["MR10.OP[1]"] = 0 if str(values["rdqs_ratio"]) == "1to1" else 1
    mr["MR10.OP[0]"] = int_bool(values["rdqs_preshift_enabled"])
    mr["MR10.OP[4:2]"] = "010" if str(values["rdqs_preamble_group"]) == "010_or_011" else "000"
    mr["MR10.OP[5]"] = 0 if str(values["rdqs_postamble_mode"]) == "static" else 1
    mr["MR10.OP[7:6]"] = str(values["rdqs_postamble_length"])
    return scenario, values, warnings


def evaluate_scenario(scenario: dict[str, Any], columns: list[str] | None = None) -> dict[str, Any]:
    out = Evaluator(scenario).run()
    values = out["resolved_values"]
    result = out["result"]
    row: dict[str, Any] = {
        "scenario_id": out.get("scenario_id"),
        "current_cmd": scenario["current_cmd"],
        "next_cmd": scenario["next_cmd"],
        "bank_relation": scenario["bank_relation"],
        "burst_length": scenario["burst_length"],
        "requested_gap_nck": scenario.get("requested_gap_nck"),
        "ws_operand": scenario.get("ws_operand"),
        "data_rate_mbps": scenario["data_rate_mbps"],
        "MR1.OP[4:0]": scenario["MR"].get("MR1.OP[4:0]"),
        "MR1.OP[5]": scenario["MR"].get("MR1.OP[5]"),
        "MR1.OP[6]": scenario["MR"].get("MR1.OP[6]"),
        "MR11.OP[4]": scenario["MR"].get("MR11.OP[4]"),
        "MR23.OP[0]": scenario["MR"].get("MR23.OP[0]"),
        "MR23.OP[2]": scenario["MR"].get("MR23.OP[2]"),
        "result_state": result.get("result_state"),
        "min_nck": result.get("min_nck"),
        "max_nck": result.get("max_nck"),
        "rule_id": result.get("rule_id"),
        "warning_count": len(out["warnings"]),
    }
    for key in columns or []:
        metric = resolve_metric(key)
        row[metric["label"]] = values.get(metric["symbol"])
    row["_trace"] = out["trace"]
    row["_warnings"] = out["warnings"]
    return row


def target_symbol_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    node_rows = {row["symbol_id"]: row for row in read_csv(GRAPH / "lpddr6_symbol_nodes.csv")}
    for symbol in TARGET_SYMBOLS:
        formula = FORMULA_REGISTRY.get(symbol, {})
        node = node_rows.get(symbol, {})
        meta = FRIENDLY_SYMBOL_META.get(symbol, {})
        rows.append(
            {
                "symbol": symbol,
                "label": meta.get("label") or symbol,
                "unit": formula.get("unit") or node.get("unit", ""),
                "description": formula.get("description_ko") or meta.get("description") or node.get("description_ko", ""),
                "formula": meta.get("formula") or formula.get("formula", ""),
                "source": formula.get("source") or node.get("source_ref", ""),
            }
        )
    return rows


def symbol_meta(symbol: str, db: SemanticDB | None = None) -> dict[str, str]:
    formula = FORMULA_REGISTRY.get(symbol, {})
    meta = FRIENDLY_SYMBOL_META.get(symbol, {})
    node = db.node_by_id.get(symbol, {}) if db is not None else {}
    return {
        "label": meta.get("label") or symbol,
        "description": formula.get("description_ko") or meta.get("description") or node.get("description_ko", ""),
        "formula": meta.get("formula") or formula.get("formula", ""),
        "unit": formula.get("unit") or node.get("unit", ""),
        "source": formula.get("source") or node.get("source_ref", ""),
    }


def direct_dependencies(symbol: str, values: dict[str, Any]) -> list[str]:
    if symbol == "tRTW_BASE":
        same_bg = bool(values.get("same_bg"))
        odt = bool(values.get("dq_odt_effective_enabled"))
        deps = ["same_bg", "RL", "BLN_MAX" if same_bg else "BLN_MIN", "tWCK2DQO_EFFECTIVE_MAX_ps", "tCK_ns", "dq_odt_enabled"]
        if odt:
            deps.extend(["tRPST_nCK", "ODTLon", "tODTon_MIN_nCK_RD"])
        else:
            deps.append("WL")
        return deps
    if symbol == "tRTW_FINAL":
        return ["tRTW_BASE", "dfeq_enabled", "per_pin_dfe_enabled"]
    if symbol == "tODT_RDon_MAX_ns":
        deps = ["dq_nt_odt_enabled", "read_nt_odt_target", "data_rate_mbps"]
        if values.get("_read_nt_odt_target") == "RDQS":
            deps.extend(["rdqs_enabled", "rdqs_preshift_enabled", "rdqs_preamble_group"])
        return deps
    if symbol in FORMULA_REGISTRY:
        return list(FORMULA_REGISTRY[symbol].get("dependencies", []))
    return list(SYMBOL_DEPENDENCIES.get(symbol, []))


def format_leaf_value(key: str, inputs: dict[str, Any]) -> str:
    raw = inputs.get(key, TARGET_INPUTS.get(key, {}).get("default"))
    if key == "speed_bin":
        option = SPEED_BY_OP.get(str(raw))
        if option:
            return f"{option['data_rate_mbps']} Mbps"
    if key == "bank_relation":
        labels = {row["value"]: row["label"] for row in TARGET_INPUTS[key]["options"]}
        return labels.get(str(raw), str(raw))
    if key in TARGET_INPUTS and TARGET_INPUTS[key]["kind"] == "bool":
        return "Enabled" if int_bool(raw) else "Disabled"
    if key in TARGET_INPUTS and "options" in TARGET_INPUTS[key]:
        labels = {str(row["value"]): row["label"] for row in TARGET_INPUTS[key]["options"]}
        return labels.get(str(raw), str(raw))
    return str(raw)


def display_value(symbol: str, values: dict[str, Any], inputs: dict[str, Any]) -> Any:
    if symbol in TARGET_INPUTS:
        return format_leaf_value(symbol, inputs)
    if symbol == "dq_odt_enabled":
        return "Enabled" if values.get("dq_odt_effective_enabled") else "Disabled"
    if symbol == "dq_nt_odt_enabled":
        return "Enabled" if values.get("dq_nt_odt_effective_enabled") else "Disabled"
    if symbol == "dq_wr_nt_odt_enabled":
        return "Enabled" if values.get("dq_wr_nt_odt_effective_enabled") else "Disabled"
    value = values.get(symbol)
    if isinstance(value, float):
        return round(value, 6)
    return value


def dependency_tree(
    symbol: str,
    values: dict[str, Any],
    inputs: dict[str, Any],
    db: SemanticDB | None = None,
    path: tuple[str, ...] = (),
) -> dict[str, Any]:
    if symbol in TARGET_INPUTS:
        entry = TARGET_INPUTS[symbol]
        return {
            "symbol": symbol,
            "label": entry["label"],
            "description": entry.get("description", ""),
            "formula": "user selected leaf input",
            "unit": "",
            "value": display_value(symbol, values, inputs),
            "kind": "leaf",
            "leaf": True,
            "mr_effect": entry.get("mr_effect", ""),
            "children": [],
        }
    if symbol in path:
        return {
            "symbol": symbol,
            "label": symbol,
            "description": "cycle reference",
            "formula": "",
            "unit": "",
            "value": display_value(symbol, values, inputs),
            "kind": "cycle",
            "leaf": False,
            "children": [],
        }

    meta = symbol_meta(symbol, db)
    deps = direct_dependencies(symbol, values)
    return {
        "symbol": symbol,
        "label": meta["label"],
        "description": meta["description"],
        "formula": meta["formula"],
        "unit": meta["unit"],
        "value": display_value(symbol, values, inputs),
        "kind": "parameter",
        "leaf": False,
        "source": meta["source"],
        "children": [dependency_tree(dep, values, inputs, db, path + (symbol,)) for dep in deps],
    }


def collect_required_inputs(node: dict[str, Any]) -> list[str]:
    out: list[str] = []

    def walk(current: dict[str, Any]) -> None:
        if current.get("leaf"):
            out.append(current["symbol"])
        for child in current.get("children", []):
            walk(child)

    walk(node)
    seen: set[str] = set()
    ordered: list[str] = []
    for key in out:
        if key not in seen:
            seen.add(key)
            ordered.append(key)
    return ordered


def input_specs(input_keys: list[str], values: dict[str, Any]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for key in input_keys:
        spec = copy.deepcopy(TARGET_INPUTS[key])
        spec["id"] = key
        spec["value"] = values.get(key, spec.get("default"))
        spec["display_value"] = format_leaf_value(key, values)
        specs.append(spec)
    return specs


def enrich_target_values(values: dict[str, Any], inputs: dict[str, Any], warnings: list[str]) -> None:
    tck = values.get("tCK_ns")
    if tck and "tODTon_MAX_ns" in values:
        values["tODTon_MAX_nCK_RU"] = math.ceil(float(values["tODTon_MAX_ns"]) / float(tck))

    target = str(inputs.get("read_nt_odt_target", "DQ"))
    values["_read_nt_odt_target"] = target
    if not values.get("dq_nt_odt_effective_enabled"):
        return

    data_rate = float(values["data_rate_mbps"])
    ck_mhz = float(values["ck_mhz"])
    rdqs_ps = "1" if int_bool(inputs.get("rdqs_preshift_enabled")) else "0"
    pre_group = str(inputs.get("rdqs_preamble_group", "000_or_001"))
    rows = []
    for row in NT_ODT_READ_ROWS:
        if row["target"] != target:
            continue
        if not (float(row["ck_lower_mhz_exclusive"]) < ck_mhz <= float(row["ck_upper_mhz_inclusive"])):
            continue
        if data_rate > float(row["data_rate_upper_mbps"]):
            continue
        if target == "RDQS":
            if not values.get("rdqs_enabled"):
                continue
            if row["rdqs_ps"] != rdqs_ps:
                continue
            if row["rdqs_pre_group"] != pre_group:
                continue
        rows.append(row)
    if not rows:
        warnings.append(
            "No seeded Read NT-ODT async-on row for "
            f"target={target}, data_rate={data_rate:g}, ck={ck_mhz:g}, rdqs_ps={rdqs_ps}, pre_group={pre_group}."
        )
        return
    row = rows[0]
    if row["status"] != "seeded":
        warnings.append(f"Read NT-ODT async-on row is {row['status']} for {target} at {data_rate:g} Mbps.")
        return
    values["tODT_RDon_MIN_ns"] = float(row["async_on_min_ns"])
    values["tODT_RDon_MAX_ns"] = float(row["async_on_max_ns"])
    if tck:
        values["tODT_RDon_MAX_nCK_RU"] = math.ceil(float(row["async_on_max_ns"]) / float(tck))
    values["tODT_RDon_source"] = row["source_table"]


def evaluate_target_parameter(
    target: str,
    inputs: dict[str, Any] | None = None,
    db: SemanticDB | None = None,
) -> dict[str, Any]:
    if target not in TARGET_SYMBOLS and target not in FORMULA_REGISTRY and target not in FRIENDLY_SYMBOL_META:
        raise ValueError(f"Unsupported target symbol: {target}")
    scenario, leaf_values, leaf_warnings = target_scenario_from_inputs(inputs)
    evaluator = Evaluator(scenario)
    out = evaluator.run()
    values = out["resolved_values"]
    warnings = leaf_warnings + out["warnings"]
    enrich_target_values(values, leaf_values, warnings)
    formula_result: dict[str, Any] | None = None
    if target in FORMULA_REGISTRY and target not in values:
        formula_result = evaluator.resolve_registered_formula(target)
        values = evaluator.values
    elif target in FORMULA_REGISTRY:
        formula_result = {
            "state": "numeric",
            "value": values.get(target),
            "formula": FORMULA_REGISTRY[target].get("formula", ""),
            "inputs": evaluator.formula_inputs(FORMULA_REGISTRY[target].get("dependencies", [])),
            "rounding": "already resolved",
        }

    root = dependency_tree(target, values, leaf_values, db)
    required = collect_required_inputs(root)
    meta = symbol_meta(target, db)
    return {
        "target": {
            "symbol": target,
            "label": meta["label"],
            "description": meta["description"],
            "formula": meta["formula"],
            "unit": meta["unit"],
            "source": meta["source"],
            "value": display_value(target, values, leaf_values),
        },
        "inputs": input_specs(required, leaf_values),
        "input_values": leaf_values,
        "tree": root,
        "formula_result": formula_result,
        "scenario_mr": scenario["MR"],
        "warnings": warnings,
        "trace": out["trace"],
    }


def run_sweep(
    *,
    current_cmd: str,
    next_cmd: str,
    bank_relation: str,
    burst_length: str,
    requested_gap_nck: int,
    ws_operand: int,
    mr1_ops: list[str],
    data_rates: list[float] | None,
    match_mr1_speed_bin: bool,
    wl_set_b_values: list[int],
    efficiency_values: list[int],
    dvfsl_values: list[int],
    write_link_values: list[int],
    read_link_values: list[int],
    output_symbols: list[str],
    max_rows: int = 500,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    explicit_rates = data_rates or [9600]
    combos = product(
        mr1_ops,
        wl_set_b_values,
        efficiency_values,
        dvfsl_values,
        write_link_values,
        read_link_values,
    )
    for mr1_op, wl_set_b, efficiency, dvfsl, write_link, read_link in combos:
        rates = [MR1_SPEED_TO_RATE.get(mr1_op, explicit_rates[0])] if match_mr1_speed_bin else explicit_rates
        for data_rate in rates:
            if len(rows) >= max_rows:
                errors.append(f"Row limit {max_rows} reached; narrow the sweep.")
                return rows, errors
            scenario = scenario_from_inputs(
                current_cmd=current_cmd,
                next_cmd=next_cmd,
                bank_relation=bank_relation,
                burst_length=burst_length,
                requested_gap_nck=requested_gap_nck,
                ws_operand=ws_operand,
                data_rate_mbps=data_rate,
                mr1_op=mr1_op,
                wl_set_b=wl_set_b,
                efficiency=efficiency,
                dvfsl=dvfsl,
                write_link=write_link,
                read_link=read_link,
            )
            try:
                rows.append(evaluate_scenario(scenario, output_symbols))
            except Exception as exc:
                errors.append(f"{mr1_op}@{data_rate:g}: {exc}")
    return rows, errors
