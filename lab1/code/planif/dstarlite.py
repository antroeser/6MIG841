"""
planif.dstarlite - Palier 3 : D*-Lite, la replanification incrementale.

A* et Theta* recalculent tout depuis zero des qu'un obstacle change. D*-Lite conserve, entre
deux appels, les valeurs g (cout reel) et rhs (cout candidat) de chaque cellule deja
calculee : quand une cellule change d'occupation, seules les cellules dont le cout est
reellement affecte sont remises dans la file et reexaminees, jamais la grille entiere
(docs/superpowers/plans/6mig841-ameliorations/plan06.md, palier 3). C'est le dernier palier :
il ne laisse aucune limite a mesurer.

Le triangle du Lab 1 se teleporte d'un point de passage au suivant (aucune cinematique),
donc l'agent ne "bouge" jamais pendant la planification : km reste a zero, et la seule
source de replanification est un changement d'occupation, jamais un deplacement de depart.
Reference algorithmique : Koenig & Likhachev, "D* Lite" (2002), simplifie pour un depart fixe.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Iterable

from .world import Cellule, World

_INFINI = float("inf")


@dataclass
class ResultatPlanification:
    """Resultat d'un appel de planification ou de replanification D*-Lite."""

    chemin: list[Cellule] | None
    longueur: float
    cellules_reexaminees: int


