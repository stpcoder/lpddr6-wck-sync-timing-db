# Target Parameter Element Map

This note describes the semantic leaf model used by the target timing
calculator. Raw MR fields are implementation details. The UI exposes semantic
leaf keys, maps them to MR/scenario fields once, and every formula references
the same resolved symbols.

## Shared Leaf Keys

| Leaf key | Meaning | Internal mapping |
|---|---|---|
| `speed_bin` | Operating data-rate range selection, shown as values such as `Up to 10667 Mbps` | `MR1.OP[4:0]`, `data_rate_mbps`, `ck_mhz`, `wck_mhz`, `tCK_ns`, `tWCK_ns` |
| `bank_relation` | Same/different BG and bank relation | `same_bg`, `same_bank` |
| `burst_length` | BL24 or BL48 | BL/n lookup selector |
| `read_dbi_enabled` | Read DBI condition | `MR3.OP[0]` |
| `efficiency_mode_enabled` | Dynamic efficiency condition | `MR1.OP[6]` |
| `dvfsl_enabled` | DVFSL condition | `MR11.OP[4]`; LF_L path when needed |
| `write_link_protection_enabled` | Write link protection condition | `MR23.OP[0]` in the current seed |
| `read_link_protection_enabled` | Read link protection condition | `MR23.OP[2]` |
| `wl_set_b` | WL Set A/B selector | `MR1.OP[5]` |
| `wck_frequency_mode` | WCK LF/HF family | `MR11.OP[6]` |
| `dq_odt_enabled` | Target DQ ODT path | `MR19.OP[2:0] != 000` |
| `dq_nt_odt_enabled` | Read non-target ODT path | `MR20.OP[2:0] != 000` |
| `rdqs_*` | RDQS timing selectors | `MR10`, `MR22` fields |
| `dfeq_enabled` | DFE equalization quantity enabled | `MR70..MR75` DFE quantity fields |
| `per_pin_dfe_enabled` | tRTW note adder | `MR41.OP[0]` |

## Requested Targets

| Target | Formula / lookup | Required base elements |
|---|---|---|
| `tRTRRD` | `RL + BLN_MAX + MAX(RU(7.5ns/tCK), 6nCK)`, then even command-gap rounding | `RL`, `BLN_MAX`, `tCK_ns` |
| `RL` | MR1 latency table lookup | `speed_bin`, Read DBI, efficiency, DVFSL, write/read link protection |
| `tWCKPST` | `RD((WCK PST coefficient * tWCK) / tCK)` | `wck_postamble_length`, `tWCK_ns`, `tCK_ns` |
| `WL` | MR1 latency table lookup plus WL Set A/B | `speed_bin`, `wl_set_b`, latency table feature selectors |
| `tRTW` | ODT off: `RL + BLN + RU(tWCK2DQO/tCK) - WL`; ODT on: `RL + BLN + RU(tWCK2DQO/tCK) + RD(tRPST/tCK) - ODTLon - RD(tODTon_MIN/tCK) + 1`; final: `EVEN(base + note adders)` | `RL`, `WL`, `BLN_MIN/MAX`, `tWCK2DQO`, `tRPST`, `ODTLon`, `tODTon_MIN`, `dfeq_enabled`, `per_pin_dfe_enabled` |
| `tWTR_S/L` | `MAX(RU(ns_floor/tCK), nCK_floor)` | DVFSL, write link protection, efficiency, `tCK_ns` |
| `tWCK2DQO` | Table477 max-ps lookup | `wck_frequency_mode`, DVFSL/DVFS family, `data_rate_mbps` |
| `ODTLon` | ODT table lookup, DQ ODT path currently uses `WL-k` by speed row | `dq_odt_enabled`, `WL`, `data_rate_mbps` |
| `tODTon_MAX` | Async ODT table max ns; optional `RU(tODTon_MAX_ns/tCK)` | `dq_odt_enabled`, `data_rate_mbps`, `tCK_ns` |
| `tODT_RDon_MAX` | Read NT-ODT async-on max ns; optional `RU(tODT_RDon_MAX_ns/tCK)` | `dq_nt_odt_enabled`, read NT-ODT target, RDQS selectors when target is RDQS, `data_rate_mbps`, `tCK_ns` |

## Key Rule

`data_rate_mbps` is a shared intermediate symbol. It is produced from
`speed_bin` once and then reused everywhere. The WCK Sync-Off path does not own
a separate data-rate value for `tRTW`, and the latency path does not own a
separate data-rate value for `RL`; both reference the same symbol in the
dependency tree.

## Note Conditions

| Note condition | Semantic leaf / condition | Formula effect | Current state |
|---|---|---|---|
| tRTW DFE equalization note | `dfeq_enabled` | `+1 nCK` before final EVEN | implemented |
| tRTW per-pin DFE note | `per_pin_dfe_enabled` | `+1 nCK` before final EVEN | implemented |
| tRTW final even rule | internal final formula | odd result rounds up to next even nCK | implemented |
| RDQS disabled tRPST guard | `rdqs_enabled = Disabled` | `tRPST = 0` in ODT-on path | implemented |
| DVFSQ forces ODT off | `dvfsq_enabled` condition, not exposed in target UI yet | ODT/NT-ODT effective false | evaluator implemented, target leaf pending |
| WCK postamble must exceed RDQS postamble | `wck_postamble_length`, RDQS postamble leaves | warning when violated | evaluator warning implemented |
