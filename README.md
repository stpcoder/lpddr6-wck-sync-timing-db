# LPDDR6 WCK Sync-Off Timing DB

This repository is a rule-oriented timing database for LPDDR6 tRTW, tWTR,
RDQS/WCK pre/postamble, WCK2DQ, and WCK2CK Sync-Off window calculation.
It is built from plain CSV/JSON rule tables plus a Python evaluator so timing
results can be traced back to MR fields, selected lookup rows, formulas, and
command-pair rules.

No source JEDEC PDF is included in this repository.

## Quick Start

Python 3.11+ is recommended. The core CLI and dependency-free browser UI use
only the Python standard library.

Run the local browser UI:

```bash
python3 tools/semantic_ui_server.py --port 8765
```

Or use the helper script:

```bash
./scripts/run_ui.sh
```

Then open:

```text
http://127.0.0.1:8765
```

Run the seeded validation suite:

```bash
./scripts/validate.sh
```

Run CLI examples:

```bash
./scripts/query_examples.sh
```

Calculate one timing parameter from semantic leaf inputs:

```bash
python3 tools/query_lpddr6_semantic_db.py target tRTRRD \
  --input speed_bin=01100 \
  --input bank_relation=different_bank_different_bg \
  --input burst_length=BL24
```

The target calculator exposes user-facing leaf inputs such as operating data
rate, burst length, Read DBI, Dynamic Efficiency Mode, DVFSL, and link
protection. It maps those leaves to MR/scenario fields internally, then builds
the dependency tree upward through intermediate values such as `RL`,
`BL/n_max`, and `tCK_ns`.

Shared leaves are single keys, not per-formula copies. For example,
`speed_bin` produces one `data_rate_mbps`, which produces one `tCK_ns`.
That same `data_rate_mbps`/`tCK_ns` path is referenced by `RL`, `WL`, `tWTR`,
`tWCK2DQO`, `tRTW`, `tRTRRD`, and WCK Sync-Off deadline formulas.

Optional Streamlit UI dependency:

```bash
python3 -m pip install -r ui/requirements.txt
python3 -m streamlit run ui/streamlit_app.py --server.port 8501
```

## Current Validation

The validation script currently checks two scopes:

- `wr_rd_full`: WR -> RD WCK Sync-Off timing over seeded MR1 speed bins,
  WLS/DEFF/DVFSL/Write Link/Read Link combinations, BL24/BL48, WS0/WS1,
  and same/different BG variants.
- `matrix_baseline`: Table263/Table264 command-pair matrix baseline over
  seeded MR1 speed bins, BL24/BL48, and WS0/WS1.

Latest generated reports are under `reports/`:

- `reports/wck_sync_wr_rd_full.csv`: 3,072 computed rows, 0 errors.
- `reports/wck_sync_matrix_baseline.csv`: 10,752 computed rows, 0 errors.

JEDEC/seed rows marked TBD are intentionally not treated as computable final
numeric paths. In the current seed set, MR1.OP[4:0] `01110`, `01111`, and
`10000` are reported as TBD paths rather than forced numeric outputs.

## Repository Layout

- `data/`: CSV/JSON seed tables, graph tables, formula registry, coverage data.
- `rules/`: normalized timing, note, and illegal-condition rules.
- `scenarios/`: sample evaluator inputs.
- `tools/`: evaluator, semantic query CLI, dependency-free UI server, validation.
- `ui/`: optional Streamlit UI.
- `scripts/`: convenience wrappers for local UI, validation, and examples.
- `docs/`: implementation notes and current design plans.

The key design decision is to avoid one very wide spreadsheet.  Instead, the
database separates:

- scenario inputs
- MR field decoding
- JEDEC lookup tables
- formula rules
- note/adder/override rules
- illegal/not-allowed constraints

The browser UI has two query surfaces:

- Timing Parameter Tree: choose a target such as `tRTRRD` or `WR_TO_RD_DIFF`,
  edit only the required leaf conditions, and inspect the calculated dependency
  tree from leaf inputs to final timing value.
- Command Pair Window: sweep WCK Sync-Off command pairs and compare a requested
  command gap against the computed min/max window.

## Initial Scope

Covered in this draft:

