#!/usr/bin/env python3
"""Streamlit UI for the LPDDR6 semantic timing DB."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

try:
    import streamlit as st
except ModuleNotFoundError as exc:  # pragma: no cover - user-facing startup guard
    raise SystemExit(
        "Streamlit is not installed. Install UI dependencies with:\n"
        "  python3 -m pip install -r ui/requirements.txt\n"
        "Then run:\n"
        "  python3 -m streamlit run ui/streamlit_app.py"
    ) from exc

from semantic_query import SemanticDB, USER_METRICS, evaluate_scenario, run_sweep, scenario_from_inputs


st.set_page_config(page_title="LPDDR6 Timing Semantic DB", layout="wide")
MR1_OPTIONS = [
    "00000",
    "00001",
    "00010",
    "00011",
    "00100",
    "00101",
    "00110",
    "00111",
    "01000",
    "01001",
    "01010",
    "01011",
    "01100",
    "01101",
]


@st.cache_data(show_spinner=False)
def load_db() -> SemanticDB:
    return SemanticDB()


def visible_row(row: dict) -> dict:
    return {k: v for k, v in row.items() if not k.startswith("_")}


def dataframe(rows: list[dict], *, height: int = 360) -> None:
    st.dataframe(pd.DataFrame(rows), use_container_width=True, height=height)


def common_scenario_controls(prefix: str = "") -> dict:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        current_cmd = st.selectbox(f"{prefix}Current CMD", ["WR", "RD", "MRR", "WFF", "RFF", "RDC", "META_WR", "META_RD"], index=0)
        bank_relation = st.selectbox(
            f"{prefix}Bank Relation",
            ["different_bank_different_bg", "different_bank_same_bg", "same_bank_same_bg"],
            index=0,
        )
    with col2:
        next_cmd = st.selectbox(f"{prefix}Next CMD", ["RD", "WR", "MRR", "WFF", "RFF", "RDC", "META_WR", "META_RD", "CAS"], index=0)
        burst_length = st.selectbox(f"{prefix}Burst", ["BL24", "BL48"], index=0)
    with col3:
        requested_gap_nck = st.number_input(f"{prefix}검증할 CMD 간격 (nCK)", min_value=0, max_value=300, value=24, step=2)
        ws_operand = st.selectbox(f"{prefix}WS Operand", [0, 1], index=1)
    with col4:
        data_rate_mbps = st.number_input(f"{prefix}Data Rate 직접 입력 (Mbps)", min_value=80.0, max_value=14400.0, value=9600.0, step=1.0)
        mr1_op = st.selectbox(f"{prefix}MR1.OP[4:0]", MR1_OPTIONS, index=12)

    col5, col6, col7, col8, col9 = st.columns(5)
    with col5:
        wl_set_b = st.selectbox(f"{prefix}MR1.OP[5] WLS", [0, 1], index=0)
    with col6:
        efficiency = st.selectbox(f"{prefix}MR1.OP[6] DEFF", [0, 1], index=0)
    with col7:
        dvfsl = st.selectbox(f"{prefix}MR11.OP[4] DVFSL", [0, 1], index=0)
    with col8:
        write_link = st.selectbox(f"{prefix}MR23.OP[0] Write Link", [0, 1], index=0)
    with col9:
        read_link = st.selectbox(f"{prefix}MR23.OP[2] Read Link", [0, 1], index=0)

    return {
        "current_cmd": current_cmd,
        "next_cmd": next_cmd,
        "bank_relation": bank_relation,
        "burst_length": burst_length,
        "requested_gap_nck": int(requested_gap_nck),
        "ws_operand": int(ws_operand),
        "data_rate_mbps": float(data_rate_mbps),
        "mr1_op": mr1_op,
        "wl_set_b": int(wl_set_b),
        "efficiency": int(efficiency),
        "dvfsl": int(dvfsl),
        "write_link": int(write_link),
        "read_link": int(read_link),
    }


db = load_db()

st.title("LPDDR6 WCK Sync-Off Timing DB")
st.caption("먼저 command pair와 MR/조건 조합을 넣어 timing table을 만들고, Symbol 구성은 계산값의 근거를 추적할 때만 확인합니다.")

tab_query, tab_calc, tab_symbols, tab_graph, tab_coverage = st.tabs(
    ["계산 결과표", "단일 Scenario", "Symbol 구성", "Graph", "DB 구축 현황"]
)

with tab_query:
    st.subheader("계산 결과표")
    st.caption("선택한 MR/조건 값들의 모든 조합을 계산해서 timing 값이 어떻게 바뀌는지 표로 만듭니다. 여러 값을 비교하려면 항목에 여러 값을 선택합니다.")
    output_candidates = [row["label"] for row in USER_METRICS]
    out_cols = st.multiselect("보고 싶은 timing 값", output_candidates, default=["RL", "WL", "tCK_ns", "tWTR_S", "WR->RD min (diff BG)"])
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        q_current = st.selectbox("Current CMD", ["WR", "RD", "MRR", "WFF", "RFF", "RDC", "META_WR", "META_RD"], index=0, key="qcur")
        q_next = st.selectbox("Next CMD", ["RD", "WR", "MRR", "WFF", "RFF", "RDC", "META_WR", "META_RD"], index=0, key="qnxt")
    with col2:
        q_bank = st.selectbox("Bank Relation", ["different_bank_different_bg", "different_bank_same_bg", "same_bank_same_bg"], index=0, key="qbank")
        q_burst = st.selectbox("Burst", ["BL24", "BL48"], index=0, key="qburst")
    with col3:
        q_gap = st.number_input(
            "CMD 간격 입력 (nCK)",
            min_value=0,
            max_value=300,
            value=24,
            step=2,
            key="qgap",
            help="실제로 넣는다고 가정할 command 간격입니다. 결과표의 min_nck보다 작으면 too-early로 판정됩니다.",
        )
        q_ws = st.selectbox("WS Operand", [0, 1], index=1, key="qws", help="WCK sync-off 관련 command operand 조건입니다.")
    with col4:
        q_match = st.checkbox(
            "MR1.OP[4:0] 기준으로 Data Rate 자동 결정",
            value=True,
            help="일반 계산은 MR1.OP[4:0]으로 data rate와 tCK를 자동 선택합니다. 직접 입력은 검증용입니다.",
        )
        q_limit = 500

    q_mr1 = st.multiselect("MR1.OP[4:0]", MR1_OPTIONS, default=["00001"])
    q_rates_text = st.text_input("Data Rate 직접 입력값(Mbps), 자동 결정 해제 시 사용", value="9600")
    q_wls = st.multiselect("MR1.OP[5] WLS 값", [0, 1], default=[0])
    q_eff = st.multiselect("MR1.OP[6] DEFF 값", [0, 1], default=[0, 1])
    q_dvfsl = st.multiselect("DVFSL", [0, 1], default=[0, 1])
    q_wlink = st.multiselect("Write Link", [0, 1], default=[0, 1])
    q_rlink = st.multiselect("Read Link", [0, 1], default=[0])

    if st.button("조건 조합 표 만들기", type="primary"):
        data_rates = [float(x.strip()) for x in q_rates_text.split(",") if x.strip()]
        rows, errors = run_sweep(
            current_cmd=q_current,
            next_cmd=q_next,
            bank_relation=q_bank,
            burst_length=q_burst,
            requested_gap_nck=int(q_gap),
            ws_operand=int(q_ws),
            mr1_ops=q_mr1,
            data_rates=data_rates,
            match_mr1_speed_bin=q_match,
            wl_set_b_values=q_wls,
            efficiency_values=q_eff,
            dvfsl_values=q_dvfsl,
            write_link_values=q_wlink,
            read_link_values=q_rlink,
            output_symbols=out_cols,
            max_rows=int(q_limit),
        )
        public_rows = [visible_row(row) for row in rows]
        st.session_state["query_rows"] = public_rows
        st.session_state["query_errors"] = errors

    if "query_rows" in st.session_state:
        dataframe(st.session_state["query_rows"], height=480)
        if st.session_state.get("query_errors"):
            st.warning("\n".join(st.session_state["query_errors"][:10]))

with tab_calc:
    st.subheader("단일 Scenario 계산")
    controls = common_scenario_controls("Calc ")
    calc_outputs = st.multiselect(
        "보고 싶은 timing 값",
        [row["label"] for row in USER_METRICS],
        default=["RL", "WL", "tCK_ns", "tWTR_S", "tWTR_L", "tRTW"],
    )
    scenario = scenario_from_inputs(**controls)
    if st.button("Evaluate Scenario", type="primary"):
        row = evaluate_scenario(scenario, calc_outputs)
        st.session_state["calc_row"] = row
    if "calc_row" in st.session_state:
        row = st.session_state["calc_row"]
        st.metric("Result", row["result_state"])
        dataframe([visible_row(row)], height=160)
        trace_df = pd.DataFrame(row["_trace"])
        st.markdown("**Trace**")
        st.dataframe(trace_df, use_container_width=True, height=420)
        if row["_warnings"]:
            st.warning("\n".join(row["_warnings"]))

with tab_symbols:
    left, right = st.columns([0.42, 0.58])
    with left:
        search = st.text_input("Search symbol", value="RL")
        kinds = sorted({row["kind"] for row in db.nodes})
        selected_kinds = st.multiselect("Kind filter", kinds, default=[])
        rows = db.symbols(search, selected_kinds)
        dataframe(rows, height=420)
    with right:
        default_symbol = "RL" if "RL" in db.node_by_id else (rows[0]["symbol_id"] if rows else "")
        symbol = st.selectbox("Selected symbol", [row["symbol_id"] for row in db.nodes], index=[row["symbol_id"] for row in db.nodes].index(default_symbol))
        detail = db.symbol_detail(symbol)
        if detail["node"]:
            st.subheader(symbol)
            st.write(detail["node"]["description_ko"])
            st.json({k: v for k, v in detail["node"].items() if k != "description_ko"})
        if detail["formula"]:
            st.markdown("**Formula**")
            st.code(detail["formula"]["formula"])
            dataframe([{"dependency": dep} for dep in detail["formula"].get("dependencies", [])], height=180)
        st.markdown("**구성 요소 Graph**")
        st.caption("MR field, 조건 selector, 단위 변환, 중간 parameter가 선택 심볼을 만드는 경로입니다.")
        dataframe(detail["upstream_edges"], height=320)
        st.markdown("**Tables**")
        dataframe(detail["tables_that_output_symbol"] + detail["tables_that_key_symbol"], height=220)

with tab_graph:
    st.subheader("Symbol Dependency Graph")
    st.caption("Symbol 구성 탭보다 자세한 개발자용 그래프 확인 화면입니다.")
    symbol = st.selectbox("Graph target", [row["symbol_id"] for row in db.nodes], index=[row["symbol_id"] for row in db.nodes].index("WR_TO_RD_DIFF"))
    depth = 4
    graph_left, graph_right = st.columns(2)
    with graph_left:
        st.markdown("**구성 요소: source → selected symbol**")
        st.graphviz_chart(db.graphviz_dot(symbol, "upstream", depth), use_container_width=True)
        dataframe(db.collect_edges(symbol, "upstream", depth), height=320)
    with graph_right:
        st.markdown("**사용처: selected symbol → final timing**")
        st.graphviz_chart(db.graphviz_dot(symbol, "downstream", depth), use_container_width=True)
        dataframe(db.collect_edges(symbol, "downstream", depth), height=320)

with tab_coverage:
    st.subheader("Coverage / Gap Dashboard")
    dataframe(db.coverage, height=260)
    st.markdown("**Formula Registry**")
    dataframe(db.formula_rows(), height=360)
    st.markdown("**Table Key Catalog**")
    dataframe(db.table_keys, height=360)
