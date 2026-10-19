## plan2.md
1. **Missing test for "no path exists" scenario**
   - File: tests/test_planner.py
   - Issue: The test suite does not verify that `plan_path` raises `ValueError` when the goal is unreachable.
   - Why it matters: This is a critical failure path specified in the plan and the code implementation; without a test, regressions in the search termination logic could go unnoticed.

The plan was reviewed in this round and no new problems were found.

## plan6.md
1. **Hardcoded line width**
   - File: render_velocity.py:32-34
   - Issue: `linewidth=1` is hardcoded for all three velocity lines.
   - Why it matters: According to R0 and the Spec, visual properties like line widths should live in `config.json` to avoid hardcoded literals.

## plan3.md
The plan was reviewed and no problem was found.

## plan4.md
The plan was reviewed and no problem was found.

## plan5.md
1. **Hardcoded visual styles and colors**
   - File: render_map.py
   - Issue: Colors ('green', 'red', 'blue', 'black', 'lightgray') and line widths are hardcoded in the source.
   - Why it matters: The specification explicitly requires that colors live in `config.json` to avoid hardcoded values (R0).
