"""
planif.app - Vue carte matplotlib du Lab 1 : la grille, l'obstacle, le chemin calcule et le
triangle qui parcourt les points de passage en s'y teleportant.

Trois boutons, un par palier (A*, Theta*, D*-Lite), rendent la comparaison des trois
planificateurs VISIBLE plutot que seulement tabulee
(docs/superpowers/plans/6mig841-ameliorations/plan06.md, etape 7). Aucune fenetre ne s'ouvre a
l'import de ce module : seul main() construit la figure et lance la boucle d'evenements, donc
aucune fenetre ne s'ouvre pendant la suite de tests (spec.md, R5).

Le triangle se TELEPORTE d'un point de passage au suivant : aucune cinematique ici, elle
arrive au Devoir 2. Un chemin correct et un mouvement correct sont deux problemes distincts,
et les meler rend l'echec illisible (enonce.md, section Lab 1).

Toutes les couleurs, tailles et la cadence de teleportation viennent de la section
`affichage` de planif_config.json (workflow.md R7) : rien n'est ecrit en dur ici.
"""

from __future__ import annotations

import sys
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.widgets import Button

from . import astar, thetastar, vue, world
from .dstarlite import DStarLite
from .world import Cellule, World

_PALIERS = ("astar", "thetastar", "dstarlite")
_ETIQUETTES = {"astar": "A*", "thetastar": "Theta*", "dstarlite": "D*-Lite"}


