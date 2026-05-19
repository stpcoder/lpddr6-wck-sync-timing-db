#!/usr/bin/env python3
"""Seed evaluator for the LPDDR6 timing DB draft.

This is intentionally narrow. It proves the table/rule shape by calculating
the currently seeded RD->WR and WR->RD paths with trace output.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RULES = ROOT / "rules"
FORMULAS = DATA / "formulas"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def ru(value: float) -> int:
    return int(math.ceil(value - 1e-12))


def rd(value: float) -> int:
    return int(math.floor(value + 1e-12))


def even(value: int) -> int:
    return value if value % 2 == 0 else value + 1


def enabled(value: Any) -> bool:
    return value in (1, "1", True, "true", "enabled")


def disabled_enabled(value: bool) -> str:
    return "enabled" if value else "disabled"


class Evaluator:
    def __init__(self, scenario: dict[str, Any]):
        self.scenario = scenario
        self.mr = scenario.get("MR", {})
        self.trace: list[dict[str, str]] = []
        self.values: dict[str, Any] = {}
        self.warnings: list[str] = []

        self.lat_selector = read_csv(DATA / "lpddr6_mr1_latency_table_selector.csv")
        self.lat_values = read_csv(DATA / "lpddr6_mr1_latency_values_seed.csv")
        self.bln_rows = read_csv(DATA / "lpddr6_bln_t381_t382.csv")
        self.tccd_rows = read_csv(DATA / "lpddr6_tccd_table382.csv")
        self.twtr_rows = read_csv(DATA / "lpddr6_twtr_core_ac.csv")
        self.wck2dq_rows = read_csv(DATA / "timing" / "lpddr6_wck2dq_t477_full.csv")
        self.nwtp_rows = read_csv(DATA / "timing" / "lpddr6_nwtp_t273_t281.csv")
        self.nrtp_rows = read_csv(DATA / "timing" / "lpddr6_read_latency_nrtp_t268_t272.csv")
        self.nacu_rows = read_csv(DATA / "timing" / "lpddr6_nacu_t415_t420.csv")
        self.mr1_speed_bins = read_csv(DATA / "timing" / "lpddr6_mr1_speed_bins.csv")
        self.write_odt_rows = read_csv(DATA / "timing" / "lpddr6_write_odt_t319_t320_t329_t330.csv")
        self.rdqs_pre_rows = read_csv(DATA / "timing" / "lpddr6_rdqs_pre_t90.csv")
        self.rdqs_preshift_rows = read_csv(DATA / "timing" / "lpddr6_rdqs_preshift_t90.csv")
        self.rdqs_pst_rows = read_csv(DATA / "timing" / "lpddr6_rdqs_pst_t90.csv")
        self.wck_pst_rows = read_csv(DATA / "timing" / "lpddr6_wck_pst_mr22_t117.csv")
        self.wck_sync_read_rows = read_csv(DATA / "timing" / "lpddr6_wck_sync_ac_read_t256_t259.csv")
        self.wck_sync_write_rows = read_csv(DATA / "timing" / "lpddr6_wck_sync_ac_write_t260.csv")
        self.wck_sync_cas_rows = read_csv(DATA / "timing" / "lpddr6_wck_sync_ac_cas_t261.csv")
        self.wck_sync_cmd_pair_rows = read_csv(DATA / "timing" / "lpddr6_wck_sync_cmd_pair_matrix_t263_t264.csv")
        self.trtw_rules = read_json(RULES / "lpddr6_trtw_rules.json")
        self.formula_registry = read_json(FORMULAS / "lpddr6_formula_registry.json")
        self.formulas = self.formula_registry["expressions"]

    def add_trace(
        self,
        stage: str,
        target: str,
        source: str,
        condition: str,
        inputs: str,
        formula: str,
        raw_result: str,
        rounding: str,
        final_value: str,
        severity: str = "info",
        message: str = "",
    ) -> None:
        self.trace.append(
            {
                "trace_id": f"TR-{len(self.trace) + 1:04d}",
                "scenario_id": self.scenario.get("scenario_id", "scenario"),
                "stage": stage,
                "target_symbol": target,
                "source": source,
                "condition_hit": condition,
                "inputs": inputs,
                "raw_formula": formula,
                "unit_conversion": "",
                "raw_result": raw_result,
                "rounding": rounding,
                "final_value": final_value,
                "severity": severity,
                "message_ko": message,
            }
        )

    def derive_clock(self) -> None:
        data_rate = float(self.scenario["data_rate_mbps"])
        ck = data_rate / 4.0
        wck = data_rate / 2.0
        tck = 1000.0 / ck
        twck = 1000.0 / wck
        self.values.update(
            {
                "data_rate_mbps": data_rate,
                "ck_mhz": ck,
                "wck_mhz": wck,
                "tCK_ns": tck,
                "tWCK_ns": twck,
            }
        )
        self.add_trace(
            "derive",
            "tCK_ns|tWCK_ns",
            "clocking",
            "spec==LPDDR6",
            f"data_rate_mbps={data_rate:g}",
            "ck=data_rate/4;wck=data_rate/2;tCK=1000/ck;tWCK=1000/wck",
            f"ck={ck:g}MHz|wck={wck:g}MHz",
            "none",
            f"tCK={tck:.6g}ns|tWCK={twck:.6g}ns",
            message="LPDDR6 clocking rule로 CK/WCK cycle 시간을 계산",
        )

    def derive_conditions(self) -> None:
        bank_relation = self.scenario["bank_relation"]
        same_bg = bank_relation in ("same_bank_same_bg", "different_bank_same_bg")
        same_bank = bank_relation == "same_bank_same_bg"
        read_dbi = enabled(self.mr.get("MR3.OP[0]", 0))
        static_efficiency_only = enabled(self.mr.get("MR0.OP[2]", 0))
        dynamic_efficiency_enabled = enabled(self.mr.get("MR1.OP[6]", 0))
        efficiency = static_efficiency_only or dynamic_efficiency_enabled
        dvfsl = enabled(self.mr.get("MR11.OP[4]", 0))
        dvfsq = enabled(self.mr.get("MR11.OP[5]", 0))
        write_link = enabled(self.mr.get("MR23.OP[0]", 0)) or enabled(self.mr.get("MR23.OP[1]", 0))
        read_link = enabled(self.mr.get("MR23.OP[2]", 0))
        dq_odt_mr = self.mr.get("MR19.OP[2:0]", "000") != "000"
        dq_odt_effective = dq_odt_mr and not dvfsq
        dq_nt_odt_mr = self.mr.get("MR20.OP[2:0]", "000") != "000"
        dq_wr_nt_odt_mr = self.mr.get("MR20.OP[5:3]", "000") != "000"
        dq_nt_odt_effective = dq_nt_odt_mr and not dvfsq
        dq_wr_nt_odt_effective = dq_wr_nt_odt_mr and not dvfsq
        per_pin_dfe = enabled(self.mr.get("MR41.OP[0]", 0))
        dfeq = any(
            str(value).strip().upper().rstrip("B") not in {"0", "00", "000", "0000", ""}
            for key, value in self.mr.items()
            if key.startswith(("MR70.", "MR71.", "MR72.", "MR73.", "MR74.", "MR75."))
        )
        wck_fm = "HF" if enabled(self.mr.get("MR11.OP[6]", 0)) else "LF"
        rdqs_enabled = self.mr.get("MR22.OP[1:0]", "00") != "00"

        self.values.update(
            {
                "same_bg": same_bg,
                "same_bank": same_bank,
                "read_dbi_enabled": read_dbi,
                "static_efficiency_only": static_efficiency_only,
                "dynamic_efficiency_enabled": dynamic_efficiency_enabled,
                "efficiency_mode_enabled": efficiency,
                "dvfsl_enabled": dvfsl,
                "dvfsq_enabled": dvfsq,
                "write_link_protection_enabled": write_link,
                "read_link_protection_enabled": read_link,
                "dq_odt_effective_enabled": dq_odt_effective,
                "dq_nt_odt_effective_enabled": dq_nt_odt_effective,
                "dq_wr_nt_odt_effective_enabled": dq_wr_nt_odt_effective,
                "per_pin_dfe_enabled": per_pin_dfe,
                "dfeq_enabled": dfeq,
                "wck_fm": wck_fm,
                "rdqs_enabled": rdqs_enabled,
            }
        )
        self.add_trace(
            "decode",
            "condition_symbols",
            "MR_decode_rules",
            "scenario MR state",
            f"bank_relation={bank_relation}|MR0.OP2={self.mr.get('MR0.OP[2]', 0)}|MR1.OP6={self.mr.get('MR1.OP[6]', 0)}|MR3.OP0={self.mr.get('MR3.OP[0]')}|MR11.OP4={self.mr.get('MR11.OP[4]')}",
            "decode booleans from MR fields",
            "-",
            "none",
            f"same_bg={same_bg}|read_dbi={read_dbi}|static_eff_only={static_efficiency_only}|dynamic_eff={dynamic_efficiency_enabled}|efficiency={efficiency}|dvfsl={dvfsl}|wck_fm={wck_fm}|dq_odt_effective={dq_odt_effective}|dq_nt_odt_effective={dq_nt_odt_effective}",
            message="scenario와 MR 값을 계산 조건 symbol로 변환",
        )
        if static_efficiency_only and "MR1.OP[6]" in self.mr:
            self.add_trace(
                "validation",
                "efficiency_mode_enabled",
                "Table45_Table47_Note7",
                "MR0.OP[2]=1",
                f"MR0.OP[2]={self.mr.get('MR0.OP[2]')}|MR1.OP[6]={self.mr.get('MR1.OP[6]')}",
                "static efficiency-only device ignores MR1.OP[6]; effective efficiency=true",
                "MR1.OP[6] ignored",
                "none",
                "efficiency_mode_enabled=true",
                "warning",
                "Static Efficiency only device에서는 MR1.OP[6] 값과 무관하게 efficiency 조건을 enabled로 처리",
            )

    def validate_mr1_speed_bin(self) -> None:
        mr1_op = self.mr.get("MR1.OP[4:0]")
        if mr1_op is None:
            msg = "MR1.OP[4:0] is required to select latency and validate the operating speed bin"
            self.warnings.append(msg)
            self.add_trace(
                "validation",
                "MR1_speed_bin",
                "Table49_72_common_speed_bin",
                "MR1.OP[4:0] missing",
                f"data_rate_mbps={self.values['data_rate_mbps']:g}",
                "lookup MR1 speed bin",
                "unresolved",
                "none",
                "unresolved",
                "warning",
                msg,
            )
            return

        row = next((r for r in self.mr1_speed_bins if r["mr1_op"] == mr1_op), None)
        if row is None:
            msg = f"No MR1 speed-bin row for MR1.OP[4:0]={mr1_op}"
            self.warnings.append(msg)
            self.add_trace(
                "validation",
                "MR1_speed_bin",
                "Table49_72_common_speed_bin",
                f"MR1.OP[4:0]={mr1_op}",
                f"data_rate_mbps={self.values['data_rate_mbps']:g}",
                "lookup MR1 speed bin",
                "unresolved",
                "none",
                "unresolved",
                "warning",
                msg,
            )
            return

        lower = float(row["data_rate_lower_mbps_exclusive"])
        upper = float(row["data_rate_upper_mbps_inclusive"])
        data_rate = self.values["data_rate_mbps"]
        in_range = lower < data_rate <= upper
        self.values.update(
            {
                "mr1_speed_bin_lower_mbps_exclusive": lower,
                "mr1_speed_bin_upper_mbps_inclusive": upper,
                "mr1_speed_bin_valid": in_range,
                "mr1_speed_bin_status": row["status"],
            }
        )
        if not in_range:
            msg = (
                f"MR1.OP[4:0]={mr1_op} speed bin requires "
                f"{lower:g}<data_rate_mbps<={upper:g}, but scenario has {data_rate:g}"
            )
            self.warnings.append(msg)
            severity = "warning"
            final = "out_of_range"
        else:
            msg = "MR1.OP[4:0] speed bin and scenario data_rate_mbps are consistent"
            severity = "info"
            final = "in_range"

        self.add_trace(
            "validation",
            "MR1_speed_bin",
            row["source"],
            f"MR1.OP[4:0]={mr1_op}",
            f"data_rate_mbps={data_rate:g}|allowed=({lower:g},{upper:g}]",
            "validate scenario data_rate against MR1 speed bin",
            "ok" if in_range else "mismatch",
            "none",
            final,
            severity,
            msg,
        )
        if not in_range and self.scenario.get("strict_mr1_speed_bin"):
            raise ValueError(msg)

    def select_latency(self) -> None:
        key = {
            "read_dbi": disabled_enabled(self.values["read_dbi_enabled"]),
            "efficiency_mode": disabled_enabled(self.values["efficiency_mode_enabled"]),
            "dvfsl": disabled_enabled(self.values["dvfsl_enabled"]),
            "write_link_protection": disabled_enabled(self.values["write_link_protection_enabled"]),
            "read_link_protection": disabled_enabled(self.values["read_link_protection_enabled"]),
        }
        match = None
        for row in self.lat_selector:
            if all(row[k] == v or row[k] == "any" for k, v in key.items()):
                match = row
                break
        if match is None:
            raise ValueError(f"No MR1 latency selector row for {key}")

        table_id = match["table_id"]
        mr1_op = self.mr["MR1.OP[4:0]"]
        val = next((r for r in self.lat_values if r["table_id"] == table_id and r["mr1_op"] == mr1_op), None)
        if val is None:
            msg = f"{table_id} MR1.OP[4:0]={mr1_op} numeric row is not seeded"
            self.warnings.append(msg)
            raise ValueError(msg)
        if val["status"] != "seeded":
            raise ValueError(f"{table_id} MR1.OP[4:0]={mr1_op} status is {val['status']}")
        numeric_columns = [
            "rl_nck",
            "wl_set_a_nck",
            "wl_set_b_nck",
            "nwtp_nck",
            "nrtp_bl24_nck",
            "nrtp_bl48_nck",
            "nacu_nck",
        ]
        if any(not val[col].isdigit() for col in numeric_columns):
            raise ValueError(f"{table_id} MR1.OP[4:0]={mr1_op} has non-numeric latency values")

        wl_col = "wl_set_b_nck" if enabled(self.mr.get("MR1.OP[5]", 0)) else "wl_set_a_nck"
        wl_set = "SET_B" if enabled(self.mr.get("MR1.OP[5]", 0)) else "SET_A"
        rl = int(val["rl_nck"])
        wl = int(val[wl_col])
        self.values.update(
            {
                "latency_table_id": table_id,
                "rl_set": match["rl_set"],
                "wl_set": wl_set,
                "RL": rl,
                "WL": wl,
                "nWTP": int(val["nwtp_nck"]),
                "nRTP_BL24": int(val["nrtp_bl24_nck"]),
                "nRTP_BL48": int(val["nrtp_bl48_nck"]),
                "nACU": int(val["nacu_nck"]),
            }
        )
        self.add_trace(
            "lookup",
            "RL|WL",
            f"{table_id}",
            "|".join(f"{k}={v}" for k, v in key.items()),
            f"MR1.OP[4:0]={mr1_op}|MR1.OP[5]={self.mr.get('MR1.OP[5]', 0)}",
            "MR1 latency table row",
            f"RL={rl}|WL={wl}",
            "none",
            f"RL={rl}nCK({match['rl_set']})|WL={wl}nCK({wl_set})",
            message="MR1 latency selector로 RL/WL을 선택",
        )
        self.crosscheck_nwtp_nacu()
        self.crosscheck_nrtp()

    def crosscheck_nrtp(self) -> None:
        data_rate = self.values["data_rate_mbps"]
        mr1_op = self.mr["MR1.OP[4:0]"]
        read_link = disabled_enabled(self.values["read_link_protection_enabled"])
        dvfsl = disabled_enabled(self.values["dvfsl_enabled"])
        nrtp_row = next(
            (
                r for r in self.nrtp_rows
                if r["read_link_protection"] == read_link
                and r["dvfsl"] == dvfsl
                and r["mr1_op"] == mr1_op
                and float(r["data_rate_lower_mbps"]) < data_rate <= float(r["data_rate_upper_mbps"])
            ),
            None,
        )
        if nrtp_row is None:
            self.add_trace(
                "validation",
                "nRTP",
                "Table268_272",
                f"read_link={read_link}|dvfsl={dvfsl}|MR1.OP[4:0]={mr1_op}|data_rate={data_rate:g}",
                f"MR1 nRTP_BL24={self.values['nRTP_BL24']}|MR1 nRTP_BL48={self.values['nRTP_BL48']}",
                "lookup nRTP timing table",
                "unresolved",
                "none",
                "unresolved",
                "warning",
                "nRTP timing table row가 없어서 DVFSL limited-row 또는 unsupported speed 조건으로 표시",
            )
            return
        if nrtp_row["status"] != "seeded" or not nrtp_row["nrtp_bl24_nck"].isdigit():
            self.add_trace(
                "validation",
                "nRTP",
                nrtp_row["source_table"],
                f"status={nrtp_row['status']}",
                f"MR1 nRTP_BL24={self.values['nRTP_BL24']}|MR1 nRTP_BL48={self.values['nRTP_BL48']}|timing nRTP_BL24={nrtp_row['nrtp_bl24_nck']}|timing nRTP_BL48={nrtp_row['nrtp_bl48_nck']}",
                "BL/n + RU(1.25/tCK)",
                f"{nrtp_row['nrtp_bl24_nck']}|{nrtp_row['nrtp_bl48_nck']}",
                "TBD propagation",
                "TBD",
                "warning",
                "nRTP timing table이 TBD라 Auto Precharge 계산에서 경고 필요",
            )
            return
        timing_bl24 = int(nrtp_row["nrtp_bl24_nck"])
        timing_bl48 = int(nrtp_row["nrtp_bl48_nck"])
        match = timing_bl24 == self.values["nRTP_BL24"] and timing_bl48 == self.values["nRTP_BL48"]
        self.add_trace(
            "validation",
            "nRTP",
            nrtp_row["source_table"],
            f"read_link={read_link}|dvfsl={dvfsl}|MR1.OP[4:0]={mr1_op}",
            f"MR1 BL24={self.values['nRTP_BL24']}|MR1 BL48={self.values['nRTP_BL48']}|timing BL24={timing_bl24}|timing BL48={timing_bl48}",
            "BL/n + RU(1.25/tCK)",
            f"{timing_bl24}|{timing_bl48}",
            "compare MR1 table vs timing table",
            f"BL24={timing_bl24}nCK|BL48={timing_bl48}nCK",
            "info" if match else "warning",
            "Table268~272 nRTP timing table과 MR1 latency row를 대조",
        )

    def crosscheck_nwtp_nacu(self) -> None:
        data_rate = self.values["data_rate_mbps"]
        mr1_op = self.mr["MR1.OP[4:0]"]
        dvfsl = disabled_enabled(self.values["dvfsl_enabled"])
        write_link = disabled_enabled(self.values["write_link_protection_enabled"])
        efficiency = disabled_enabled(self.values["efficiency_mode_enabled"])

        nwtp_row = next(
            (
                r for r in self.nwtp_rows
                if r["dvfsl"] == dvfsl
                and r["write_link_protection"] == write_link
                and r["efficiency_mode"] == efficiency
                and r["mr1_op"] == mr1_op
                and float(r["data_rate_lower_mbps"]) < data_rate <= float(r["data_rate_upper_mbps"])
            ),
            None,
        )
        if nwtp_row is None:
            self.add_trace(
                "validation",
                "nWTP",
                "Table273_281",
                f"dvfsl={dvfsl}|write_link={write_link}|efficiency={efficiency}|MR1.OP[4:0]={mr1_op}|data_rate={data_rate:g}",
                f"MR1 nWTP={self.values['nWTP']}",
                "lookup nWTP timing table",
                "unresolved",
                "none",
                "unresolved",
                "warning",
                "nWTP timing table row가 없어서 DVFSL limited-row 또는 unsupported speed 조건으로 표시",
            )
        elif nwtp_row["status"] != "seeded" or not nwtp_row["nwtp_nck"].isdigit():
            self.add_trace(
                "validation",
                "nWTP",
                nwtp_row["source_table"],
                f"status={nwtp_row['status']}",
                f"MR1 nWTP={self.values['nWTP']}|timing nWTP={nwtp_row['nwtp_nck']}",
                nwtp_row["formula_floor"],
                nwtp_row["nwtp_nck"],
                "TBD propagation",
                "TBD",
                "warning",
                "nWTP timing table이 TBD라 최종 AP timing 계산에서는 경고 필요",
            )
        else:
            timing_nwtp = int(nwtp_row["nwtp_nck"])
            severity = "info" if timing_nwtp == self.values["nWTP"] else "warning"
            self.add_trace(
                "validation",
                "nWTP",
                nwtp_row["source_table"],
                f"dvfsl={dvfsl}|write_link={write_link}|efficiency={efficiency}|MR1.OP[4:0]={mr1_op}",
                f"MR1 nWTP={self.values['nWTP']}|timing nWTP={timing_nwtp}",
                nwtp_row["formula_floor"],
                str(timing_nwtp),
                "compare MR1 table vs timing table",
                f"{timing_nwtp}nCK",
                severity,
                "Table273~281 nWTP timing table과 MR1 latency row를 대조",
            )

        nacu_row = next(
            (
                r for r in self.nacu_rows
                if r["dvfsl"] == dvfsl
                and float(r["data_rate_lower_mbps"]) < data_rate <= float(r["data_rate_upper_mbps"])
            ),
            None,
        )
        if nacu_row is None:
            raise ValueError(f"No nACU row for dvfsl={dvfsl}, data_rate={data_rate:g}")
        if nacu_row["status"] != "seeded" or not nacu_row["nacu_nck"].isdigit():
            self.add_trace(
                "validation",
                "nACU",
                nacu_row["source_table"],
                f"status={nacu_row['status']}",
                f"MR1 nACU={self.values['nACU']}|timing nACU={nacu_row['nacu_nck']}",
                "RU(tACU/tCK at upper clock frequency)",
                nacu_row["nacu_nck"],
                "TBD propagation",
                "TBD",
                "warning",
                "nACU timing table이 TBD라 tRPab/tRPpb 등 최종 계산에서 경고 필요",
            )
            return
        timing_nacu = int(nacu_row["nacu_nck"])
        severity = "info" if timing_nacu == self.values["nACU"] else "warning"
        self.add_trace(
            "validation",
            "nACU",
            nacu_row["source_table"],
            f"dvfsl={dvfsl}|data_rate={data_rate:g}",
            f"MR1 nACU={self.values['nACU']}|timing nACU={timing_nacu}|tACU={nacu_row['tacu_ns']}ns",
            "RU(tACU/tCK at upper clock frequency)",
            str(timing_nacu),
            "compare MR1 table vs timing table",
            f"{timing_nacu}nCK",
            severity,
            "Table415/420 nACU timing table과 MR1 latency row를 대조",
        )

    def select_bln(self) -> None:
        wck_mhz = self.values["wck_mhz"]
        speed_key = "le_3200_mhz" if wck_mhz <= 3200 else "gt_3200_mhz"
        bank_scope = "same_bg" if self.values["same_bg"] else "different_bg"
        bl = self.scenario["burst_length"]
        row = next(
            r for r in self.bln_rows
            if r["wck_freq_condition"] == speed_key and r["bank_scope"] == bank_scope and r["burst_length"] == bl
        )

        def eval_formula(text: str) -> int:
            if text.isdigit():
                return int(text)
            if "tCCD_L" not in text:
                raise ValueError(f"Unsupported BLN formula: {text}")
            tccd_row = next(
                r for r in self.tccd_rows
                if float(r["data_rate_lower_mbps_exclusive"]) < self.values["data_rate_mbps"] <= float(r["data_rate_upper_mbps_inclusive"])
            )
            col = "bl24_same_bg_bln_nck" if bl == "BL24" else "bl48_same_bg_bln_nck"
            tccd_nck = int(tccd_row[col])
            if text.startswith("max"):
                return max(6, tccd_nck)
            if text.startswith("12+"):
                return 12 + tccd_nck
            raise ValueError(f"Unsupported BLN formula: {text}")

        bln = eval_formula(row["bln_formula"])
        bln_min = eval_formula(row["bln_min_formula"])
        bln_max = eval_formula(row["bln_max_formula"])
        self.values.update({"BLN": bln, "BLN_MIN": bln_min, "BLN_MAX": bln_max})
        severity = "warning" if row["status"] == "review" else "info"
        self.add_trace(
            "lookup",
            "BLN|BLN_MIN|BLN_MAX",
            row["source"],
            f"wck_freq_condition={speed_key}|bank_scope={bank_scope}|burst_length={bl}",
            f"wck_mhz={wck_mhz:g}",
            f"BLN={row['bln_formula']}|BLN_MIN={row['bln_min_formula']}|BLN_MAX={row['bln_max_formula']}",
            f"{bln}|{bln_min}|{bln_max}",
            "formula row",
            f"BLN={bln}nCK|BLN_MIN={bln_min}nCK|BLN_MAX={bln_max}nCK",
            severity=severity,
            message="Table381/382 모델로 BL/n 계열 값을 선택",
        )

    def select_twtr(self) -> None:
        key = {
            "dvfsl": disabled_enabled(self.values["dvfsl_enabled"]),
            "link_protection": disabled_enabled(self.values["write_link_protection_enabled"]),
            "efficiency_mode": disabled_enabled(self.values["efficiency_mode_enabled"]),
        }
        row = next(r for r in self.twtr_rows if all(r[k] == v for k, v in key.items()))
        tck = self.values["tCK_ns"]
        twtr_s = max(ru(float(row["twtr_s_ns_floor"]) / tck), int(row["twtr_s_nck_floor"]))
        twtr_l = max(ru(float(row["twtr_l_ns_floor"]) / tck), int(row["twtr_l_nck_floor"]))
        self.values.update({"tWTR_S_nCK": twtr_s, "tWTR_L_nCK": twtr_l})
        self.add_trace(
            "lookup",
            "tWTR_S_nCK|tWTR_L_nCK",
            row["source_table"],
            "|".join(f"{k}={v}" for k, v in key.items()),
            f"tCK_ns={tck:.6g}",
            "max(RU(ns_floor/tCK_ns);nck_floor)",
            f"S={twtr_s}|L={twtr_l}",
            "RU then max",
            f"tWTR_S={twtr_s}nCK|tWTR_L={twtr_l}nCK",
            message="Core AC table에서 tWTR_S/L을 nCK로 변환",
        )

    def select_wck2dqo(self) -> None:
        wck_fm = self.values["wck_fm"]
        dvfsl = self.values["dvfsl_enabled"]
        dvfs_mode = "dvfsl" if dvfsl else "normal_or_dvfsh_or_dvfsb"
        if wck_fm == "LF" and dvfsl:
            output_family = "tWCK2DQO_LF_L"
            input_family = "tWCK2DQI_LF_L"
        elif wck_fm == "LF":
            output_family = "tWCK2DQO_LF"
            input_family = "tWCK2DQI_LF"
            dvfs_mode = "normal"
        else:
            output_family = "tWCK2DQO_HF"
            input_family = "tWCK2DQI_HF"

        def find_row(group: str, symbol: str) -> dict[str, str] | None:
            return next(
                (
                    r for r in self.wck2dq_rows
                    if r["parameter_group"] == group
                    and r["symbol"] == symbol
                    and r["dvfs_mode"] == dvfs_mode
                    and float(r["data_rate_lower_mbps_exclusive"]) < self.values["data_rate_mbps"] <= float(r["data_rate_upper_mbps_inclusive"])
                ),
                None,
            )

        output_row = find_row("output_offset", output_family)
        input_row = find_row("input_offset", input_family)
        if output_row is None:
            raise ValueError(
                "No tWCK2DQO row for "
                f"family={output_family}, dvfs_mode={dvfs_mode}, "
                f"data_rate={self.values['data_rate_mbps']:g}. "
                "Check WCK FM/DVFS legality such as Table478."
            )
        if input_row is None:
            raise ValueError(
                "No tWCK2DQI row for "
                f"family={input_family}, dvfs_mode={dvfs_mode}, "
                f"data_rate={self.values['data_rate_mbps']:g}. "
                "Check WCK FM/DVFS legality such as Table478."
            )
        for label, row in (("tWCK2DQO", output_row), ("tWCK2DQI", input_row)):
            if row["status"] == "tbd" or row["max_value"] == "TBD":
                raise ValueError(f"{label} is TBD for row {row}")
            if row["status"] == "not_applicable":
                raise ValueError(f"{label} row is not applicable: {row}")

        output_max_ps = float(output_row["max_value"])
        output_min_ps = float(output_row["min_value"])
        input_max_ps = float(input_row["max_value"])
        input_min_ps = float(input_row["min_value"])
        self.values.update(
            {
                "tWCK2DQO_MIN_ps": output_min_ps,
                "tWCK2DQO_MAX_ps": output_max_ps,
                "tWCK2DQO_EFFECTIVE_MAX_ps": output_max_ps,
                "tWCK2DQI_MIN_ps": input_min_ps,
                "tWCK2DQI_MAX_ps": input_max_ps,
            }
        )
        self.add_trace(
            "lookup",
            "tWCK2DQO_MAX_ps",
            output_row["source_table"],
            f"wck_fm={wck_fm}|dvfs_mode={dvfs_mode}|family={output_family}",
            f"data_rate={self.values['data_rate_mbps']:g}",
            "Table477 max_ps",
            f"min={output_min_ps:g}ps|max={output_max_ps:g}ps",
            "none",
            f"{output_max_ps:g}ps",
            message="WCK FM과 DVFS mode로 tWCK2DQO max를 선택",
        )
        self.add_trace(
            "lookup",
            "tWCK2DQI_MAX_ps",
            input_row["source_table"],
            f"wck_fm={wck_fm}|dvfs_mode={dvfs_mode}|family={input_family}",
            f"data_rate={self.values['data_rate_mbps']:g}",
            "Table477 max_ps",
            f"min={input_min_ps:g}ps|max={input_max_ps:g}ps",
            "none",
            f"{input_max_ps:g}ps",
            message="WCK FM과 DVFS mode로 tWCK2DQI max를 선택",
        )

        variation_pairs = [
            ("tWCK2DQO_temp_var", "output_temp_var", output_family.replace("tWCK2DQO", "tWCK2DQO_temp")),
            ("tWCK2DQO_volt_var", "output_volt_var", output_family.replace("tWCK2DQO", "tWCK2DQO_volt")),
            ("tWCK2DQI_temp_var", "input_temp_var", input_family.replace("tWCK2DQI", "tWCK2DQI_temp")),
            ("tWCK2DQI_volt_var", "input_volt_var", input_family.replace("tWCK2DQI", "tWCK2DQI_volt")),
        ]
        selected = []
        for key, group, symbol in variation_pairs:
            row = find_row(group, symbol)
            if row is None or row["status"] != "seeded" or row["max_value"] in ("NA", "TBD"):
                continue
            self.values[key] = f"{row['max_value']}{row['unit']}"
            selected.append(f"{key}={row['max_value']}{row['unit']}")
        if selected:
            self.add_trace(
                "lookup",
                "tWCK2DQ variation coefficients",
                "Table477",
                f"wck_fm={wck_fm}|dvfs_mode={dvfs_mode}",
                f"data_rate={self.values['data_rate_mbps']:g}",
                "select temp/voltage variation coefficients; no scenario delta applied",
                "|".join(selected),
                "none",
                "|".join(selected),
                message="온도/전압 delta 입력이 없으므로 variation 계수만 trace에 남김",
            )

    def eval_wl_formula(self, formula: str) -> int:
        text = formula.replace(" ", "")
        if text == "WL":
            return int(self.values["WL"])
        if text.startswith("WL+"):
            return int(self.values["WL"]) + int(text[3:])
        if text.startswith("WL-"):
            return int(self.values["WL"]) - int(text[3:])
        raise ValueError(f"Unsupported WL formula: {formula}")

    def select_rdqs_pst(self) -> None:
        if not self.values["rdqs_enabled"]:
            self.values.update(
                {
                    "RDQS_PRE_SHIFT_twck": 0.0,
                    "tRPRE_STATIC_twck": 0.0,
                    "tRPRE_TOGGLE_twck": 0.0,
                    "tRPRE_TOTAL_twck": 0.0,
                    "tRPRE_ns": 0.0,
                    "tRPRE_nCK_RU": 0,
                    "tRPST_twck": 0.0,
                    "tRPST_ns": 0.0,
                    "tRPST_nCK_RD": 0,
                }
            )
            self.add_trace(
                "lookup",
                "tRPRE|tRPST",
                "TRTW_RDQS_DISABLED_PREPOST_ZERO",
                "rdqs_enabled=false",
                "MR22.OP[1:0]=00",
                "0",
                "0ns",
                "none",
                "0nCK",
                message="RDQS disabled 조건에서는 RDQS pre/post timing을 0으로 처리",
            )
            return

        ratio = "1" if enabled(self.mr.get("MR10.OP[1]", 0)) else "0"
        pre_shift_code = "1" if enabled(self.mr.get("MR10.OP[0]", 0)) else "0"
        pre_code = self.mr.get("MR10.OP[4:2]", "000")
        pst_mode = "1" if enabled(self.mr.get("MR10.OP[5]", 0)) else "0"
        pst_code = self.mr.get("MR10.OP[7:6]", "00")
        pre_shift_row = next(
            (r for r in self.rdqs_preshift_rows if r["pre_shift_code"] == pre_shift_code),
            None,
        )
        pre_row = next(
            (
                r for r in self.rdqs_pre_rows
                if r["ratio_code"] == ratio and r["pre_code"] == pre_code
            ),
            None,
        )
        pst_row = next(
            (
                r for r in self.rdqs_pst_rows
                if r["ratio_code"] == ratio
                and r["pst_mode_code"] == pst_mode
                and r["pst_code"] == pst_code
            ),
            None,
        )
        if pre_shift_row is None:
            raise ValueError(f"No MR10 RDQS pre-shift row for OP[0]={pre_shift_code}")
        if pre_row is None:
            raise ValueError(f"No MR10 RDQS PRE row for OP[1]={ratio}, OP[4:2]={pre_code}")
        if pst_row is None:
            raise ValueError(f"No MR10 RDQS PST row for OP1={ratio}, OP5={pst_mode}, OP[7:6]={pst_code}")
        if pre_shift_row["status"] == "illegal":
            raise ValueError(f"MR10 RDQS pre-shift illegal row: {pre_shift_row}")
        if pre_row["status"] == "illegal":
            raise ValueError(f"MR10 RDQS PRE illegal/RFU row: {pre_row}")
        if pst_row["status"] == "illegal":
            raise ValueError(f"MR10 RDQS PST reserved/illegal row: {pst_row}")
        data_rate = self.values["data_rate_mbps"]
        if pre_shift_row["data_rate_condition"] == "data_rate_mbps>8533" and data_rate <= 8533:
            raise ValueError(f"MR10.OP[0]=1 RDQS pre-shift requires data_rate_mbps>8533. Got {data_rate:g}")
        if pre_row["data_rate_condition"] == "data_rate_mbps>8533" and data_rate <= 8533:
            raise ValueError(f"MR10.OP[4:2]={pre_code} RDQS PRE requires data_rate_mbps>8533. Got {data_rate:g}")

        pre_shift_twck = float(pre_shift_row["pre_shift_twck"])
        pre_static_twck = float(pre_row["pre_static_twck"])
        pre_toggle_twck = float(pre_row["pre_toggle_twck"])
        pre_total_twck = float(pre_row["pre_total_twck"])
        trpre_ns = pre_total_twck * self.values["tWCK_ns"]
        trpre_ru = ru(trpre_ns / self.values["tCK_ns"])
        trpst_twck = float(pst_row["pst_twck"])
        trpst_ns = trpst_twck * self.values["tWCK_ns"]
        trpst_rd = rd(trpst_ns / self.values["tCK_ns"])
        self.values.update(
            {
                "RDQS_PRE_SHIFT_twck": pre_shift_twck,
                "tRPRE_STATIC_twck": pre_static_twck,
                "tRPRE_TOGGLE_twck": pre_toggle_twck,
                "tRPRE_TOTAL_twck": pre_total_twck,
                "tRPRE_ns": trpre_ns,
                "tRPRE_nCK_RU": trpre_ru,
                "tRPST_twck": trpst_twck,
                "tRPST_ns": trpst_ns,
                "tRPST_nCK_RD": trpst_rd,
            }
        )
        severity = "warning" if "high_speed_only" in pre_row["status"] or "high_speed_only" in pre_shift_row["status"] else "info"
        self.add_trace(
            "lookup",
            "RDQS_PRE_SHIFT|tRPRE",
            f"{pre_shift_row['source_table']}_{pre_row['source_table']}",
            f"rdqs_enabled=true|MR10.OP[0]={pre_shift_code}|MR10.OP[1]={ratio}|MR10.OP[4:2]={pre_code}",
            f"tWCK_ns={self.values['tWCK_ns']:.6g}|tCK_ns={self.values['tCK_ns']:.6g}|data_rate={data_rate:g}",
            "pre_shift_twck; tRPRE=static_twck+toggle_twck",
            f"pre_shift={pre_shift_twck:g}tWCK|static={pre_static_twck:g}tWCK|toggle={pre_toggle_twck:g}tWCK|total={pre_total_twck:g}tWCK",
            f"RU(tRPRE/tCK)={trpre_ru}",
            f"pre_shift={pre_shift_twck:g}tWCK|tRPRE={trpre_ru}nCK_RU",
            severity,
            "MR10 Table90 RDQS pre-shift와 preamble static/toggle 구간을 변환",
        )
        self.add_trace(
            "lookup",
            "tRPST",
            pst_row["source_table"],
            f"rdqs_enabled=true|MR10.OP[1]={ratio}|MR10.OP[5]={pst_mode}|MR10.OP[7:6]={pst_code}",
            f"tWCK_ns={self.values['tWCK_ns']:.6g}|tCK_ns={self.values['tCK_ns']:.6g}",
            f"{pst_row['pst_units']} Unit; Unit={pst_row['unit_twck']}*tWCK; waveform={pst_row['waveform']}",
            f"{trpst_ns:.6g}ns",
            f"RD(tRPST/tCK)={trpst_rd}",
            f"{trpst_rd}nCK",
            "info",
            "MR10 Table90 RDQS postamble을 tRTW 계산용 tRPST로 변환",
        )

    def select_write_odt(self) -> None:
        if not self.values["dq_odt_effective_enabled"]:
            self.add_trace(
                "lookup",
                "ODTLon|tODTon_MIN",
                "Table319_Table320",
                "dq_odt_effective_enabled=false",
                f"MR19.OP[2:0]={self.mr.get('MR19.OP[2:0]', '000')}|dvfsq={self.values['dvfsq_enabled']}",
                "not used",
                "not_applicable",
                "none",
                "not_applicable",
                message="DQ ODT가 effective off라 ODT enabled tRTW parameter lookup을 생략",
            )
            return

        data_rate = self.values["data_rate_mbps"]
        row = next(
            (
                r for r in self.write_odt_rows
                if r["odt_path"] == "DQ_ODT"
                and float(r["ck_lower_mhz_exclusive"]) < self.values["ck_mhz"] <= float(r["ck_upper_mhz_inclusive"])
                and data_rate <= float(r["data_rate_upper_mbps"])
            ),
            None,
        )
        if row is None:
            raise ValueError(f"No DQ ODT row for data_rate={data_rate:g}, ck={self.values['ck_mhz']:g}")
        odtlon = self.eval_wl_formula(row["odtlon_formula"])
        todton_min_ns = float(row["todton_min_ns"])
        todton_rd = rd(todton_min_ns / self.values["tCK_ns"])
        self.values.update(
            {
                "ODTLon": odtlon,
                "ODTLoff_BL24_formula": row["odtloff_bl24_formula"],
                "ODTLoff_BL48_formula": row["odtloff_bl48_formula"],
                "tODTon_MIN_ns": todton_min_ns,
                "tODTon_MIN_nCK_RD": todton_rd,
                "tODTon_MAX_ns": float(row["todton_max_ns"]),
                "tODToff_MIN_ns": float(row["todtoff_min_ns"]),
                "tODToff_MAX_ns": float(row["todtoff_max_ns"]),
            }
        )
        self.add_trace(
            "lookup",
            "ODTLon|tODTon_MIN",
            f"{row['source_table']}_{row['async_table']}",
            f"dq_odt_effective_enabled=true|data_rate<={row['data_rate_upper_mbps']}",
            f"WL={self.values['WL']}|tCK_ns={self.values['tCK_ns']:.6g}|MR19.OP[2:0]={self.mr.get('MR19.OP[2:0]')}",
            f"ODTLon={row['odtlon_formula']}|tODTon_MIN={row['todton_min_ns']}ns",
            f"ODTLon={odtlon}|tODTon_MIN={todton_min_ns:g}ns",
            f"RD(tODTon_MIN/tCK)={todton_rd}",
            f"ODTLon={odtlon}nCK|tODTon_MIN={todton_rd}nCK_RD",
            "info",
            "Table319/320에서 DQ ODT enabled tRTW에 필요한 ODTLon과 tODTon(min)을 선택",
        )

    def select_twckpst(self) -> None:
        code = self.mr.get("MR22.OP[7:6]", "00")
        row = next((r for r in self.wck_pst_rows if r["wck_pst_code"] == code), None)
        if row is None:
            raise ValueError(f"No MR22 WCK PST row for OP[7:6]={code}")
        if row["status"] == "illegal":
            raise ValueError(f"MR22.OP[7:6]={code} is reserved for tWCKPST")
        coeff = float(row["wck_pst_twck"])
        twckpst_ns = coeff * self.values["tWCK_ns"]
        twckpst_rd = rd(twckpst_ns / self.values["tCK_ns"])
        self.values.update(
            {
                "tWCKPST_twck": coeff,
                "tWCKPST_ns": twckpst_ns,
                "tWCKPST_nCK_RD": twckpst_rd,
            }
        )
        self.add_trace(
            "decode",
            "tWCKPST",
            row["source_table"],
            f"MR22.OP[7:6]=={code}",
            f"tWCK_ns={self.values['tWCK_ns']:.6g}",
            f"{coeff}*tWCK",
            f"{twckpst_ns:.6g}ns",
            f"RD(tWCKPST/tCK)={twckpst_rd}",
            f"{twckpst_rd}nCK_RD",
            message="MR22 WCK postamble operand를 시간값으로 변환",
        )
        if self.values.get("rdqs_enabled") and coeff <= float(self.values.get("tRPST_twck", 0.0)):
            msg = (
                "MR22 Table117 Note11 위반 가능성: "
                f"tWCKPST={coeff:g}tWCK <= tRPST={self.values.get('tRPST_twck')}tWCK"
            )
            self.warnings.append(msg)
            self.add_trace(
                "validation",
                "tWCKPST>tRPST",
                "Table117_Note11",
                "rdqs_enabled=true",
                f"tWCKPST={coeff:g}tWCK|tRPST={self.values.get('tRPST_twck')}tWCK",
                "tWCKPST length should be larger than tRPST length",
                "violation" if coeff <= float(self.values.get("tRPST_twck", 0.0)) else "ok",
                "none",
                "warning",
                "warning",
                msg,
            )

    def select_wck_sync_ac(self) -> None:
        cmd = self.scenario["current_cmd"].upper()
        mr1_op = self.mr["MR1.OP[4:0]"]
        data_rate = self.values["data_rate_mbps"]

        def row_for_mr1(rows: list[dict[str, str]], **conditions: str) -> dict[str, str] | None:
            return next(
                (
                    r for r in rows
                    if r["mr1_op"] == mr1_op
                    and all(r[k] == v for k, v in conditions.items())
                    and float(r["data_rate_lower_mbps"]) < data_rate <= float(r["data_rate_upper_mbps"])
                ),
                None,
            )

        def numeric(row: dict[str, str], *columns: str) -> bool:
            return row["status"] == "seeded" and all(row[col].isdigit() for col in columns)

        if cmd.startswith(("RD", "MRR", "RDC", "RFF")):
            read_link = disabled_enabled(self.values["read_link_protection_enabled"])
            dvfsl = disabled_enabled(self.values["dvfsl_enabled"])
            row = row_for_mr1(self.wck_sync_read_rows, read_link_protection=read_link, dvfsl=dvfsl)
            if row is None:
                self.add_trace(
                    "lookup",
                    "tWCKENL_RD|tWCKPRE_RD",
                    "Table256_Table259",
                    f"read_link={read_link}|dvfsl={dvfsl}|MR1.OP[4:0]={mr1_op}|data_rate={data_rate:g}",
                    "current_cmd=" + cmd,
                    "lookup read WCK sync AC table",
                    "unresolved",
                    "none",
                    "unresolved",
                    "warning",
                    "현재 read 계열 command에 맞는 WCK sync AC row가 없음",
                )
                return
            suffix = self.values["rl_set"].lower()
            twckenl_col = f"twckenl_rd_{suffix}_nck"
            rl_col = f"rl_{suffix}_nck"
            cols = [
                twckenl_col,
                "twckpre_static_nck",
                "twckpre_toggle_rd_half_nck",
                "twckpre_toggle_rd_full_nck",
                "twckpre_total_rd_nck",
            ]
            if not numeric(row, *cols):
                self.add_trace(
                    "lookup",
                    "tWCKENL_RD|tWCKPRE_RD",
                    row["source_table"],
                    f"read_link={read_link}|dvfsl={dvfsl}|MR1.OP[4:0]={mr1_op}|rl_set={self.values['rl_set']}",
                    f"row_status={row['status']}|{twckenl_col}={row.get(twckenl_col)}",
                    "read WCK sync AC row",
                    "TBD_or_NA",
                    "propagate warning",
                    "unresolved",
                    "warning",
                    "WCK sync AC read row가 TBD/NA라 계산값으로 확정할 수 없음",
                )
                return
            self.values.update(
                {
                    "wck_sync_ac_source": row["source_table"],
                    "tWCKENL_CURRENT_nCK": int(row[twckenl_col]),
                    "tWCKPRE_STATIC_CURRENT_nCK": int(row["twckpre_static_nck"]),
                    "tWCKPRE_TOGGLE_HALF_CURRENT_nCK": int(row["twckpre_toggle_rd_half_nck"]),
                    "tWCKPRE_TOGGLE_FULL_CURRENT_nCK": int(row["twckpre_toggle_rd_full_nck"]),
                    "tWCKPRE_TOTAL_CURRENT_nCK": int(row["twckpre_total_rd_nck"]),
                }
            )
            severity = "info" if int(row[rl_col]) == self.values["RL"] else "warning"
            self.add_trace(
                "lookup",
                "tWCKENL_RD|tWCKPRE_RD",
                row["source_table"],
                f"current={cmd}|read_link={read_link}|dvfsl={dvfsl}|MR1.OP[4:0]={mr1_op}|rl_set={self.values['rl_set']}",
                f"RL={self.values['RL']}|table_RL={row[rl_col]}|data_rate={data_rate:g}",
                "tWCKPRE_total=tWCKPRE_Static+tWCKPRE_toggle_half+tWCKPRE_toggle_full",
                f"tWCKENL={row[twckenl_col]}|static={row['twckpre_static_nck']}|half={row['twckpre_toggle_rd_half_nck']}|full={row['twckpre_toggle_rd_full_nck']}|total={row['twckpre_total_rd_nck']}",
                "nCK table values",
                f"tWCKENL={row[twckenl_col]}nCK|tWCKPRE_TOTAL={row['twckpre_total_rd_nck']}nCK",
                severity,
                "Table256~259 read WCK2CK Sync AC parameter를 현재 command 기준으로 선택",
            )
            return

        if cmd.startswith(("WR", "MRW", "WFF")):
            row = row_for_mr1(self.wck_sync_write_rows)
            if row is None:
                self.add_trace(
                    "lookup",
                    "tWCKENL_WR|tWCKPRE_WR",
                    "Table260",
                    f"MR1.OP[4:0]={mr1_op}|data_rate={data_rate:g}",
                    "current_cmd=" + cmd,
                    "lookup write WCK sync AC table",
                    "unresolved",
                    "none",
                    "unresolved",
                    "warning",
                    "현재 write 계열 command에 맞는 WCK sync AC row가 없음",
                )
                return
            suffix = self.values["wl_set"].lower()
            twckenl_col = f"twckenl_wr_{suffix}_nck"
            wl_col = f"wl_{suffix}_nck"
            cols = [
                twckenl_col,
                "twckpre_static_nck",
                "twckpre_toggle_wr_half_nck",
                "twckpre_toggle_wr_full_nck",
                "twckpre_total_wr_nck",
            ]
            if not numeric(row, *cols):
                self.add_trace(
                    "lookup",
                    "tWCKENL_WR|tWCKPRE_WR",
                    row["source_table"],
                    f"MR1.OP[4:0]={mr1_op}|wl_set={self.values['wl_set']}",
                    f"row_status={row['status']}|{twckenl_col}={row.get(twckenl_col)}",
                    "write WCK sync AC row",
                    "TBD_or_NA",
                    "propagate warning",
                    "unresolved",
                    "warning",
                    "WCK sync AC write row가 TBD/NA라 계산값으로 확정할 수 없음",
                )
                return
            self.values.update(
                {
                    "wck_sync_ac_source": row["source_table"],
                    "tWCKENL_CURRENT_nCK": int(row[twckenl_col]),
                    "tWCKPRE_STATIC_CURRENT_nCK": int(row["twckpre_static_nck"]),
                    "tWCKPRE_TOGGLE_HALF_CURRENT_nCK": int(row["twckpre_toggle_wr_half_nck"]),
                    "tWCKPRE_TOGGLE_FULL_CURRENT_nCK": int(row["twckpre_toggle_wr_full_nck"]),
                    "tWCKPRE_TOTAL_CURRENT_nCK": int(row["twckpre_total_wr_nck"]),
                }
            )
            severity = "info" if int(row[wl_col]) == self.values["WL"] else "warning"
            self.add_trace(
                "lookup",
                "tWCKENL_WR|tWCKPRE_WR",
                row["source_table"],
                f"current={cmd}|MR1.OP[4:0]={mr1_op}|wl_set={self.values['wl_set']}",
                f"WL={self.values['WL']}|table_WL={row[wl_col]}|data_rate={data_rate:g}",
                "tWCKPRE_total=tWCKPRE_Static+tWCKPRE_toggle_half+tWCKPRE_toggle_full",
                f"tWCKENL={row[twckenl_col]}|static={row['twckpre_static_nck']}|half={row['twckpre_toggle_wr_half_nck']}|full={row['twckpre_toggle_wr_full_nck']}|total={row['twckpre_total_wr_nck']}",
                "nCK table values",
                f"tWCKENL={row[twckenl_col]}nCK|tWCKPRE_TOTAL={row['twckpre_total_wr_nck']}nCK",
                severity,
                "Table260 write WCK2CK Sync AC parameter를 현재 command 기준으로 선택",
            )
            return

        if cmd.startswith("CAS"):
            row = row_for_mr1(self.wck_sync_cas_rows)
            if row is None or not numeric(row, "twckenl_fs_nck", "twckpre_static_nck"):
                self.add_trace(
                    "lookup",
                    "tWCKENL_FS|tWCKPRE_Static_FS",
                    "Table261",
                    f"MR1.OP[4:0]={mr1_op}|data_rate={data_rate:g}",
                    "current_cmd=" + cmd,
                    "lookup CAS WCK sync AC table",
                    "TBD_or_unresolved",
                    "propagate warning",
                    "unresolved",
                    "warning",
                    "CAS WCK sync AC row가 없거나 TBD임",
                )
                return
            self.values.update(
                {
                    "wck_sync_ac_source": row["source_table"],
                    "tWCKENL_CURRENT_nCK": int(row["twckenl_fs_nck"]),
                    "tWCKPRE_STATIC_CURRENT_nCK": int(row["twckpre_static_nck"]),
                    "tWCKPRE_TOGGLE_HALF_CURRENT_nCK": "depends_on_following_command",
                    "tWCKPRE_TOGGLE_FULL_CURRENT_nCK": "depends_on_following_command",
                    "tWCKPRE_TOTAL_CURRENT_nCK": "depends_on_following_command",
                }
            )
            self.add_trace(
                "lookup",
                "tWCKENL_FS|tWCKPRE_Static_FS",
                row["source_table"],
                f"current={cmd}|MR1.OP[4:0]={mr1_op}",
                f"data_rate={data_rate:g}",
                "tWCKPRE_toggle_FS depends on the command following CAS WS=1",
                f"tWCKENL_FS={row['twckenl_fs_nck']}|static={row['twckpre_static_nck']}",
                "nCK table values",
                f"tWCKENL_FS={row['twckenl_fs_nck']}nCK|static={row['twckpre_static_nck']}nCK",
                message="Table261 CAS WCK2CK Sync AC parameter를 선택. toggle은 다음 command 종류로 재해석 필요",
            )
            return

        self.add_trace(
            "lookup",
            "WCK_SYNC_AC",
            "Table256_Table261",
            f"current={cmd}",
            "unsupported command class in seed evaluator",
            "not evaluated",
            "not_applicable",
            "none",
            "not_applicable",
            "warning",
            "현재 seed evaluator는 RD/WR/CAS 계열 WCK Sync AC만 직접 선택",
        )

    def compute_trtw_value(self, same_bg: bool, target_suffix: str = "") -> int:
        odt = self.values["dq_odt_effective_enabled"]
        rule = next(
            r for r in self.trtw_rules["base_rules"]
            if r["conditions"]["same_bg"] == same_bg and r["conditions"]["dq_odt_effective_enabled"] == odt
        )
        bln_key = "BLN_MAX" if same_bg else "BLN_MIN"
        converted = ru((self.values["tWCK2DQO_EFFECTIVE_MAX_ps"] / 1000.0) / self.values["tCK_ns"])
        if odt:
            rpst_rd = self.values["tRPST_nCK_RD"]
            odton_rd = self.values["tODTon_MIN_nCK_RD"]
            base = self.values["RL"] + self.values[bln_key] + converted + rpst_rd - self.values["ODTLon"] - odton_rd + 1
            inputs = (
                f"RL={self.values['RL']}|{bln_key}={self.values[bln_key]}|"
                f"tWCK2DQO={self.values['tWCK2DQO_EFFECTIVE_MAX_ps']}ps|tCK={self.values['tCK_ns']:.6g}|"
                f"tRPST_RD={rpst_rd}|ODTLon={self.values['ODTLon']}|tODTon_MIN_RD={odton_rd}"
            )
            rounding = f"RU(tWCK2DQO/tCK)={converted}|RD(tRPST/tCK)={rpst_rd}|RD(tODTon_MIN/tCK)={odton_rd}"
            message = "Table389/390의 ODT on tRTW base 식 적용"
        else:
            base = self.values["RL"] + self.values[bln_key] + converted - self.values["WL"]
            inputs = (
                f"RL={self.values['RL']}|{bln_key}={self.values[bln_key]}|"
                f"tWCK2DQO={self.values['tWCK2DQO_EFFECTIVE_MAX_ps']}ps|tCK={self.values['tCK_ns']:.6g}|WL={self.values['WL']}"
            )
            rounding = f"RU(tWCK2DQO/tCK)={converted}"
            message = "Table389/390의 ODT off tRTW base 식 적용"
        add = 0
        if self.values["dfeq_enabled"]:
            add += 1
        if self.values["per_pin_dfe_enabled"]:
            add += 1
        final = even(base + add)
        base_key = f"tRTW_BASE{target_suffix}"
        final_key = f"tRTW_FINAL{target_suffix}"
        self.values.update({base_key: base, final_key: final})
        self.add_trace(
            "formula",
            base_key,
            rule["source"],
            f"same_bg={same_bg}|dq_odt_effective_enabled={odt}",
            inputs,
            rule["formula"],
            str(base),
            rounding,
            f"{base}nCK",
            message=message,
        )
        self.add_trace(
            "formula",
            final_key,
            self.trtw_rules["final_formula"]["source"],
            f"dfeq={self.values['dfeq_enabled']}|per_pin_dfe={self.values['per_pin_dfe_enabled']}",
            f"tRTW_BASE={base}|adders={add}",
            self.trtw_rules["final_formula"]["formula"],
            str(base + add),
            f"EVEN({base + add})={final}",
            f"{final}nCK",
            message="DFE note adder와 even rounding 적용",
        )
        return final

    def compute_trtw(self) -> None:
        self.compute_trtw_value(self.values["same_bg"])

    def canonical_cmd(self, raw: str) -> str:
        text = raw.upper().replace("-", "_")
        if text in {"META_WR", "WR_M", "WRITE_META", "META_WRITE"}:
            return "META_WR"
        if text in {"META_RD", "RD_M", "READ_META", "META_READ"}:
            return "META_RD"
        if text.startswith("RDC") or "READ_DQ_CAL" in text:
            return "RDC"
        if text.startswith("RFF") or "READ_FIFO" in text:
            return "RFF"
        if text.startswith("WFF") or "WRITE_FIFO" in text:
            return "WFF"
        if text.startswith("MRR"):
            return "MRR"
        if text.startswith("CAS"):
            return "CAS"
        if text.startswith("WR") or text.startswith("WRITE"):
            return "WR"
        if text.startswith("RD") or text.startswith("READ"):
            return "RD"
        return text

    def bank_scope_key(self) -> str:
        return "same_bg" if self.values["same_bg"] else "diff_bg"

    def select_cmd_pair_rule(self, current_cmd: str, next_cmd: str) -> dict[str, str] | None:
        candidates = [
            r for r in self.wck_sync_cmd_pair_rows
            if r["current_cmd"] == current_cmd and r["next_cmd"] == next_cmd
        ]
        if not candidates:
            return None
        scope = self.bank_scope_key()
        return next((r for r in candidates if r["bank_scope"] == scope), None) or next(
            (r for r in candidates if r["bank_scope"] == "any"),
            None,
        )

    def ensure_trtw_current(self) -> int:
        if "tRTW_FINAL" not in self.values:
            self.compute_trtw()
        return int(self.values["tRTW_FINAL"])

    def ensure_trtw_diff_bg(self) -> int:
        if "tRTW_FINAL_DIFF_BG" not in self.values:
            self.compute_trtw_value(False, "_DIFF_BG")
        return int(self.values["tRTW_FINAL_DIFF_BG"])

    def formula_inputs(self, dependencies: list[str]) -> dict[str, Any]:
        inputs: dict[str, Any] = {}
        for symbol in dependencies:
            if symbol in self.values:
                inputs[symbol] = self.values[symbol]
            elif symbol in self.mr:
                inputs[symbol] = self.mr[symbol]
            else:
                inputs[symbol] = "unresolved_or_not_used_on_this_path"
        return inputs

    def eval_formula_ast(self, node: dict[str, Any]) -> float:
        if "const" in node:
            return node["const"]
        if "symbol" in node:
            symbol = node["symbol"]
            if symbol not in self.values:
                raise KeyError(f"Formula symbol {symbol} has not been resolved")
            return self.values[symbol]

        op = node["op"]
        if op in {"ru", "rd"}:
            value = self.eval_formula_ast(node["arg"])
            return ru(value) if op == "ru" else rd(value)

        args = [self.eval_formula_ast(arg) for arg in node["args"]]
        if op == "add":
            return sum(args)
        if op == "sub":
            if len(args) != 2:
                raise ValueError(f"sub expects two args, got {len(args)}")
            return args[0] - args[1]
        if op == "mul":
            out = 1
            for arg in args:
                out *= arg
            return out
        if op == "div":
            if len(args) != 2:
                raise ValueError(f"div expects two args, got {len(args)}")
            return args[0] / args[1]
        if op == "max":
            return max(args)
        if op == "min":
            return min(args)
        raise ValueError(f"Unsupported formula AST op: {op}")

    def formula_numeric_result(
        self,
        formula_id: str,
        entry: dict[str, Any],
        raw_value: float,
        inputs: dict[str, Any],
        formula_override: str | None = None,
        rounding_override: str | None = None,
    ) -> dict[str, Any]:
        raw_int = int(raw_value)
        rounding_rule = entry.get("rounding", "even_command_gap")
        if rounding_rule == "even_command_gap":
            final = even(raw_int)
            rounding = rounding_override or f"EVEN({raw_int})={final}"
        elif rounding_rule == "none":
            final = raw_int
            rounding = rounding_override or "none"
        else:
            raise ValueError(f"Unsupported rounding rule for {formula_id}: {rounding_rule}")

        formula_text = formula_override or entry["formula"]
        self.values[formula_id] = final
        self.add_trace(
            "formula",
            formula_id,
            entry["source"],
            "formula_registry",
            json.dumps(inputs, ensure_ascii=False, sort_keys=True),
            formula_text,
            str(raw_int),
            rounding,
            f"{final}{entry.get('unit', '')}",
            "info",
            entry.get("description_ko", "formula registry expression 계산"),
        )
        return {
            "state": "numeric",
            "value": final,
            "raw_value": raw_int,
            "formula": formula_text,
            "inputs": inputs,
            "rounding": rounding,
        }

    def resolve_external_formula(self, formula_id: str, entry: dict[str, Any]) -> dict[str, Any]:
        resolver = entry["resolver"]
        inputs = self.formula_inputs(entry.get("dependencies", []))

        if resolver == "tRTW_CURRENT":
            value = self.ensure_trtw_current()
            inputs["tRTW_FINAL"] = value
            return self.formula_numeric_result(formula_id, entry, value, inputs)

        if resolver == "tRTW_DIFF_BG":
            value = self.ensure_trtw_diff_bg()
            inputs["tRTW_FINAL_DIFF_BG"] = value
            return self.formula_numeric_result(formula_id, entry, value, inputs)

        if resolver == "MRR_TO_WR_MIN":
            tck = self.values["tCK_ns"]
            if self.values["dq_odt_effective_enabled"]:
                converted = ru((self.values["tWCK2DQO_EFFECTIVE_MAX_ps"] / 1000.0) / tck)
                odton_rd = self.values.get("tODTon_MIN_nCK_RD")
                if odton_rd is None or "ODTLon" not in self.values:
                    return {
                        "state": "unresolved",
                        "value": None,
                        "formula": "MRR DQ ODT path requires ODTLon and tODTon_MIN",
                        "inputs": inputs,
                        "rounding": "none",
                    }
                value = self.values["RL"] + self.values["BLN_MAX"] + converted - self.values["ODTLon"] - odton_rd + 2
                inputs.update(
                    {
                        "RU_tWCK2DQO_to_nCK": converted,
                        "ODTLon": self.values["ODTLon"],
                        "tODTon_MIN_nCK_RD": odton_rd,
                    }
                )
                return self.formula_numeric_result(
                    formula_id,
                    entry,
                    value,
                    inputs,
                    "RL+BLN_MAX+RU(tWCK2DQO/tCK)-ODTLon-RD(tODTon_MIN/tCK)+2",
                )
            value = self.compute_trtw_value(True, "_MRR_WR_BASE") + 2
            inputs["tRTW_FINAL_same_bg"] = value - 2
            return self.formula_numeric_result(formula_id, entry, value, inputs, "tRTW_FINAL_same_bg+2")

        if resolver == "WFF_TO_RFF_MIN":
            tck = self.values["tCK_ns"]
            nt_odt = self.values["dq_nt_odt_effective_enabled"] or self.values["dq_wr_nt_odt_effective_enabled"]
            base_guard = max(ru(10.0 / tck), 4)
            inputs.update({"nt_odt_effective": nt_odt, "base_guard": base_guard})
            if nt_odt:
                return {
                    "state": "unresolved",
                    "value": None,
                    "formula": "MAX(6nCK,WL+BLN_MAX-RL+RU(tODToff_MAX/tCK)+MAX(RU(10ns/tCK),4nCK))",
                    "inputs": inputs,
                    "rounding": "requires NT-ODT tODToff_MAX lookup",
                }
            value = max(6, self.values["WL"] + self.values["BLN_MAX"] - self.values["RL"] + base_guard)
            return self.formula_numeric_result(
                formula_id,
                entry,
                value,
                inputs,
                "MAX(6nCK,WL+BLN_MAX-RL+MAX(RU(10ns/tCK),4nCK))",
            )

        raise ValueError(f"Unsupported external formula resolver: {resolver}")

    def resolve_registered_formula(self, formula_id: str) -> dict[str, Any]:
        entry = self.formulas[formula_id]
        if "resolver" in entry:
            return self.resolve_external_formula(formula_id, entry)
        raw_value = self.eval_formula_ast(entry["ast"])
        inputs = self.formula_inputs(entry.get("dependencies", []))
        return self.formula_numeric_result(formula_id, entry, raw_value, inputs)

    def resolve_pair_expr(self, expr: str) -> dict[str, Any]:
        if expr == "open":
            return {"state": "open", "value": None, "formula": "open", "inputs": {}, "rounding": "none"}
        if expr == "NOT_ALLOWED":
            return {"state": "not_allowed", "value": None, "formula": "Not Allowed", "inputs": {}, "rounding": "none"}
        if expr in self.formulas:
            return self.resolve_registered_formula(expr)
        return {
            "state": "unresolved",
            "value": None,
            "formula": expr,
            "inputs": {},
            "rounding": "unsupported expression id; add it to data/formulas/lpddr6_formula_registry.json",
        }

    def compute_wsoe_window(self, current_cmd: str, next_cmd: str, gap: int) -> dict[str, Any] | None:
        if next_cmd != "CAS":
            return None
        wsoe = enabled(self.mr.get("MR26.OP[3]", 0))
        ws = enabled(self.scenario.get("ws_operand", 0))
        ws_off = enabled(self.scenario.get("ws_off_operand", 0))
        if not (wsoe and not ws and not ws_off):
            return None
        read_class = current_cmd in {"RD", "META_RD", "MRR", "RFF", "RDC"}
        write_class = current_cmd in {"WR", "META_WR", "WFF"}
        if not (read_class or write_class):
            return None
        min_gap = 2
        max_exclusive = self.values["RL"] if read_class else self.values["WL"]
        state = "allowed_wsoe" if min_gap <= gap < max_exclusive else ("too_early_wsoe" if gap < min_gap else "too_late_wsoe")
        self.add_trace(
            "decision",
            "WSOE_window",
            "Table265_Table266",
            f"current={current_cmd}|next=CAS|MR26.OP[3]=1|WS=0|WS_OFF=0",
            f"requested_gap={gap}|min={min_gap}|max_exclusive={max_exclusive}",
            "2nCK <= gap < WL_or_RL",
            state,
            "none",
            state,
            "info" if state.startswith("allowed") else "warning",
            "CAS WS=0 and WS_OFF=0 WCK Sync-Off Extension acceptable period 판정",
        )
        return {"result_state": state, "min_nck": min_gap, "max_nck": max_exclusive - 1, "max_exclusive_nck": max_exclusive}

    def compute_window(self) -> dict[str, Any]:
        current_cmd = self.canonical_cmd(self.scenario["current_cmd"])
        next_cmd = self.canonical_cmd(self.scenario["next_cmd"])
        gap = int(self.scenario.get("requested_gap_nck", 0))

        wsoe_result = self.compute_wsoe_window(current_cmd, next_cmd, gap)
        if wsoe_result is not None:
            return wsoe_result

        row = self.select_cmd_pair_rule(current_cmd, next_cmd)
        if row is None:
            raise ValueError(f"No WCK Sync-Off command pair row for {current_cmd}->{next_cmd}")

        ws = enabled(self.scenario.get("ws_operand", 0))
        min_expr = row["with_min_expr"] if ws else row["without_min_expr"]
        max_expr = row["with_max_expr"] if ws else row["without_max_expr"]
        min_res = self.resolve_pair_expr(min_expr)
        max_res = self.resolve_pair_expr(max_expr)
        path = "with_new_sync" if ws else "without_new_sync"

        self.add_trace(
            "lookup",
            "command_pair_rule",
            row["source_table"],
            f"current={current_cmd}|next={next_cmd}|bank_scope={row['bank_scope']}|path={path}",
            f"requested_gap={gap}|ws_operand={ws}",
            f"min_expr={min_expr}|max_expr={max_expr}",
            f"min={min_res['state']}:{min_res.get('value')}|max={max_res['state']}:{max_res.get('value')}",
            f"min_round={min_res['rounding']}|max_round={max_res['rounding']}",
            row["rule_id"],
            "info" if row["status"].startswith("seeded") else "warning",
            "Table263/264 command pair matrix에서 현재 CMD->next CMD rule을 선택",
        )

        if min_res["state"] == "not_allowed" or max_res["state"] == "not_allowed":
            state = f"not_allowed_{path}"
            self.add_trace(
                "decision",
                "command_window",
                row["source_table"],
                f"rule={row['rule_id']}|path={path}",
                f"requested_gap={gap}|min_expr={min_expr}|max_expr={max_expr}",
                "selected path contains Not Allowed",
                state,
                "none",
                state,
                "warning",
                "선택된 WS path가 JEDEC table상 Not Allowed",
            )
            return {"result_state": state, "min_nck": None, "max_nck": None, "rule_id": row["rule_id"]}

        if min_res["state"] == "unresolved" or max_res["state"] == "unresolved":
            state = "unresolved_parameter"
            self.add_trace(
                "decision",
                "command_window",
                row["source_table"],
                f"rule={row['rule_id']}|path={path}",
                f"min={min_res['formula']}|max={max_res['formula']}",
                "TBD or not-yet-seeded parameter blocks final decision",
                state,
                "none",
                state,
                "warning",
                "필요 parameter가 아직 seed되지 않아 최종 allowed 판정 불가",
            )
            return {"result_state": state, "min_nck": None, "max_nck": None, "rule_id": row["rule_id"]}

        min_gap = min_res["value"] if min_res["state"] == "numeric" else None
        max_gap = max_res["value"] if max_res["state"] == "numeric" else None
        if min_gap is not None and gap < min_gap:
            state = f"too_early_{path}"
        elif max_gap is not None and gap > max_gap:
            state = "requires_new_ws1_after_sync_off" if not ws else f"too_late_{path}"
        else:
            state = f"allowed_{path}"

        max_text = "open" if max_gap is None else str(max_gap)
        self.add_trace(
            "decision",
            "command_window",
            row["source_table"],
            f"rule={row['rule_id']}|path={path}",
            f"requested_gap={gap}|min={min_gap}|max={max_text}",
            "min<=gap<=max_or_open",
            state,
            "none",
            state,
            "info" if state.startswith("allowed") else "warning",
            "WCK Sync-Off command window 최종 판정",
        )
        return {"result_state": state, "min_nck": min_gap, "max_nck": max_gap, "rule_id": row["rule_id"]}

    def run(self) -> dict[str, Any]:
        self.derive_clock()
        self.derive_conditions()
        self.validate_mr1_speed_bin()
        self.select_latency()
        self.select_bln()
        self.select_twtr()
        self.select_wck2dqo()
        self.select_rdqs_pst()
        self.select_twckpst()
        self.select_wck_sync_ac()
        self.select_write_odt()
        if "tRTW_FINAL" not in self.values:
            self.compute_trtw()
        result = self.compute_window()
        return {
            "scenario_id": self.scenario.get("scenario_id"),
            "result": result,
            "resolved_values": self.values,
            "warnings": self.warnings,
            "trace": self.trace,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", type=Path)
    parser.add_argument("--trace-only", action="store_true")
    args = parser.parse_args()

    scenario = read_json(args.scenario)
    output = Evaluator(scenario).run()
    if args.trace_only:
        print(json.dumps(output["trace"], indent=2, ensure_ascii=False))
    else:
        print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
