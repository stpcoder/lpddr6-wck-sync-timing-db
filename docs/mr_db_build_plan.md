# LPDDR6 MR DB Build Plan

## Purpose

The MR DB must support three uses:

1. Human review of every MR field and OP value.
2. Automatic decoding from raw MR values into timing variables.
3. Illegal or warning condition checks before timing calculation.

## Files

- `data/mr/lpddr6_mr_catalog.csv`
  - One row per MR address from MR0 to MR127.
  - Tracks access type, high-level function, FSP scope, and seeding status.

- `data/mr/lpddr6_mr_field_definitions_seed.csv`
  - Field-level definitions such as `MR22_WCK_PST = MR22 OP[7:6]`.
  - Includes Korean comments for what the field does.

- `data/mr/lpddr6_mr_value_map_seed.csv`
  - OP value meanings and side effects.
  - Uses grouped values such as `001B_110B` when all values share the same behavior.

- `data/mr/lpddr6_mr_illegal_rules.csv`
  - Illegal, warning, and dependency conditions.
  - These rules should be evaluated before timing rules.

## Status Categories

- `seeded`: entered from the local JEDEC text and ready for review.
- `partial`: only high-impact fields have been entered.
- `not_seeded`: cataloged but detailed field/value table is not entered yet.
- `review`: entered but needs PDF layout or interpretation confirmation.

## Next Fill Order

1. Complete MR2 and MR3 detailed definitions because DBI and driver controls affect latency and output timing.
2. Fill full VREF code tables MR12/MR14/MR15 if voltage margin calculation is required.
3. Fill MR30-MR40 training support fields completely.
4. Fill MR78-MR84 pre-drive settings because they connect to DFE/pre-drive behavior.
5. Fill MR85-MR99 fault/PRAC/meta controls.
6. Fill MR111-MR117 ECS controls.

## Evaluator Rule

The evaluator should process MR in this order:

1. Validate access and RFU/Reserved/DNU rules.
2. Resolve active FSP from MR13 FSP-OP.
3. Select FSP-scoped field values from active FSP.
4. Apply global illegal/warning rules.
5. Decode timing variables used by tRTW/tWTR/WCK Sync-Off.
