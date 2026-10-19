# Progress

**Goal.** The ledger: one section per plan, each a list of tasks, telling the
harness which plan is current and which steps are done.

**Contents.** Task lines only, pointing at `plan<N>.md` for the detail. Never a
restatement of a plan. Marks: `- [ ]` not done, `- [x]` done and audited clean,
`- [!]` audit raised an issue, with one line naming it.

## plan1.md
- [ ] config.json with every configured value
- [ ] world.py: grid, cell geometry, obstacle occupancy
- [ ] world.py: grid / Cartesian / polar conversion about the bottom-left corner
- [ ] tests/test_world.py
- [ ] requirements.txt: declare any package this plan imports
- [ ] tests pass

## plan2.md
- [ ] planner.py: line-of-sight test between two cells - lit le config de World, lève KeyError si absent (R3)
- [ ] planner.py: Theta* returning waypoints from start to goal - lève ValueError si start/goal dans obstacle ou pas de chemin
- [ ] tests/test_planner.py - couvre succès, échec obstacle, échec pas de chemin, propriété Theta*
- [ ] requirements.txt: declare any package this plan imports (none new)
- [ ] tests pass

## plan3.md
- [ ] trajectory.py: trapezoidal profile, value and derivative at time t
- [ ] trajectory.py: total time split across segments by length
- [ ] tests/test_trajectory.py
- [ ] requirements.txt: declare any package this plan imports
- [ ] tests - suite passing (increased integration resolution to fix numerical tolerance issues)
- [ ] tests pass

## plan4.md
- [ ] arcs.py: drive r and angle by their own trapezoids, sample the arc
- [ ] arcs.py: collision verification against the obstacle, reported loudly
- [ ] tests/test_arcs.py
- [ ] requirements.txt: declare any package this plan imports (numpy, matplotlib already present)
- [ ] tests pass

## plan5.md
- [ ] render_map.py: grid, obstacle, planned path, travelled trail
- [ ] render_map.py: robot triangle oriented along motion, r/angle readout
- [ ] render_map.py: resize keeps content fitted and the grid square
- [ ] tests/test_render_map.py
- [ ] requirements.txt: declare any package this plan imports
- [ ] tests pass

## plan6.md
- [ ] render_velocity.py: rdot, angledot and Cartesian speed against time
- [ ] render_velocity.py: curves grow with the simulation, units and legend
- [ ] tests/test_render_velocity.py
- [ ] requirements.txt: declare any package this plan imports (none new)
- [ ] tests pass

## plan7.md
- [ ] app.py: the four controls and the elapsed-time display
- [ ] app.py: animation loop advancing simulated time and redrawing both axes
- [ ] tests/test_app.py
- [ ] requirements.txt: declare any package this plan imports (none new)
- [ ] tests pass

## final audit
- [ ] code audited and reviewed, problems listed
