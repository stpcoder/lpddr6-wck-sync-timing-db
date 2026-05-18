# Exact Timing DB Status

## MR status

MR table은 전부 완료가 아니다.

완료된 범위:

1. MR0~MR127 address catalog.
2. Timing-critical MR field/value seed.
3. 주요 timing illegal/warning seed.
4. MR1 Table49~72 RL/WL/nWTP/nRTP/nACU numeric seed.
5. MR1 Table47/Table48 condition reference.
6. nWTP Table273~281 timing values and start-reference note.
7. nRTP Table268~272 timing values and start-reference note.
8. nACU Table415/Table420 values by DVFSL and speed bin.
9. DQ ODT Write Table319/Table320 ODTLon and async timing values. ODTLoff는 JEDEC TBD 그대로 유지.
10. NT-ODT Write Table329/Table330 values with high-speed TBD rows preserved.
11. NT-ODT Read Table331~336 values for DQ/RDQS.
12. MR10 Table90 RDQS pre-shift/preamble/postamble seed. MR10.OP[1]=1 half-rate RDQS는 Unit=2*tWCK로 환산.
13. MR22 Table117 WCK postamble seed.
14. WCK2CK Sync AC Table256~261 seed for read/write/CAS.
15. WCK2CK Sync-Off Table263~266 normalized seed rows.
16. Table263/Table264 full CMD pair matrix seed for WR/RD/MRR/WFF/RFF/RDC/meta transitions.
17. Table398 `tWRWTR`/`tRTRRD` and Table310 `tMRR` helper timing seed.
18. WCK2DQI/WCK2DQO Table477 full seed including LF/HF/LF_L temp/voltage variation coefficients and source TBD rows.
19. LPDDR5 대비 ODT write timing delta seed.
20. MR1.OP[4:0] common speed-bin validation. `data_rate_mbps`는 실제 operating point 입력이고, MR1 code가 허용하는 bin 안에 있는지 evaluator trace로 검증한다.

아직 남은 범위:

1. 모든 MR의 full OP value map.
2. 모든 MR의 full illegal 조합.
3. non-timing MR의 세부 기능 설명.
4. 현재 ODT write delta seed를 제외한 full LPDDR5 비교 layer.

따라서 현재 상태는 “전체 MR 완료”가 아니라 “timing 계산에 먼저 필요한 MR1 latency layer를 완성 단계로 올린 상태”다.

## MR1 latency lookup 조건

MR1 latency 계산은 다음 순서로 resolve해야 한다.

1. `active_fsp`: MR13 OP[7:6] FSP-OP로 active MR1 slot 선택.
2. `MR1.OP[4:0]`: RL/WL/nWTP/nRTP/nACU code 선택.
3. `MR1.OP[5]`: WL Set A 또는 Set B 선택.
4. `Read DBI`: MR3 OP[0] 기준.
5. `Efficiency`: MR1 OP[6]과 MR0 OP[2] static efficiency status 기준.
6. `DVFSL`: MR11 OP[4] 기준.
7. `Write Link Protection`: MR23 OP[0] 또는 OP[1] 기준.
8. `Read Link Protection`: MR23 OP[2] 기준.

Read Link Protection이 enabled인 Table65~72에서는 Table48 기준 Read DBI가 '-' 처리된다. 그래서 selector에서는 `read_dbi=any`로 둔다.

`MR1.OP[4:0]`는 RL/WL table row를 고르는 code이고 동시에 speed-bin과 묶여 있다. 다만 `tWTR`의 nCK 변환은 MR1 code 자체가 아니라 실제 `data_rate_mbps`에서 나온 `tCK_ns`를 사용한다. 그래서 evaluator는 MR1 code로 data rate를 임의 고정하지 않고, `data_rate_mbps`가 해당 MR1 speed-bin 안에 있는지 먼저 검증한다. 같은 MR1 code bin 안에서도 실제 operating data rate가 다르면 `tCK_ns`와 `RU(ns/tCK)` 결과가 달라질 수 있다.

## Timing 우선순위

Command table보다 먼저 안정화해야 하는 timing layer:

1. MR1 latency: Table49~72.
2. nWTP usage: Table273~281. Seeded.
3. nACU concrete value: Table415 and Table420. Seeded.
4. nRTP usage: Table268~272. Seeded.
5. ODT latency: Table319/320/329/330 write side seeded with source TBD retained. Table331~336 read side seeded.
6. RDQS/WCK preamble/postamble: MR10, MR22, Table455. tRPRE/tRPST/tWCKPST evaluator trace is active; JEDEC AC table TBD values are preserved as status.
7. WCK2CK Sync AC: Table256~261. tWCKENL and tWCKPRE static/half/full toggle values are seeded and evaluator-backed for current RD/WR/MRR/RFF/RDC/WFF command classes.
8. WCK Sync-Off command-pair matrix: Table263~264. All seeded rows dispatch through evaluator; missing NT-ODT tODToff path is marked unresolved instead of guessed.
9. tWCK2DQO/tWCK2DQI: Table477 and Table478. HF/LF/LF_L input/output offset and temp/voltage variation coefficients are seeded with high-speed TBD preserved.
10. tWTR: Table414/416/417/418/419/421/422/423.
11. tRTW: Table389/390 plus ODT and DFE notes. DQ ODT off/on RD->WR and MRR->WR note paths are evaluator-backed.

이 layer들이 안정화된 다음에 Command Table383~412를 command-pair matrix로 확장하는 것이 맞다.
