"""
planif.astar - Palier 1 : A* sur grille, le chemin le plus court, en escalier.

A* rend le chemin le plus court sur la grille 8-connexe, mais en suivant les aretes des
cellules : chaque cellule visitee est un point de passage, ce qui multiplie les changements
de direction (docs/superpowers/plans/6mig841-ameliorations/plan06.md, palier 1). C'est cette
limite, mesuree par le nombre de points de passage, que le palier 2 (thetastar) reduit.
"""

from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass

from .world import Cellule, World


@dataclass
class ResultatPlanification:
    """Resultat d'un appel de planification A*."""

    chemin: list[Cellule] | None
    longueur: float
    cellules_examinees: int


def planifier(monde: World, depart: Cellule, but: Cellule) -> ResultatPlanification:
    """
    --------------------------------------------------------------------------
    Purpose:
        Calculer le plus court chemin de `depart` a `but` par A*, 8-connexe.

    Inputs:
        monde (World): grille et occupation
        depart (Cellule): cellule de depart
        but (Cellule): cellule d'arrivee

    Outputs:
        resultat (ResultatPlanification): chemin (None si inatteignable), longueur totale
            en unites, et nombre de cellules examinees
    --------------------------------------------------------------------------
    """
    if not monde.est_dans_la_grille(depart):
        raise ValueError(f"Depart hors grille : {depart}.")
    if not monde.est_dans_la_grille(but):
        raise ValueError(f"But hors grille : {but}.")
    # Trouve par comparaison avec la reference Aider (planner.py, _validate_start_goal) :
    # sans ce controle, un depart occupe n'etait ni refuse ni meme detecte -- A* rendait un
    # chemin qui COMMENCE sur l'obstacle, comme si le robot pouvait legalement s'y trouver
    # (mesure : depart=(0,0) occupe, chemin=[(0,0), (1,1), ...] rendu tel quel). Un but occupe,
    # lui, redevenait deja "chemin=None" par construction (aucun voisin occupe n'est jamais
    # relache), mais sans dire POURQUOI -- indiscernable d'un but simplement encercle.
    if monde.est_occupee(depart):
        raise ValueError(f"Depart {depart} est dans l'obstacle.")
    if monde.est_occupee(but):
        raise ValueError(f"But {but} est dans l'obstacle.")

    # Compteur d'insertion : depart-egalite deterministe dans le tas (R19). A f-cout egal,
    # l'entree inseree en premier sort en premier, et l'ordre d'insertion ne depend que de
    # l'ordre fixe des voisins de World, donc deux executions identiques donnent le meme
    # chemin.
    # Indice : tas priorise par cout f = cout_venu + heuristique, fermer avant d'expandre
    # Tests : test_chemin_en_ligne_droite_sans_obstacle_ne_fait_aucun_detour, test_obstacle_contourne_le_chemin_existe_et_s_allonge, test_arrivee_enfermee_ne_rend_rien
    raise NotImplementedError(
        "fonction 'astar.planifier' a implementer (voir l'enonce et les tests cites)"
    )


def _reconstruire(parent: dict[Cellule, Cellule], depart: Cellule, but: Cellule) -> list[Cellule]:
    """Remonte la chaine des parents de `but` a `depart`, puis inverse l'ordre."""
    chemin = [but]
    actuelle = but
    while actuelle != depart:
        actuelle = parent[actuelle]
        chemin.append(actuelle)
    chemin.reverse()
    return chemin
