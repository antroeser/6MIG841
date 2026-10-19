"""
planif.vue - Le trace du quadrillage du Lab 1, isole de l'application qui l'utilise.

Ce module ne contient QUE du dessin : pas de planificateur, pas de bouton, pas de boucle
d'evenements, et aucune fenetre ne s'ouvre a l'import. Il existe parce que deux vues
differentes doivent tracer EXACTEMENT le meme quadrillage :

  - `planif.app.VueCarte`, l'application du Lab 1, qui y ajoute les trois chemins compares
    et le triangle qui se teleporte ;
  - `Devoir2.code.grille_view.VueGrilleDevoir2`, qui y reporte la position reelle de la
    tortue turtlesim pendant le Devoir 2.

Recopier le trace dans la seconde aurait cree deux quadrillages qui derivent en silence :
une couleur changee d'un cote, une ligne de bord oubliee de l'autre, et plus rien ne dit
lequel est le bon. C'est aussi ce que demande la progression du cours (enonce.md) : chaque
travail REPREND le contenu du precedent, il ne le reecrit pas.

Le trace suit la solution de reference en lecture seule
`C:\\Users\\m3otis\\solution_robot_dimension\\render_map.py` (fonction `_draw_grid`) :
une ligne par FRONTIERE de cellule, donc `largeur_cellules + 1` verticales et
`hauteur_cellules + 1` horizontales, en `lightgray` d'epaisseur 0.5.

Toutes les couleurs viennent de la section `affichage` de planif_config.json (R7).
"""

from __future__ import annotations

from typing import Any

import matplotlib.pyplot as plt

from .world import Cellule, World

#: Conversion technique entre l'unite de `matplotlib.Axes.scatter` (points au carre, fixee
#: par l'API de matplotlib) et la fraction de cellule exprimee dans planif_config.json.
#: Ce n'est pas une valeur configuree mais une constante de l'API de rendu (R0), au meme
#: titre que le 400 de `planif.app` pour le triangle.
_AIRE_MARQUEUR_POINTS2 = 80


def cadrer_axes(ax: Any, monde: World) -> None:
    """
    --------------------------------------------------------------------------
    Purpose:
        Borner les axes sur l'etendue exacte de la grille et imposer des cellules
        CARREES. Sans `set_aspect('equal')`, matplotlib etire la figure a la taille
        de la fenetre et le quadrillage devient un damier de rectangles : c'est ce
        qui avait ete signale comme « ce n'est plus un grillage » le 2026-09-20.

    Inputs:
        ax (matplotlib.axes.Axes): axes a cadrer
        monde (World): grille de reference (origine, nombre et taille des cellules)

    Outputs:
        aucun
    --------------------------------------------------------------------------
    """
    ax.set_xlim(monde.origine_x,
                monde.origine_x + monde.largeur_cellules * monde.taille_cellule)
    ax.set_ylim(monde.origine_y,
                monde.origine_y + monde.hauteur_cellules * monde.taille_cellule)
    ax.set_aspect("equal")
    ax.set_facecolor("white")


def tracer_grille(ax: Any, monde: World, affichage: dict[str, Any],
                  avec_obstacle: bool = True) -> None:
    """
    --------------------------------------------------------------------------
    Purpose:
        Tracer une ligne sur chaque FRONTIERE de cellule, bords compris, puis
        remplir les cellules d'obstacle.

        Le nombre de lignes est `largeur_cellules + 1` et non `largeur_cellules` :
        une grille de N cellules a N+1 frontieres. Omettre le +1 laisse le bord
        droit et le bord haut ouverts.

    Inputs:
        ax (matplotlib.axes.Axes): axes deja cadres par `cadrer_axes`
        monde (World): grille de reference
        affichage (dict): section 'affichage' de planif_config.json
        avec_obstacle (bool): tracer aussi l'obstacle DU PLANIFICATEUR. Vrai pour
            le Lab 1, ou cet obstacle est le sujet meme de l'exercice. FAUX pour
            le Devoir 2, ou le seul obstacle reel est la tortue engendree dans
            turtlesim : l'afficher tous les deux mettait deux obstacles
            differents dans la meme image, et la tortue demarrant au centre du
            canevas turtlesim (5.544, 5.544) tombe exactement sur la cellule
            centrale, donc DANS l'obstacle du planificateur. On annoncait ainsi
            un evitement de collision en dessinant le robot a l'interieur d'un
            obstacle qui n'existe pas dans la simulation (defaut signale par
            l'enseignant le 2026-09-20).

    Outputs:
        aucun
    --------------------------------------------------------------------------
    """
    for colonne in range(monde.largeur_cellules + 1):
        x = monde.origine_x + colonne * monde.taille_cellule
        ax.axvline(x, color=affichage["couleur_grille"], linewidth=0.5, zorder=0)
    for ligne in range(monde.hauteur_cellules + 1):
        y = monde.origine_y + ligne * monde.taille_cellule
        ax.axhline(y, color=affichage["couleur_grille"], linewidth=0.5, zorder=0)

    if avec_obstacle:
        for cellule in monde.cellules_obstacle():
            tracer_cellule(ax, monde, cellule, affichage["couleur_obstacle"])


def tracer_cellule(ax: Any, monde: World, cellule: Cellule, couleur: str) -> None:
    """
    --------------------------------------------------------------------------
    Purpose:
        Remplir une cellule entiere de `couleur`, en partant de son COIN et non de
        son centre : `World.vers_unites` rend le centre, qui conviendrait a un
        marqueur mais decalerait le rectangle d'une demi-cellule.

    Inputs:
        ax (matplotlib.axes.Axes): axes cibles
        monde (World): grille de reference
        cellule (Cellule): couple (colonne, ligne)
        couleur (str): couleur matplotlib

    Outputs:
        aucun
    --------------------------------------------------------------------------
    """
    colonne, ligne = cellule
    taille = monde.taille_cellule
    x = monde.origine_x + colonne * taille
    y = monde.origine_y + ligne * taille
    ax.add_patch(plt.Rectangle((x, y), taille, taille, color=couleur, zorder=1))


def tracer_marqueur(ax: Any, monde: World, cellule: Cellule, couleur: str) -> None:
    """
    --------------------------------------------------------------------------
    Purpose:
        Placer un marqueur rond au CENTRE d'une cellule (depart, but).

    Inputs:
        ax (matplotlib.axes.Axes): axes cibles
        monde (World): grille de reference
        cellule (Cellule): couple (colonne, ligne)
        couleur (str): couleur matplotlib

    Outputs:
        aucun
    --------------------------------------------------------------------------
    """
    x, y = monde.vers_unites(cellule)
    ax.scatter([x], [y], marker="o", s=_AIRE_MARQUEUR_POINTS2, color=couleur, zorder=3)
