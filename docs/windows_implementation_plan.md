# Windows Implementation Plan

## Tool Stack

- Python 3.11 or later
- VS Code
- Excel for CSV review
- SQLite for local cache, optional
- Streamlit for UI, optional after rule correctness is stable

No external package is required for the first evaluator if JSON and CSV are
used.  Streamlit can be added later for the calculator UI.

## First Evaluator Milestone

Inputs:

- one scenario JSON
- CSV lookup tables
- JSON rule files

Outputs:

- resolved symbol table
- selected rules
- final command min/max gap
- PASS/FAIL/illegal/not_allowed/requires_new_ws1
- trace lines

## UI Views

1. Scenario Calculator
   - command pair
   - data rate
   - BL
   - bank relation
   - MR values
   - requested gap

2. Trace View
   - every selected lookup row
   - every formula
   - every note adder
   - every illegal rule hit

3. Matrix View
   - sweep MR1 OP[4:0]
   - optionally sweep ODT on/off and same/different BG

4. Rule Browser
   - filter by target symbol such as tRTW_FINAL
   - filter by source table or note

## Maintenance Checks

- every rule must have source
- no overlapping formula rule without priority
- every required symbol must resolve before final formula
- any TBD in final path must raise warning
- any status=review in final path must raise warning
- illegal constraints must be evaluated before allowed result
