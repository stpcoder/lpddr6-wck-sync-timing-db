#!/usr/bin/env python3
"""Audit semantic target leaves and shared dependency conventions."""

from __future__ import annotations

import csv
import re
from pathlib import Path

from semantic_query import TARGET_INPUTS, evaluate_target_parameter


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


RAW_UI_RE = re.compile(r"\bMR\d+|OP\[|speed code|Code \d|[01]{1,3}B")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def flatten_symbols(node: dict) -> list[str]:
    out = [node["symbol"]]
    for child in node.get("children", []):
        out.extend(flatten_symbols(child))
    return out


def audit_visible_leaf_text() -> list[str]:
    errors: list[str] = []
    for key, spec in TARGET_INPUTS.items():
        for field in ("label", "description"):
            text = str(spec.get(field, ""))
            if RAW_UI_RE.search(text):
                errors.append(f"{key}.{field} exposes raw MR wording: {text}")
        for option in spec.get("options", []) or []:
            text = str(option.get("label", ""))
            if RAW_UI_RE.search(text):
                errors.append(f"{key}.option exposes raw MR wording: {text}")
    return errors


def audit_target_map_leaf_keys() -> list[str]:
    errors: list[str] = []
    rows = read_csv(DATA / "timing" / "lpddr6_target_parameter_element_map.csv")
    for row in rows:
        for key in row["basic_leaf_keys"].split("|"):
            if key and key not in TARGET_INPUTS:
                errors.append(f"{row['symbol']} references unknown leaf key {key}")
    return errors


def audit_shared_speed_leaf() -> list[str]:
    errors: list[str] = []
    targets = [
        "RL",
        "WL",
        "tWTR_S_nCK",
        "tWTR_L_nCK",
        "tWCK2DQO_EFFECTIVE_MAX_ps",
        "tWCKPST_nCK_RD",
        "tRTW_FINAL",
        "tRTRRD",
    ]
    for target in targets:
        payload = evaluate_target_parameter(target, {"speed_bin": "01100"})
        input_ids = {row["id"] for row in payload["inputs"]}
        symbols = set(flatten_symbols(payload["tree"]))
        if "speed_bin" not in input_ids:
            errors.append(f"{target} does not expose shared speed_bin leaf")
        if target not in {"RL", "WL"} and not ({"data_rate_mbps", "tCK_ns"} & symbols):
            errors.append(f"{target} tree does not show shared data_rate/tCK path")
    return errors


def audit_note_leaves() -> list[str]:
    errors: list[str] = []
    payload = evaluate_target_parameter("tRTW_FINAL", {"dfeq_enabled": "1", "per_pin_dfe_enabled": "1"})
    input_ids = {row["id"] for row in payload["inputs"]}
    for required in ("dfeq_enabled", "per_pin_dfe_enabled"):
        if required not in input_ids:
            errors.append(f"tRTW_FINAL is missing note leaf {required}")
    if payload["target"]["value"] is None:
        errors.append("tRTW_FINAL note-enabled scenario did not compute a numeric value")
    return errors


def audit_sweep_ui_labels() -> list[str]:
    from semantic_ui_server import HTML

    errors: list[str] = []
    removed_labels = [
        "MR1.OP[4:0] 값",
        "MR1.OP[5] WLS 값",
        "MR1.OP[6] DEFF 값",
        "MR11.OP[4] DVFSL 값",
        "MR23.OP[0] Write Link 값",
        "MR23.OP[2] Read Link 값",
        "MR1.OP[4:0] 기준",
    ]
    required_labels = [
        "Operating Data Rate Rows",
        "Write Latency Set",
        "Dynamic Efficiency Mode",
        "Write Link Protection",
        "Read Link Protection",
    ]
    for label in removed_labels:
        if label in HTML:
            errors.append(f"sweep UI still exposes raw field label: {label}")
    for label in required_labels:
        if label not in HTML:
            errors.append(f"sweep UI is missing semantic label: {label}")
    return errors


def main() -> None:
    errors: list[str] = []
    errors.extend(audit_visible_leaf_text())
    errors.extend(audit_target_map_leaf_keys())
    errors.extend(audit_shared_speed_leaf())
    errors.extend(audit_note_leaves())
    errors.extend(audit_sweep_ui_labels())
    if errors:
        print("target leaf audit failed:")
        for error in errors:
            print(f"  - {error}")
        raise SystemExit(1)
    print("target leaf audit passed")


if __name__ == "__main__":
    main()
