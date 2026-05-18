# Timing Calculation Architecture

## 현재 결론

MR은 아직 “전부 완료”가 아니다. 현재 완료된 것은 MR0~MR127 주소 카탈로그와
timing에 직접 영향을 주는 MR seed다. 전체 OP value map과 모든 illegal 조합은
계속 보강해야 한다.

다음 단계는 JEDEC 표를 단순 표로 옮기는 것이 아니라, 계산 가능한 rule packet으로
쪼개는 것이다. 각 timing parameter는 반드시 아래 정보를 가져야 한다.

1. 원 JEDEC 위치: table, note, figure, clause.
2. 원 단위: ns, ps, nCK, tWCK, tCK, mixed.
3. 계산 단위: 기본은 nCK.
4. 조건 key: MR bit, command 종류, BG 관계, ODT, DVFS, link protection 등.
5. 변환 규칙: RU, RD, EVEN, max, min, TBD propagation.
6. 최종 trace: 어떤 조건이 hit 되었고 어떤 식으로 값이 나왔는지.

## 계산 흐름

1. Scenario를 읽는다.
2. MR13 기준 active FSP를 정한다.
3. active FSP의 MR field를 condition dictionary의 symbol로 decode한다.
4. illegal 또는 reserved MR 조합을 먼저 검사한다.
5. MR1 table selector로 RL, WL, nWTP, nRTP, nACU table을 고른다.
6. nWTP/nRTP/nACU timing table과 MR1 row가 일치하는지 source table 기준으로 대조한다.
7. data rate에서 CK와 WCK를 계산한다.
8. BL/n, BL/n_min, BL/n_max를 고른다.
9. DVFSL, link protection, efficiency 조건으로 tWTR_S/L raw 값을 고른다.
10. WCK FM과 voltage mode로 tWCK2DQI/O family와 variation coefficient를 고른다.
11. MR10으로 RDQS pre-shift, tRPRE, tRPST를 고르고 MR22로 tWCKPST를 고른다.
12. 현재 command class로 WCK2CK Sync AC table을 골라 tWCKENL과 tWCKPRE static/half/full toggle 값을 남긴다.
13. RDQS postamble과 ODT effective 조건으로 tRTW formula branch 입력값을 고른다.
14. DFE note adder와 EVEN rounding을 적용한다.
15. WCK Sync Off window의 min/max와 requested gap을 비교한다.
16. 계산 trace를 표 형태로 남긴다.

## Rule 추가 방식

새로운 JEDEC 표를 추가할 때는 다음 순서로 넣는다.

1. `lpddr6_condition_dictionary.csv`에 새 조건 key가 있는지 확인한다.
2. 없으면 condition key를 먼저 추가한다.
3. 원 표 값은 별도 data CSV에 넣는다.
4. 그 표가 어떤 symbol을 만드는지 `lpddr6_timing_parameter_catalog.csv`에 등록한다.
5. lookup 또는 formula 관계를 `lpddr6_rule_dependency_graph.csv`에 넣는다.
6. command pair에 직접 영향을 주면 `lpddr6_command_gap_rule_packets_seed.csv`에 rule row를 추가한다.
7. trace에 표시할 문구와 source를 반드시 넣는다.

## Parser 우선순위

P0는 실제 tRTW/tWTR/WCK Sync Off 계산에 막히는 항목이다.

1. MR1 Table 49~72의 RL/WL/nWTP/nRTP/nACU 전체 numeric row.
2. ODT Table 319, 320, 329, 330, 331~336. 현재 write/read seed는 들어갔고 TBD propagation과 rank-to-rank 적용을 보강해야 한다.
3. Command Table 383~390과 WCK Sync Off Table 263. 현재 RD/WR seed는 active.
4. WCK/RDQS timing: MR10, MR22, Table256~261, Table455, Table477. 현재 seed는 active이고 source TBD는 보존.
5. CAS WS/WS_OFF Table 394~396.
6. MRR/MRW Table 399와 Table 400의 timing-affecting MR list.

P1은 full scheduler 확장에 필요한 항목이다.

1. Auto-precharge Table 391~393.
2. rank-to-rank Table 401~405.
3. meta command Table 406~412.
4. WCK preamble과 half-toggle 관련 figure 설명 layer.

P2는 비교와 장기 유지보수 항목이다.

1. LPDDR5 matching table.
2. training, VREF, PPR, DCA, ECS 관련 MR full value map.

## Trace 요구 사항

최종 결과만 표시하면 안 된다. evaluator는 최소한 다음 row를 남겨야 한다.

1. clock derive: data rate에서 CK/WCK/tCK/tWCK가 어떻게 나왔는지.
2. MR decode: 각 MR bit가 어떤 condition으로 바뀌었는지.
3. lookup: 어떤 표 row가 선택되었는지.
4. formula: 어떤 식이 선택되었고 입력값이 무엇인지.
5. unit conversion: ns 또는 ps가 nCK로 어떻게 변환되었는지.
6. rounding: RU, RD, EVEN 적용 결과.
7. decision: requested gap이 min/max window 안인지.

이 구조로 가야 추후 조건을 추가해도 결과값뿐 아니라 “왜 그렇게 계산됐는지”를
검토할 수 있다.
