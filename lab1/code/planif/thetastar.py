"""
planif.thetastar - Palier 2 : Theta*, la ligne de vue qui supprime l'escalier d'A*.

Theta* etend A* d'un seul ajout : avant d'accepter un voisin par le noeud courant, il teste
la ligne de vue directe depuis le PARENT du noeud courant. Si elle est libre, le voisin
rattache directement son parent au grand-parent, ce qui saute le noeud intermediaire. Le
chemin final suit donc des segments a angle libre au lieu des aretes de la grille, avec
beaucoup moins de points de passage qu'A* (docs/superpowers/plans/6mig841-ameliorations/
plan06.md, palier 2). Sa limite, que le palier 3 (dstarlite) resout, est qu'il replanifie
tout depuis zero des qu'un obstacle change.
"""

from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass

from .world import Cellule, World


@dataclass
class ResultatPlanification:
    """Resultat d'un appel de planification Theta*."""

    chemin: list[Cellule] | None
    longueur: float
    cellules_examinees: int


def planifier(monde: World, depart: Cellule, but: Cellule) -> ResultatPlanification:
    """
    --------------------------------------------------------------------------
    Purpose:
        Calculer un chemin a angle libre de `depart` a `but` par Theta*, 8-connexe.

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
    # Meme controle qu'astar.py, trouve par comparaison avec la reference Aider : sans lui,
    # un depart occupe n'etait ni refuse ni detecte.
    if monde.est_occupee(depart):
        raise ValueError(f"Depart {depart} est dans l'obstacle.")
    if monde.est_occupee(but):
        raise ValueError(f"But {but} est dans l'obstacle.")

    compteur = itertools.count()  # depart-egalite deterministe (R19), comme astar.py
    file: list[tuple[float, int, Cellule]] = []
    heapq.heappush(file, (0.0, next(compteur), depart))

    cout_venu: dict[Cellule, float] = {depart: 0.0}
    parent: dict[Cellule, Cellule] = {depart: depart}
    fermes: set[Cellule] = set()
    cellules_examinees = 0

    while file:
        _, _, actuelle = heapq.heappop(file)
        if actuelle in fermes:
            continue
        fermes.add(actuelle)
        cellules_examinees += 1

        if actuelle == but:
            return ResultatPlanification(
                chemin=_reconstruire(parent, depart, but),
                longueur=cout_venu[actuelle],
                cellules_examinees=cellules_examinees,
            )

        for voisine in monde.voisins(actuelle):
            if voisine in fermes:
                continue
            _mettre_a_jour_sommet(monde, actuelle, voisine, cout_venu, parent, but, file, compteur)

    return ResultatPlanification(chemin=None, longueur=float("inf"), cellules_examinees=cellules_examinees)


def _mettre_a_jour_sommet(
    monde: World,
    actuelle: Cellule,
    voisine: Cellule,
    cout_venu: dict[Cellule, float],
    parent: dict[Cellule, Cellule],
    but: Cellule,
    file: list[tuple[float, int, Cellule]],
    compteur: itertools.count,
) -> None:
    """
    Regle de Theta* (Nash et al.) : si le grand-parent de `actuelle` voit `voisine` en
    ligne directe, on rattache `voisine` au grand-parent (saute `actuelle`) plutot qu'a
    `actuelle` elle-meme, quand cela raccourcit le chemin.
    """
    # Indice : regle de Nash et al. : si le grand-parent voit voisine en ligne directe, rattacher au grand-parent plutot qu'a actuelle
    # Tests : test_thetastar_a_moins_de_points_de_passage_qu_astar_sur_la_meme_grille, test_chemin_theta_reste_libre_de_collision
    raise NotImplementedError(
        "fonction 'thetastar._mettre_a_jour_sommet' a implementer (voir l'enonce et les tests cites)"
    )


def _reconstruire(parent: dict[Cellule, Cellule], depart: Cellule, but: Cellule) -> list[Cellule]:
    """Remonte la chaine des parents de `but` a `depart` (le depart est son propre parent)."""
    chemin = [but]
    actuelle = but
    while actuelle != depart:
        actuelle = parent[actuelle]
        chemin.append(actuelle)
    chemin.reverse()
    return chemin
