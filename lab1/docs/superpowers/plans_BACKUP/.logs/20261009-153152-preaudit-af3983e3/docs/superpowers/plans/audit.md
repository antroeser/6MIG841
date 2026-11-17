## plan2.md
1. **Missing test for "no path exists" scenario**
   - File: tests/test_planner.py
   - Issue: The test suite does not verify that `plan_path` raises `ValueError` when the goal is unreachable.
   - Why it matters: This is a critical failure path specified in the plan and the code implementation; without a test, regressions in the search termination logic could go unnoticed.

The plan was reviewed in this round and no new problems were found.

## plan3.md
The plan was reviewed and no problem was found.

## plan4.md
1. **Placeholder test for arc bulging**
   - File: tests/test_arcs.py:148-183
   - Issue: `test_verify_arc_bulging_into_obstacle` is empty (contains only `pass`).
   - Why it matters: The spec identifies arc bulging as the primary risk; without a functional test, the most critical failure path is unverified.
2. **Weak assertion in collision reporting test**
   - File: tests/test_arcs.py:211
   - Issue: `test_build_trajectory_collision_reporting` only checks if the result is a list, not if it contains collisions.
   - Why it matters: The test passes even if no collisions are detected.