def _calculer_chemins(monde: World, depart: Cellule, but: Cellule) -> dict[str, list[Cellule] | None]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Calculer le chemin initial des trois planificateurs sur le meme monde, une fois,
        pour que les trois boutons n'aient qu'a relire un resultat deja pret.

    Inputs:
        monde (World): grille et occupation partagees
        depart (Cellule): cellule de depart
        but (Cellule): cellule d'arrivee

    Outputs:
        chemins (dict[str, list[Cellule] | None]): un chemin (ou None) par palier
    --------------------------------------------------------------------------
    """
    return {
        "astar": astar.planifier(monde, depart, but).chemin,
        "thetastar": thetastar.planifier(monde, depart, but).chemin,
        "dstarlite": DStarLite(monde, depart, but).planifier().chemin,
    }


class VueCarte:
    """
    Fenetre matplotlib unique : grille, obstacle en noir, chemin du palier selectionne, et
    le triangle qui se teleporte de point de passage en point de passage. Un bouton par
    palier bascule le chemin trace et redemarre la teleportation depuis le depart.
    """

    def __init__(self, monde: World, affichage: dict[str, Any]):
        self.monde = monde
        self.affichage = affichage
        self.depart = monde.depart
        self.but = monde.but
        if self.depart is None or self.but is None:
            raise ValueError(
                "planif_config.json doit fournir 'depart' et 'but' pour l'affichage."
            )

        self.chemins = _calculer_chemins(monde, self.depart, self.but)
        self.palier_actif = "astar"
        self._index_triangle = 0
        self._minuteur = None

        self.figure, self.ax = plt.subplots(
            figsize=(affichage["largeur_figure"], affichage["hauteur_figure"]),
            dpi=affichage["dpi_figure"],
        )
        plt.subplots_adjust(bottom=0.22)
        self._tracer_grille()
        (self._ligne_chemin,) = self.ax.plot([], [], "-", linewidth=2, zorder=2)
        # Le 400 n'est pas une valeur configuree : c'est la conversion technique entre
        # l'unite de matplotlib.Axes.scatter (points^2, fixee par l'API) et la fraction de
        # cellule que "taille_triangle" exprime dans planif_config.json. C'est une constante
        # mathematique de l'API de rendu, pas une decision de l'enseignant (R0).
        self._point_triangle = self.ax.scatter(
            [], [],
            marker="^",
            s=400 * affichage["taille_triangle"],
            color=affichage["couleur_triangle"],
            zorder=3,
        )
        self._boutons: list[Button] = []
        self._construire_boutons()
        self._selectionner_palier("astar")

    # ---------------------------------------------------------------------- construction

    def _tracer_grille(self) -> None:
        """
        Dessine les lignes de grille, l'obstacle en noir, et les marqueurs depart/but.

        Le trace lui-meme vit dans `planif.vue` depuis le 2026-09-20, parce que la vue
        du Devoir 2 doit afficher EXACTEMENT le meme quadrillage (voir le docstring de
        ce module-la). Cette methode n'est plus qu'un assemblage.
        """
        aff = self.affichage
        vue.cadrer_axes(self.ax, self.monde)
        vue.tracer_grille(self.ax, self.monde, aff)
        vue.tracer_marqueur(self.ax, self.monde, self.depart, aff["couleur_depart"])
        vue.tracer_marqueur(self.ax, self.monde, self.but, aff["couleur_but"])

    def _tracer_cellule(self, cellule: Cellule, couleur: str) -> None:
        """Remplit une cellule de grille avec `couleur` (utilise pour l'obstacle, en noir)."""
        vue.tracer_cellule(self.ax, self.monde, cellule, couleur)

    def _tracer_marqueur(self, cellule: Cellule, couleur: str) -> None:
        """Place un marqueur rond (depart ou but) au centre d'une cellule."""
        vue.tracer_marqueur(self.ax, self.monde, cellule, couleur)

    def _construire_boutons(self) -> None:
        """Un bouton par palier (A*, Theta*, D*-Lite), pour que la comparaison soit visible."""
        largeur = 0.2
        for index, palier in enumerate(_PALIERS):
            zone = self.figure.add_axes([0.05 + index * (largeur + 0.02), 0.05, largeur, 0.08])
            bouton = Button(zone, _ETIQUETTES[palier])
            bouton.on_clicked(self._creer_gestionnaire(palier))
            self._boutons.append(bouton)

    def _creer_gestionnaire(self, palier: str):
        """Capture `palier` dans une fermeture distincte par bouton (evite le piege de boucle)."""

        def _gestionnaire(_evenement) -> None:
            self._selectionner_palier(palier)

        return _gestionnaire

    # ------------------------------------------------------------------------ interaction

    def _selectionner_palier(self, palier: str) -> None:
        """Trace le chemin du palier choisi dans sa propre couleur et relance la teleportation."""
        self.palier_actif = palier
        chemin = self.chemins[palier]
        if chemin is None:
            self._ligne_chemin.set_data([], [])
        else:
            points = [self.monde.vers_unites(cellule) for cellule in chemin]
            xs, ys = zip(*points)
            self._ligne_chemin.set_data(xs, ys)

        couleur = self.affichage[f"couleur_chemin_{palier}"]
        self._ligne_chemin.set_color(couleur)
        self._point_triangle.set_color(couleur)
        self.ax.set_title(f"Palier : {_ETIQUETTES[palier]}")
        self._index_triangle = 0
        self._redemarrer_teleportation()
        self.figure.canvas.draw_idle()

    def _redemarrer_teleportation(self) -> None:
        """Replace le triangle au depart et relance le minuteur de teleportation."""
        if self._minuteur is not None:
            self._minuteur.stop()
        chemin = self.chemins[self.palier_actif]
        if not chemin:
            return
        self._placer_triangle(chemin[0])
        intervalle = self.affichage["intervalle_teleportation_ms"]
        self._minuteur = self.figure.canvas.new_timer(interval=intervalle)
        self._minuteur.add_callback(self._teleporter)
        self._minuteur.start()

    def _teleporter(self) -> None:
        """Deplace le triangle au point de passage suivant, sans aucune interpolation entre eux."""
        chemin = self.chemins[self.palier_actif]
        if not chemin:
            return
        self._index_triangle = (self._index_triangle + 1) % len(chemin)
        self._placer_triangle(chemin[self._index_triangle])
        self.figure.canvas.draw_idle()

    def _placer_triangle(self, cellule: Cellule) -> None:
        """Fixe la position du triangle au centre de `cellule`, sans transition visuelle."""
        x, y = self.monde.vers_unites(cellule)
        self._point_triangle.set_offsets(np.array([[x, y]]))

    def demarrer(self) -> None:
        """Affiche la fenetre et lance la boucle d'evenements matplotlib (bloquant)."""
        plt.show()


def main() -> int:
    """
    --------------------------------------------------------------------------
    Purpose:
        Point d'entree de l'application matplotlib du Lab 1. Charge la configuration,
        construit la vue et lance la fenetre. N'est jamais appele a l'import du module.

    Inputs:
        aucun

    Outputs:
        code (int): 0
    --------------------------------------------------------------------------
    """
    monde = World()
    affichage = world.config_section("affichage")
    vue = VueCarte(monde, affichage)
    vue.demarrer()
    return 0


if __name__ == "__main__":
    sys.exit(main())