class DStarLite:
    """
    Planificateur D*-Lite a depart fixe. Conserve g/rhs et la file de priorite entre les
    appels, pour que `mettre_a_jour_obstacle` ne reexamine que ce qu'un changement affecte.
    """

    def __init__(self, monde: World, depart: Cellule, but: Cellule):
        if not monde.est_dans_la_grille(depart):
            raise ValueError(f"Depart hors grille : {depart}.")
        if not monde.est_dans_la_grille(but):
            raise ValueError(f"But hors grille : {but}.")
        # Meme controle qu'astar.py et thetastar.py, trouve par comparaison avec la
        # reference Aider (planner.py, _validate_start_goal) : sans lui, un depart ou un
        # but occupe des la CONSTRUCTION n'etait ni refuse ni explique. D*-Lite finissait
        # bien par rendre chemin=None dans ce cas (son propre _mettre_a_jour_sommet force
        # rhs a l'infini pour une cellule occupee des qu'elle est visitee), mais seulement
        # par effet de bord de la recherche, sans jamais dire POURQUOI -- indiscernable
        # d'un depart simplement inatteignable.
        if monde.est_occupee(depart):
            raise ValueError(f"Depart {depart} est dans l'obstacle.")
        if monde.est_occupee(but):
            raise ValueError(f"But {but} est dans l'obstacle.")

        self.monde = monde
        self.depart = depart
        self.but = but
        self._g: dict[Cellule, float] = {}
        self._rhs: dict[Cellule, float] = {but: 0.0}
        self._file: list[tuple[tuple[float, float], Cellule]] = []
        self._dans_file: dict[Cellule, tuple[float, float]] = {}
        self.cellules_reexaminees = 0

        cle = self._cle(but)
        self._dans_file[but] = cle
        heapq.heappush(self._file, (cle, but))

    # ------------------------------------------------------------------ acces g/rhs/cle

    def _g_de(self, cellule: Cellule) -> float:
        return self._g.get(cellule, _INFINI)

    def _rhs_de(self, cellule: Cellule) -> float:
        return self._rhs.get(cellule, _INFINI)

    def _cle(self, cellule: Cellule) -> tuple[float, float]:
        petit = min(self._g_de(cellule), self._rhs_de(cellule))
        return (petit + self.monde.distance_heuristique(self.depart, cellule), petit)

    # ------------------------------------------------------------------------- file lazy

    def _sommet_haut(self) -> tuple[tuple[float, float] | None, Cellule | None]:
        """Sommet valide le plus prioritaire, en purgeant les entrees perimees en tete."""
        while self._file:
            cle, cellule = self._file[0]
            if self._dans_file.get(cellule) != cle:
                heapq.heappop(self._file)  # entree perimee : une cle plus recente existe
                continue
            return cle, cellule
        return None, None

    def _mettre_a_jour_sommet(self, cellule: Cellule) -> None:
        if cellule != self.but:
            if self.monde.est_occupee(cellule):
                meilleur = _INFINI
            else:
                meilleur = _INFINI
                for voisine in self.monde.voisins(cellule):
                    cout = self._g_de(voisine) + self.monde.cout_deplacement(cellule, voisine)
                    if cout < meilleur:
                        meilleur = cout
            self._rhs[cellule] = meilleur

        self._dans_file.pop(cellule, None)
        if self._g_de(cellule) != self._rhs_de(cellule):
            cle = self._cle(cellule)
            self._dans_file[cellule] = cle
            heapq.heappush(self._file, (cle, cellule))

    def _calculer_chemin_le_plus_court(self) -> None:
        """
        Boucle incrementale de D*-Lite (Koenig et Likhachev) : depiler le sommet de plus
        petite cle tant qu'elle est inferieure a celle du depart ou que g et rhs du depart
        divergent, et propager la mise a jour aux voisins. Seuls les sommets touches par le
        dernier changement sont reexamines, jamais toute la grille.
        """
        # Indice : depiler tant que la cle du sommet est inferieure a celle du depart, propager g/rhs aux voisins potentiels
        # Tests : test_moins_de_cellules_reexaminees_qu_une_replanification_complete, test_premier_calcul_dstarlite_egale_la_longueur_d_astar
        raise NotImplementedError(
            "fonction 'DStarLite._calculer_chemin_le_plus_court' a implementer (voir l'enonce et les tests cites)"
        )

    # --------------------------------------------------------------------------- public

    def planifier(self) -> ResultatPlanification:
        """Calcule (ou complete) le chemin courant. Reinitialise le compteur d'examens."""
        self.cellules_reexaminees = 0
        self._calculer_chemin_le_plus_court()
        return self._resultat()

    def mettre_a_jour_obstacle(self, cellules: Iterable[Cellule], occupee: bool) -> ResultatPlanification:
        """
        --------------------------------------------------------------------------
        Purpose:
            Basculer l'occupation de `cellules`, ne reexaminer que ce que le changement
            affecte reellement, et rendre le nouveau chemin. C'est la mesure comparee a
            une replanification complete (test central du palier 3).

        Inputs:
            cellules (Iterable[Cellule]): cellules dont l'occupation change
            occupee (bool): True pour ajouter un obstacle, False pour le retirer

        Outputs:
            resultat (ResultatPlanification): nouveau chemin, longueur, et nombre de
                cellules reexaminees pour CETTE mise a jour seulement
        --------------------------------------------------------------------------
        """
        self.cellules_reexaminees = 0
        changees = self.monde.definir_occupation(cellules, occupee)
        for cellule in changees:
            self._mettre_a_jour_sommet(cellule)
            for voisine in self.monde.voisins_potentiels(cellule):
                self._mettre_a_jour_sommet(voisine)
        self._calculer_chemin_le_plus_court()
        return self._resultat()

    def _resultat(self) -> ResultatPlanification:
        if self._g_de(self.depart) == _INFINI:
            return ResultatPlanification(
                chemin=None, longueur=_INFINI, cellules_reexaminees=self.cellules_reexaminees
            )

        chemin = [self.depart]
        actuelle = self.depart
        garde_fou = self.monde.largeur_cellules * self.monde.hauteur_cellules + 1
        while actuelle != self.but:
            garde_fou -= 1
            if garde_fou < 0:
                raise RuntimeError("dstarlite: la reconstruction du chemin ne converge pas.")
            meilleure = None
            meilleur_cout = _INFINI
            for voisine in self.monde.voisins(actuelle):
                cout = self.monde.cout_deplacement(actuelle, voisine) + self._g_de(voisine)
                if cout < meilleur_cout:
                    meilleur_cout = cout
                    meilleure = voisine
            if meilleure is None:
                return ResultatPlanification(
                    chemin=None, longueur=_INFINI, cellules_reexaminees=self.cellules_reexaminees
                )
            chemin.append(meilleure)
            actuelle = meilleure

        longueur = sum(
            self.monde.cout_deplacement(chemin[i], chemin[i + 1]) for i in range(len(chemin) - 1)
        )
        return ResultatPlanification(
            chemin=chemin, longueur=longueur, cellules_reexaminees=self.cellules_reexaminees
        )
