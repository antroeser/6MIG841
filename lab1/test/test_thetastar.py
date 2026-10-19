"""
test_thetastar.py - Tests de planif.thetastar, palier 2 des trois planificateurs (plan06).

Theta* ajoute a A* un test de ligne de vue depuis le parent du noeud courant : le chemin final
suit des segments a angle libre au lieu des aretes de la grille, avec beaucoup moins de points
de passage qu'A*. Cette suite verifie la primitive dont Theta* depend (ligne de vue), sa raison
d'etre mesuree (moins de points de passage qu'A* sur la meme grille, teste en gras dans le plan),
que l'angle libre ne traverse jamais l'obstacle, et le chemin d'echec exige (arrivee enfermee,
workflow.md R5).
"""

from __future__ import annotations

import math

import pytest

from planif import astar, thetastar, world


def _petit_monde(largeur=8, hauteur=8, obstacle=None) -> world.World:
    """Un petit monde, avec un obstacle rectangulaire optionnel."""
    donnees: dict = {
        "grille": {"largeur_cellules": largeur, "hauteur_cellules": hauteur, "taille_cellule": 1.0}
    }
    if obstacle is not None:
        donnees["obstacle_initial"] = obstacle
    return world.World(donnees)


# --------------------------------------------------------------------- chemin heureux

def test_ligne_de_vue_libre_a_cote_de_l_obstacle_mais_pas_a_travers():
    """La primitive dont Theta* depend : vraie sous l'obstacle, fausse quand elle le traverse."""
    monde = _petit_monde(
        obstacle={"colonne_min": 3, "colonne_max": 4, "ligne_min": 0, "ligne_max": 4}
    )
    assert monde.ligne_de_vue_libre((0, 6), (7, 6)) is True
    assert monde.ligne_de_vue_libre((0, 2), (7, 2)) is False


def test_thetastar_a_moins_de_points_de_passage_qu_astar_sur_la_meme_grille():
    """
    La raison d'etre du palier 2 (plan06, ligne en gras) : sur le MEME monde, Theta* rend
    strictement moins de points de passage qu'A*, grace au raccourci en ligne de vue.
    """
    monde = _petit_monde(
        largeur=10, hauteur=10,
        obstacle={"colonne_min": 4, "colonne_max": 5, "ligne_min": 0, "ligne_max": 6},
    )
    depart, but = (0, 0), (9, 0)
    resultat_astar = astar.planifier(monde, depart, but)
    resultat_theta = thetastar.planifier(monde, depart, but)
    assert resultat_astar.chemin is not None
    assert resultat_theta.chemin is not None
    assert len(resultat_theta.chemin) < len(resultat_astar.chemin)


def test_longueur_rendue_egale_la_somme_des_distances_du_chemin():
    """
    Revue finale (constat Important) : aucun test de ce fichier ne lit
    `resultat.longueur`, la grandeur que `compare.py` publie pour justifier le palier 2.
    Le trou de `_mettre_a_jour_sommet` calcule `nouveau_cout` avec deux bases
    differentes selon la branche (raccourci vers le grand-parent ou non) ; rien ne
    verifiait que la valeur accumulee reste cohERENTE avec le chemin reellement
    reconstruit. Ce test calcule la longueur INDEPENDAMMENT, par la distance
    euclidienne entre points de passage consecutifs (`math.hypot`, jamais
    `monde.cout_deplacement` : aucune fonction du module sous test n'est reutilisee
    pour produire la valeur attendue), et la compare a `resultat.longueur`.
    """
    monde = _petit_monde(
        largeur=10, hauteur=10,
        obstacle={"colonne_min": 4, "colonne_max": 5, "ligne_min": 0, "ligne_max": 6},
    )
    depart, but = (0, 0), (9, 0)
    resultat = thetastar.planifier(monde, depart, but)
    assert resultat.chemin is not None
    assert len(resultat.chemin) > 2, (
        "le raccourci en ligne de vue doit reellement se produire, sinon ce test ne "
        "distingue pas les deux bases de cout possibles"
    )

    longueur_attendue = sum(
        math.hypot(bx - ax, by - ay) * monde.taille_cellule
        for (ax, ay), (bx, by) in zip(resultat.chemin, resultat.chemin[1:])
    )
    assert resultat.longueur == pytest.approx(longueur_attendue, abs=1e-9)


def test_chemin_theta_ne_traverse_aucune_cellule_occupee_controle_independant(
    segments_traversant_une_cellule_occupee,
):
    """
    Remplace l'ancien `test_chemin_theta_reste_libre_de_collision`, juge CIRCULAIRE par la
    revue finale du 2026-09-19 : il rappelait `monde.ligne_de_vue_libre` sur chaque segment
    du chemin, la MEME fonction que Theta* utilise pour construire ce chemin -- une version
    cassee de `ligne_de_vue_libre` passe donc systematiquement son propre jugement. C'est
    exactement ce qui est arrive : mesure par l'enseignant le 2026-09-20 sur
    planif_config.json (grille 64x64), Theta* traversait l'obstacle sur des segments entiers
    sans qu'aucun test ne le detecte. Le jugement ici est INDEPENDANT
    (`segments_traversant_une_cellule_occupee`, conftest.py) : il echantillonne chaque segment
    en coordonnees reelles et teste `monde.est_occupee` directement, sans jamais appeler
    `ligne_de_vue_libre`.
    """
    monde = _petit_monde(
        largeur=10, hauteur=10,
        obstacle={"colonne_min": 4, "colonne_max": 5, "ligne_min": 0, "ligne_max": 6},
    )
    depart, but = (0, 0), (9, 0)
    resultat = thetastar.planifier(monde, depart, but)
    assert resultat.chemin is not None
    assert segments_traversant_une_cellule_occupee(monde, resultat.chemin) == []


# --------------------------------------------------------------------- chemin d'echec

def test_arrivee_enfermee_ne_rend_rien():
    """Un but completement enferme par des obstacles ne rend jamais un chemin partiel, comme A*."""
    monde = _petit_monde()
    but = (2, 2)
    anneau = [(1, 1), (1, 2), (1, 3), (2, 1), (2, 3), (3, 1), (3, 2), (3, 3)]
    monde.definir_occupation(anneau, True)
    resultat = thetastar.planifier(monde, (0, 0), but)
    assert resultat.chemin is None


def test_depart_hors_grille_leve_une_erreur_explicite():
    """Comme A*, un depart hors grille leve ValueError, jamais un repli sur le bord."""
    monde = _petit_monde()
    with pytest.raises(ValueError, match="hors grille"):
        thetastar.planifier(monde, (-1, 0), (2, 2))


def test_depart_dans_l_obstacle_leve_une_erreur_explicite():
    """
    Comme A* (test_astar.py) : trouve par comparaison avec la reference Aider. Sans ce
    controle, un depart occupe n'etait ni refuse ni detecte par Theta* non plus.
    """
    monde = _petit_monde(obstacle={"colonne_min": 0, "colonne_max": 0, "ligne_min": 0, "ligne_max": 0})
    with pytest.raises(ValueError, match="obstacle"):
        thetastar.planifier(monde, (0, 0), (7, 7))


def test_but_dans_l_obstacle_leve_une_erreur_explicite():
    """Comme A* : un but occupe leve, plutot que de rendre chemin=None comme un but enferme."""
    monde = _petit_monde(obstacle={"colonne_min": 7, "colonne_max": 7, "ligne_min": 7, "ligne_max": 7})
    with pytest.raises(ValueError, match="obstacle"):
        thetastar.planifier(monde, (0, 0), (7, 7))
