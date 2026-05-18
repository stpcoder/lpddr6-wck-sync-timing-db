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
