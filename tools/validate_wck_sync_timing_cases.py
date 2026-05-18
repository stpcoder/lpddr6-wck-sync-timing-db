#!/usr/bin/env python3
"""Validate seeded LPDDR6 WCK Sync-Off timing combinations."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

from semantic_query import MR1_SEEDED_OPS, MR1_SPEED_TO_RATE, MR1_TBD_OPS, run_sweep


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REPORTS = ROOT / "reports"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    rows = [{key: value for key, value in row.items() if not key.startswith("_")} for row in rows]
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def bank_relations(scope: str) -> list[str]:
    if scope == "diff_bg":
        return ["different_bank_different_bg"]
    if scope == "same_bg":
        return ["different_bank_same_bg", "same_bank_same_bg"]
    return ["different_bank_different_bg", "different_bank_same_bg", "same_bank_same_bg"]


def legal_mr1_ops_for_dvfsl(dvfsl: int) -> list[str]:
    if not dvfsl:
        return MR1_SEEDED_OPS
    return [op for op in MR1_SEEDED_OPS if MR1_SPEED_TO_RATE[op] <= 1600]


def validate_wr_rd_full() -> tuple[list[dict[str, Any]], list[str]]:
    rows_out: list[dict[str, Any]] = []
    errors: list[str] = []
    outputs = ["RL", "WL", "tWTR_S", "tWTR_L", "WR->RD min (diff BG)", "WR->RD min (same BG)", "tRTW"]
    for bank in bank_relations("any"):
        for burst in ["BL24", "BL48"]:
            for ws in [0, 1]:
                for dvfsl in [0, 1]:
                    rows, row_errors = run_sweep(
                        current_cmd="WR",
                        next_cmd="RD",
                        bank_relation=bank,
                        burst_length=burst,
                        requested_gap_nck=24,
                        ws_operand=ws,
                        mr1_ops=legal_mr1_ops_for_dvfsl(dvfsl),
                        data_rates=[],
                        match_mr1_speed_bin=True,
                        wl_set_b_values=[0, 1],
                        efficiency_values=[0, 1],
                        dvfsl_values=[dvfsl],
                        write_link_values=[0, 1],
                        read_link_values=[0, 1],
                        output_symbols=outputs,
                        max_rows=100000,
                    )
                    errors.extend(
                        f"WR->RD {bank} {burst} WS={ws} DVFSL={dvfsl}: {err}"
                        for err in row_errors
                    )
                    for row in rows:
                        expected_key = (
                            "WR->RD min (diff BG)"
                            if row["bank_relation"] == "different_bank_different_bg"
                            else "WR->RD min (same BG)"
                        )
                        expected = row.get(expected_key)
                        if row["ws_operand"] == 1 and row["min_nck"] != expected:
                            errors.append(
                                "WR->RD min mismatch: "
                                f"{row['bank_relation']} {row['burst_length']} "
                                f"MR1={row['MR1.OP[4:0]']} WLS={row['MR1.OP[5]']} "
                                f"DEFF={row['MR1.OP[6]']} DVFSL={row['MR11.OP[4]']} "
                                f"WRL={row['MR23.OP[0]']} RDL={row['MR23.OP[2]']} "
                                f"min_nck={row['min_nck']} expected={expected}"
                            )
                        rows_out.append(row)
    return rows_out, errors


def validate_matrix_baseline() -> tuple[list[dict[str, Any]], list[str]]:
    rows_out: list[dict[str, Any]] = []
    errors: list[str] = []
    command_rows = read_csv(DATA / "timing" / "lpddr6_wck_sync_cmd_pair_matrix_t263_t264.csv")
    outputs = ["RL", "WL", "tWTR_S", "tWTR_L", "tRTW", "RD sync-off deadline", "WR sync-off deadline"]
    for command_row in command_rows:
        for bank in bank_relations(command_row["bank_scope"]):
            for burst in ["BL24", "BL48"]:
                for ws in [0, 1]:
                    rows, row_errors = run_sweep(
                        current_cmd=command_row["current_cmd"],
                        next_cmd=command_row["next_cmd"],
                        bank_relation=bank,
                        burst_length=burst,
                        requested_gap_nck=24,
                        ws_operand=ws,
                        mr1_ops=MR1_SEEDED_OPS,
                        data_rates=[],
                        match_mr1_speed_bin=True,
                        wl_set_b_values=[0],
                        efficiency_values=[0],
                        dvfsl_values=[0],
                        write_link_values=[0],
                        read_link_values=[0],
                        output_symbols=outputs,
                        max_rows=100000,
                    )
                    errors.extend(
                        f"{command_row['rule_id']} {bank} {burst} WS={ws}: {err}"
                        for err in row_errors
                    )
                    rows_out.extend(rows)
    return rows_out, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=["wr_rd_full", "matrix_baseline"], default="wr_rd_full")
    parser.add_argument("--report", default="")
    args = parser.parse_args()

    if args.scope == "wr_rd_full":
        rows, errors = validate_wr_rd_full()
    else:
        rows, errors = validate_matrix_baseline()

    report = Path(args.report) if args.report else REPORTS / f"wck_sync_{args.scope}.csv"
    write_csv(report, rows)

    print(f"scope={args.scope}")
    print(f"seeded_mr1_ops={','.join(MR1_SEEDED_OPS)}")
    print(f"tbd_mr1_ops={','.join(MR1_TBD_OPS)}")
    print(f"rows={len(rows)}")
    print(f"errors={len(errors)}")
    print(f"report={report}")
    for error in errors[:30]:
        print(f"ERROR: {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
