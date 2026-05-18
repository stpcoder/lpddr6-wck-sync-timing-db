# Graph Rule Engine Architecture

이 draft의 목표는 JEDEC timing을 flat spreadsheet가 아니라 symbol graph로 계산하는 것이다.

## Layer

1. `symbol_nodes`
   - 가장 작은 입력/조건/계산값 단위.
   - 예: `MR1.OP[4:0]`, `data_rate_mbps`, `dvfsl_enabled`, `RL`, `WL`, `tWTR_S_nCK`, `WR_TO_RD_DIFF`.

2. `dependency_edges`
   - 어떤 symbol이 어떤 symbol을 바꾸는지 표현한다.
   - 예: `MR11.OP[4] -> dvfsl_enabled -> tWTR_S_nCK -> WR_TO_RD_DIFF`.

3. `table_keys`
   - JEDEC table CSV가 어떤 key를 받고 어떤 output symbol을 내는지 정의한다.
   - 같은 key symbol이 여러 table에서 공유되도록 만드는 layer다.

4. `formula_registry`
   - command-pair matrix에 들어가는 식을 문자열이 아니라 AST로 저장한다.
   - 예: `WR_TO_RD_DIFF = WL + BLN_MIN + tWTR_S_nCK`.

5. `evaluator trace`
   - 실제 scenario에서 어떤 table row와 formula가 hit되었는지 남긴다.

## Current Executable Path

현재 evaluator가 registry 기반으로 계산하는 path:

1. `data_rate_mbps -> tCK_ns`
2. `MR fields -> condition symbols`
3. `MR1.OP[4:0] + data_rate_mbps -> MR1_speed_bin validation`
4. MR1 selector/value table -> `RL`, `WL`
5. BL/n tables -> `BLN`, `BLN_MIN`, `BLN_MAX`
6. tWTR table -> `tWTR_S_nCK`, `tWTR_L_nCK`
7. WCK/RDQS/ODT/tRTW helper lookup
8. Table263/264 command pair matrix -> formula id
9. `formula_registry` AST/external resolver -> min/max gap
10. requested gap -> final `result_state`

## Example

`WR_TO_RD_DIFF`는 다음 의존성을 갖는다.

```text
MR1.OP[4:0] -> latency_table_id -> WL
MR11.OP[4] -> dvfsl_enabled -> tWTR_S_nCK
MR23.OP[0/1] -> write_link_protection_enabled -> tWTR_S_nCK
MR1.OP[6] or MR0.OP[2] -> efficiency_mode_enabled -> tWTR_S_nCK
data_rate_mbps -> tCK_ns -> tWTR_S_nCK
burst_length/data_rate/bank_relation -> BLN_MIN
WL + BLN_MIN + tWTR_S_nCK -> WR_TO_RD_DIFF
```

이 구조 때문에 MR 값을 바꾸면 condition symbol이 바뀌고, 그 condition이 공유 key로 쓰이는 table들이 다시 resolve되며, 최종 command window도 trace 가능한 방식으로 바뀐다.

## Inspection

```bash
python3 tools/inspect_lpddr6_graph.py WR_TO_RD_DIFF
```

JSON output:

```bash
python3 tools/inspect_lpddr6_graph.py WR_TO_RD_DIFF --json
```
