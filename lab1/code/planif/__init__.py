"""
planif - Les trois planificateurs d'evitement de collision du Lab 1 (6MIG841).

Palier 1 A* (world, astar), palier 2 Theta* (thetastar), palier 3 D*-Lite (dstarlite).
Voir docs/superpowers/plans/6mig841-ameliorations/plan06.md pour la progression complete.

Ce paquet ne depend que de la bibliotheque standard, matplotlib et numpy (spec.md : le
Lab 1 se conforme a la contrainte matplotlib+numpy seulement, sans bibliotheque de
planification tierce et sans dependance a `ihr_ros`).
"""

from __future__ import annotations