- LPDDR6 normal READ/WRITE command gap calculation
- tRTW rules from Table 389 and Table 390
- tWTR_S/tWTR_L selection from Table 414/416/417/418/419/421/422/423
- BL/n, BL/n_min, BL/n_max table model from Table 381 and Table 382
- MR1 latency table selector model for Table 49 through Table 72
- nWTP/nRTP/nACU timing cross-check tables from Table 268 through Table 281 and Table 415/420
- DQ ODT and write NT-ODT latency/async timing from Table 319/320/329/330
- RDQS pre-shift/preamble/postamble decode from MR10 Table 90
- WCK postamble decode from MR22 Table 117
- WCK2CK Sync AC timing from Table 256 through Table 261
- WCK2CK Sync-Off timing rules from Table 263 and Table 264
- WSOE basic constraints from Table 265 and Table 266
- training transition helper timings `tWRWTR`, `tRTRRD`, and `tMRR` from Table 398 and Table 310
- WCK2DQI/WCK2DQO AC timing and temp/voltage variation coefficients from Table 477
- MR1.OP[4:0] common speed-bin validation against the scenario operating data rate
- note rules such as DFE +1 nCK and per-pin DFE +1 nCK
- illegal/Not Allowed state marking

Not fully populated yet:

- full rank-to-rank timing tables
- vendor-specific TBD values
- full LPDDR5 comparison layer beyond the current ODT write delta seed
- non-timing MR OP value maps outside the current timing-critical seed set
- evaluator validation for all TBD and limited-row MR1 and ODT cases

## Evaluation Order

1. Load scenario.
2. Resolve active FSP using MR13 FSP-OP.
3. Decode MR fields into feature variables.
4. Validate that `data_rate_mbps` is inside the selected MR1.OP[4:0] speed bin.
5. Select MR1 latency table and resolve RL/WL.
6. Resolve BL/n, BL/n_min, and BL/n_max.
7. Resolve tWTR_S or tWTR_L by DVFSL, link protection, efficiency mode, and the actual `tCK_ns`.
8. Resolve tWCK2DQI/O(max), RDQS tRPRE/tRPST, and WCK tWCKPST.
9. Resolve WCK2CK Sync AC values such as tWCKENL and tWCKPRE for the current command.
10. Resolve ODTLon and tODTon(min) when the selected path requires DQ ODT.
11. Select tRTW base formula.
12. Apply note adders and overrides.
13. Apply RU/RD/EVEN rounding.
14. Apply WCK2CK Sync-Off min/max window.
15. Return allowed/illegal/not_allowed/requires_new_ws1 with trace.

## Setup Notes

For Windows, use PowerShell or Git Bash with Python 3.11+:

```powershell
python tools\semantic_ui_server.py --port 8765
python tools\validate_wck_sync_timing_cases.py --scope wr_rd_full
python tools\validate_wck_sync_timing_cases.py --scope matrix_baseline
```

For macOS/Linux, the helper scripts use `python3` by default. Override with:

```bash
PYTHON=/path/to/python ./scripts/validate.sh
```

## Windows-Friendly Implementation

Recommended implementation:

- edit CSV/JSON in Excel or VS Code
- use Python 3.11+ for evaluator
- store queryable cache in SQLite or DuckDB later
- use Streamlit for a local UI after the data model is stable

The files here are intentionally plain CSV and JSON so they can be reviewed
without special tooling.

## MR Database

Mode-register work starts under `data/mr/`.

- `lpddr6_mr_catalog.csv`: MR0 through MR127 address catalog.
- `lpddr6_mr_field_definitions_seed.csv`: seeded OP field definitions with Korean comments.
- `lpddr6_mr_value_map_seed.csv`: seeded OP value meanings and effects.
- `lpddr6_mr_illegal_rules.csv`: illegal/warning combinations such as reserved OP codes, WCK FM/DVFS conflicts, WECC/WEDC mutual exclusion, WSOE/WCK-AON conflict, and DFE RFU bits.

The catalog is complete at address level.  Field/value seeding is intentionally
focused first on timing-relevant MRs and known illegal combinations.

## Timing Database

Timing structure starts under `data/timing/`.

- `lpddr6_timing_parameter_catalog.csv`: symbol-level catalog with units, domains, dependencies, and MR dependencies.
- `lpddr6_unit_conversion_rules.csv`: common unit and rounding rules such as ns-to-nCK, ps-to-nCK, tWCK expression conversion, and EVEN command-gap rounding.
- `lpddr6_rule_dependency_graph.csv`: dependency graph from scenario input to final legality decision.
- `lpddr6_calculation_trace_schema.csv`: required trace columns for explainable calculation output.
- `lpddr6_parse_backlog.csv`: remaining JEDEC parsing backlog by priority.
- `lpddr6_condition_dictionary.csv`: normalized condition keys such as BG relation, DVFS, ODT, WCK FM, WS, RDQS, and DFE.
- `lpddr6_rule_packet_schema.csv`: standard columns for adding lookup/formula/decision rules.
- `lpddr6_target_parameter_element_map.csv`: human-readable target map for
  `tRTRRD`, `RL`, `WL`, `tRTW`, `tWTR`, `tWCK2DQO`, `ODTLon`, `tODTon`, and
  `tODT_RDon` showing leaf keys, shared intermediate symbols, formulas, and
  condition selectors.
