# Current Stage Audit

## Short Answer

MR parsing is not fully complete yet.

What is complete:

- MR0 through MR127 address catalog is present.
- Timing-critical MR seed fields are present for MR0, MR1, MR3, MR9 through MR28, MR30 through MR41, and MR70 through MR75.
- Major illegal combinations have been seeded.
- tRTW, tWTR, BL/n, WCK2DQI/O, RDQS pre/post, WCK pre/post, WCK Sync AC/Off, WCK FM/VDD mode, and ODT dependency files exist.
- Condition dictionary, rule packet schema, command gap seed rules, and a narrow seed evaluator now exist.
- The seed evaluator can emit trace output for seeded RD->WR and WR->RD examples.
- MR1 Table49 through Table72 latency values are now seeded into `data/lpddr6_mr1_latency_values_seed.csv`.
- MR1 latency condition notes from Table47 and Table48 are now captured in `data/timing/lpddr6_mr1_latency_condition_reference.csv`.
- nWTP Table273 through Table281, nRTP Table268 through Table272, and nACU Table415/Table420 are seeded and evaluator traces cross-checks against MR1 values.
- DQ ODT Table319/Table320 and write NT-ODT Table329/Table330 are seeded for ODTLon and async timing. DQ ODT ODTLoff remains explicit TBD per table.
- NT-ODT read tables Table331 through Table336 are seeded for DQ/RDQS read ODT latency.
- A first LPDDR5-vs-LPDDR6 ODT write timing comparison seed is present.
- RDQS MR10 Table90, WCK postamble MR22 Table117, WCK2CK Sync AC Table256 through Table261, WCK Sync-Off Table263 through Table266, Table263/264 CMD pair matrix, and WCK2DQ Table477 are seeded.
- The seed evaluator now dispatches all seeded Table263/264 WCK Sync-Off CMD pair rows and supports numeric, open, not-allowed, and unresolved decisions.
- The seed evaluator trace now includes tRPRE, tRPST, tWCKPST, tWCKENL, tWCKPRE, and tWCK2DQI/O selection.

What is not complete:

- Full OP value maps for every MR are not complete.
- Full MR table parsing is not complete. MR1 latency tables are seeded, but non-timing MR OP value maps still remain partial.
- MR1 has explicit TBD rows and DVFSL limited-row tables exactly as reflected in JEDEC; these must still produce warning/error decisions in the evaluator.
- MR2 and MR3 detailed definitions need to be parsed next because DBI and driver controls affect latency/output timing.
- ODT write/DQ ODT timing remains partial only where the source table itself is TBD. Table319 DQ ODT ODTLoff remains TBD and Table329 high-speed write rows include TBD.
- Command constraint coverage still excludes AP, detailed MRR/MRW Table399/Table400 guard paths, rank-to-rank, and efficiency/meta tables. WCK Sync-Off Table263/264 itself is now matrix-backed.
- TBD values must remain explicit and raise warnings in the evaluator.

## Required Database Standard

Every timing calculation must resolve through the following layers:

1. Scenario input.
2. Active FSP selection.
3. MR field decode.
4. Illegal/warning validation.
5. Lookup table selection.
6. Raw timing parameter resolution.
7. Unit conversion.
8. Formula rule selection.
9. Note adders and overrides.
10. Even command-gap rounding.
11. Final legal/not-allowed/illegal decision.
12. Trace output.

No final timing value should be emitted without a trace showing source table,
condition hit, formula, unit conversion, and rounding.

## Immediate Next Work

1. Add evaluator validation for MR1 TBD rows and DVFSL limited-row OP codes.
2. Add evaluator validation for ODT TBD paths and write NT-ODT ODTLoff formulas.
3. Add LPDDR5 comparison timing layer for RDQS/WCK Sync/WCK2DQ and tRTW/tWTR definitions.
4. Add the remaining MRR/MRW Table399/Table400 guard paths and NT-ODT enabled WFF->RFF tODToff(max) lookup.
5. Add UI/query layer that shows selected MR fields, source tables, formula inputs, and illegal/TBD warnings per scenario.
