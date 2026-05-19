#!/usr/bin/env python3
"""CLI query surface for the LPDDR6 semantic timing DB."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from semantic_query import SemanticDB, TARGET_INPUTS, USER_METRICS, evaluate_target_parameter, run_sweep, write_csv


def parse_csv_list(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def parse_float_list(text: str) -> list[float]:
    return [float(item.strip()) for item in text.split(",") if item.strip()]


def parse_int_list(text: str) -> list[int]:
    return [int(item.strip()) for item in text.split(",") if item.strip()]


def input_display_value(spec: dict) -> str:
    if "display_value" in spec:
        return str(spec["display_value"])
    value = str(spec.get("value", ""))
    for option in spec.get("options", []) or []:
        if str(option.get("value")) == value:
            return str(option.get("label", value))
    if spec.get("kind") == "bool":
        return "Enabled" if value.lower() in {"1", "true", "enabled"} else "Disabled"
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    symbols = sub.add_parser("symbols")
    symbols.add_argument("--search", default="")
    symbols.add_argument("--kind", action="append", default=[])
    symbols.add_argument("--json", action="store_true")

    detail = sub.add_parser("detail")
    detail.add_argument("symbol")
    detail.add_argument("--depth", type=int, default=4)
    detail.add_argument("--json", action="store_true")

    target = sub.add_parser("target")
    target.add_argument("symbol", nargs="?", default="tRTRRD")
    target.add_argument("--input", action="append", default=[], help="Leaf input as key=value, for example speed_bin=01100")
    target.add_argument("--json", action="store_true")

    sweep = sub.add_parser("sweep")
    sweep.add_argument("--current-cmd", default="WR")
    sweep.add_argument("--next-cmd", default="RD")
    sweep.add_argument("--bank-relation", default="different_bank_different_bg")
    sweep.add_argument("--burst-length", default="BL24")
    sweep.add_argument("--gap", type=int, default=24)
    sweep.add_argument("--ws", type=int, default=1)
    sweep.add_argument("--mr1", default="00001")
    sweep.add_argument("--data-rate", default="9600")
    sweep.add_argument("--match-mr1-speed-bin", action="store_true")
    sweep.add_argument("--wl-set-b", default="0")
    sweep.add_argument("--efficiency", default="0,1")
    sweep.add_argument("--dvfsl", default="0,1")
    sweep.add_argument("--write-link", default="0,1")
    sweep.add_argument("--read-link", default="0")
    sweep.add_argument(
        "--outputs",
        default="RL,WL,tCK_ns,tWTR_S,tWTR_L,BL/n_min,BL/n_max,WR->RD min (diff BG),WR->RD min (same BG),tRTW",
        help="Comma-separated user-facing metric labels. Common labels: "
        + ", ".join(row["label"] for row in USER_METRICS),
    )
    sweep.add_argument("--max-rows", type=int, default=500)
    sweep.add_argument("--out")
    sweep.add_argument("--json", action="store_true")

    args = parser.parse_args()
    db = SemanticDB()

    if args.cmd == "symbols":
        rows = db.symbols(args.search, args.kind)
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
        else:
            for row in rows:
                print(f"{row['symbol_id']}\t{row['kind']}\t{row['unit']}\t{row['description_ko']}")
        return

    if args.cmd == "detail":
        payload = db.symbol_detail(args.symbol, args.depth)
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"symbol: {args.symbol}")
            if payload["node"]:
                node = payload["node"]
                print(f"node: {node['kind']} {node['unit']} {node['description_ko']}")
            if payload["formula"]:
                formula = payload["formula"]
                print(f"formula: {formula['formula']}")
                print("dependencies: " + ", ".join(formula.get("dependencies", [])))
            print("upstream:")
            for edge in payload["upstream_edges"]:
                print(f"  {edge['from_symbol']} -> {edge['to_symbol']} [{edge['edge_type']}:{edge['rule_id']}]")
        return

    if args.cmd == "target":
        inputs = {}
        for item in args.input:
            if "=" not in item:
                raise SystemExit(f"Invalid --input {item!r}; use key=value")
            key, value = item.split("=", 1)
            if key not in TARGET_INPUTS:
                raise SystemExit(f"Unknown target input {key!r}. Valid keys: {', '.join(TARGET_INPUTS)}")
            inputs[key] = value
        payload = evaluate_target_parameter(args.symbol, inputs, db)
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            target_row = payload["target"]
            print(f"{target_row['symbol']} = {target_row['value']} {target_row['unit']}".rstrip())
            print(f"formula: {target_row['formula']}")
            print("required leaf inputs:")
            for spec in payload["inputs"]:
                print(f"  - {spec['id']}: {input_display_value(spec)} ({spec['label']})")
            if payload["warnings"]:
                print("warnings:")
                for warning in payload["warnings"]:
                    print(f"  - {warning}")
        return

    rows, errors = run_sweep(
        current_cmd=args.current_cmd,
        next_cmd=args.next_cmd,
        bank_relation=args.bank_relation,
        burst_length=args.burst_length,
        requested_gap_nck=args.gap,
        ws_operand=args.ws,
        mr1_ops=parse_csv_list(args.mr1),
        data_rates=parse_float_list(args.data_rate),
        match_mr1_speed_bin=args.match_mr1_speed_bin,
        wl_set_b_values=parse_int_list(args.wl_set_b),
        efficiency_values=parse_int_list(args.efficiency),
        dvfsl_values=parse_int_list(args.dvfsl),
        write_link_values=parse_int_list(args.write_link),
        read_link_values=parse_int_list(args.read_link),
        output_symbols=parse_csv_list(args.outputs),
        max_rows=args.max_rows,
    )
    public_rows = [{k: v for k, v in row.items() if not k.startswith("_")} for row in rows]
    if args.out:
        write_csv(Path(args.out), public_rows)
    if args.json:
        print(json.dumps({"rows": public_rows, "errors": errors}, indent=2, ensure_ascii=False))
    else:
        if public_rows:
            headers = list(public_rows[0].keys())
            print("\t".join(headers))
            for row in public_rows:
                print("\t".join("" if row.get(h) is None else str(row.get(h)) for h in headers))
        if errors:
            print("errors:")
            for error in errors:
                print(f"  - {error}")


if __name__ == "__main__":
    main()
