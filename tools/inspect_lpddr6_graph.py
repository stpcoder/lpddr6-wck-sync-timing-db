#!/usr/bin/env python3
"""Inspect the seeded LPDDR6 timing dependency graph.

The graph CSVs are intentionally simple. This tool answers the practical
question: "If I care about this target symbol, which upstream symbols and
formula dependencies can change it?"
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "data" / "graph"
FORMULAS = ROOT / "data" / "formulas"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_upstream(edges: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    upstream: dict[str, list[dict[str, str]]] = defaultdict(list)
    for edge in edges:
        upstream[edge["to_symbol"]].append(edge)
    return upstream


def collect_upstream(
    upstream: dict[str, list[dict[str, str]]],
    target: str,
    depth: int,
    seen: set[tuple[str, str]],
) -> list[dict[str, str]]:
    if depth < 0:
        return []
    rows: list[dict[str, str]] = []
    for edge in upstream.get(target, []):
        key = (edge["from_symbol"], edge["to_symbol"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(edge)
        rows.extend(collect_upstream(upstream, edge["from_symbol"], depth - 1, seen))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="Target symbol or formula id, for example WR_TO_RD_DIFF")
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = parser.parse_args()

    nodes = {row["symbol_id"]: row for row in read_csv(GRAPH / "lpddr6_symbol_nodes.csv")}
    edges = read_csv(GRAPH / "lpddr6_dependency_edges.csv")
    table_keys = read_csv(GRAPH / "lpddr6_table_keys.csv")
    formulas = read_json(FORMULAS / "lpddr6_formula_registry.json")["expressions"]

    upstream = build_upstream(edges)
    edge_rows = collect_upstream(upstream, args.target, args.depth, set())
    formula = formulas.get(args.target)
    payload = {
        "target": args.target,
        "node": nodes.get(args.target),
        "formula": formula,
        "upstream_edges": edge_rows,
        "tables_that_output_target": [
            row for row in table_keys if args.target in row["output_symbols"].split("|")
        ],
    }

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    print(f"target: {args.target}")
    if payload["node"]:
        print(f"node: {payload['node']['kind']} {payload['node']['unit']} - {payload['node']['description_ko']}")
    if formula:
        print(f"formula: {formula['formula']}")
        print("formula_dependencies: " + ", ".join(formula.get("dependencies", [])))
    if payload["tables_that_output_target"]:
        print("tables:")
        for row in payload["tables_that_output_target"]:
            print(f"  - {row['table_id']}: keys={row['key_symbols']} outputs={row['output_symbols']}")
    print("upstream_edges:")
    for edge in edge_rows:
        print(
            "  - "
            f"{edge['from_symbol']} -> {edge['to_symbol']} "
            f"[{edge['edge_type']}:{edge['rule_id']}] "
            f"{edge['description_ko']}"
        )


if __name__ == "__main__":
    main()