- `lpddr6_mr1_speed_bins.csv`: central MR1.OP[4:0] speed-bin map used to validate `data_rate_mbps`.
- `lpddr6_command_gap_rule_packets_seed.csv`: seed command-window rules for RD/WR and WCK Sync-Off decisions.
- `lpddr6_mr1_latency_condition_reference.csv`: MR1 Table47/Table48 condition notes for RL/WL/nWTP/nRTP/nACU lookup.
- `lpddr6_read_latency_nrtp_t268_t272.csv`: nRTP and read latency timing table values by read-link protection and DVFSL.
- `lpddr6_nwtp_t273_t281.csv`: nWTP timing table values and feature conditions.
- `lpddr6_nacu_t415_t420.csv`: nACU timing table values by DVFSL and data rate.
- `lpddr6_write_odt_t319_t320_t329_t330.csv`: DQ ODT and write NT-ODT ODTLon/ODTLoff plus async ODT timing values.
- `lpddr6_nt_odt_read_t331_t336.csv`: NT-ODT read DQ/RDQS latency values and async timing.
- `lpddr6_rdqs_pre_t90.csv`, `lpddr6_rdqs_preshift_t90.csv`, `lpddr6_rdqs_pst_t90.csv`: MR10 RDQS pre/post seed including 1:1 and 2:1 Unit conversion.
- `lpddr6_wck_pst_mr22_t117.csv`: MR22 WCK postamble decode.
- `lpddr6_wck_sync_ac_read_t256_t259.csv`, `lpddr6_wck_sync_ac_write_t260.csv`, `lpddr6_wck_sync_ac_cas_t261.csv`: WCK2CK Sync AC timing seed.
- `lpddr6_wck_sync_off_t263_t266.csv`: WCK Sync-Off and WSOE normalized seed rows.
- `lpddr6_wck_sync_cmd_pair_matrix_t263_t264.csv`: full normalized CMD pair matrix for WR/RD/MRR/WFF/RFF/RDC/meta WCK Sync-Off dispatch.
- `lpddr6_wck2dq_t477_full.csv`: Table477 input/output offset plus temp/voltage variation seed.
- `lp5_lp6_odt_write_compare_seed.csv`: first LPDDR5-vs-LPDDR6 timing delta seed for ODT write behavior.
- `lpddr6_timing_definition_notes.csv`: start/end reference notes for timing symbols.
- `data/graph/lpddr6_symbol_nodes.csv`: node catalog for scenario inputs, MR fields, condition symbols, lookup outputs, and formula outputs.
- `data/graph/lpddr6_dependency_edges.csv`: explicit upstream/downstream dependency edges between timing symbols.
- `data/graph/lpddr6_table_keys.csv`: shared key/output map for the JEDEC-derived CSV tables.
- `data/formulas/lpddr6_formula_registry.json`: structured AST formula registry used by the command-pair evaluator.
- `data/coverage/lpddr6_wck_sync_graph_coverage.csv`: current coverage and remaining gaps for the graph-backed timing path.

The evaluator should reject or warn on any final path that includes `TBD`,
`review`, or unresolved symbols.

## Seed Evaluator

`tools/evaluate_lpddr6_timing_seed.py` is a proof-of-structure evaluator.
It now dispatches the seeded Table263/Table264 command-pair matrix and returns
numeric, open, not-allowed, or unresolved states with trace output.

Example:

```bash
python3 tools/evaluate_lpddr6_timing_seed.py scenarios/sample_read_to_write_same_bg.json
```

The output includes resolved values and trace rows showing source table,
condition hit, formula, rounding, and final decision.

Dependency inspection:

```bash
python3 tools/inspect_lpddr6_graph.py WR_TO_RD_DIFF
```

## Semantic UI

Dependency-free browser UI:

```bash
python3 tools/semantic_ui_server.py --port 8765
```

The optional Streamlit UI is under `ui/`.

Install:

```bash
python3 -m pip install -r ui/requirements.txt
```

Run:

```bash
python3 -m streamlit run ui/streamlit_app.py --server.port 8501
```

The same query backend is available without Streamlit:

```bash
python3 tools/query_lpddr6_semantic_db.py detail WR_TO_RD_DIFF
python3 tools/query_lpddr6_semantic_db.py sweep --match-mr1-speed-bin
```

The query UI uses user-facing metric names such as `tRTW`, `tWTR_S`, and
`WR->RD min (diff BG)`. Internal symbols such as `tRTW_FINAL` and
`tRTW_BASE` remain available in graph/trace views for debug.
