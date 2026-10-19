"""
test_astar.py - Tests de planif.astar, palier 1 des trois planificateurs (plan06).

A* rend le plus court chemin, en escalier (chaque cellule visitee est un point de passage).
Cette suite verifie le chemin heureux (ligne droite, contournement, determinisme) ET les
chemins d'echec exiges : arrivee enfermee, arrivee dans l'obstacle, depart hors grille
(workflow.md R5).
"""

from __future__ import annotations

import math

import pytest

from planif import astar, world


def _petit_monde(largeur=6, hauteur=6) -> world.World:
    """Un petit monde sans obstacle, pour les cas de base."""
    return world.World({"grille": {"largeur_cellules": largeur, "hauteur_cellules": hauteur, "taille_cellule": 1.0}})


# --------------------------------------------------------------------- chemin heureux

def test_chemin_en_ligne_droite_sans_obstacle_ne_fait_aucun_detour():
    """Sans obstacle, la longueur du chemin diagonal egale la distance octile exacte."""
    monde = _petit_monde()
    depart, but = (0, 0), (4, 4)
    resultat = astar.planifier(monde, depart, but)
    assert resultat.chemin is not None
    assert resultat.chemin[0] == depart
    assert resultat.chemin[-1] == but
    assert resultat.longueur == pytest.approx(4 * math.sqrt(2))


def test_obstacle_contourne_le_chemin_existe_et_s_allonge():
    """Un obstacle sur la ligne directe force un detour : le chemin existe et s'allonge."""
    monde = world.World({
        "grille": {"largeur_cellules": 6, "hauteur_cellules": 6, "taille_cellule": 1.0},
        "obstacle_initial": {"colonne_min": 2, "colonne_max": 2, "ligne_min": 0, "ligne_max": 4},
    })
    depart, but = (0, 0), (5, 0)
    resultat = astar.planifier(monde, depart, but)
    assert resultat.chemin is not None
    distance_directe = monde.distance_heuristique(depart, but)
    assert resultat.longueur > distance_directe


def test_chemin_astar_ne_traverse_aucune_cellule_occupee_controle_independant(
    segments_traversant_une_cellule_occupee,
):
    """
    Controle independant (`segments_traversant_une_cellule_occupee`, conftest.py) : chaque
    segment reliant deux points de passage consecutifs du chemin d'A* est echantillonne en
    coordonnees reelles et teste directement contre `monde.est_occupee`, sans jamais appeler
    `ligne_de_vue_libre` (A* ne l'utilise de toute facon pas, mais le meme controle est
    applique aux trois planificateurs pour une preuve symetrique). Sert aussi de reference
    negative : A* n'a jamais montre de traversee reelle a cette precision, seulement un
    artefact d'arrondi flottant dans un controle ad hoc moins prudent (voir le rapport de
    regression, .sdd/6mig841-ameliorations/planificateurs-regression-report.md).
    """
    monde = world.World({
        "grille": {"largeur_cellules": 6, "hauteur_cellules": 6, "taille_cellule": 1.0},
        "obstacle_initial": {"colonne_min": 2, "colonne_max": 2, "ligne_min": 0, "ligne_max": 4},
    })
    depart, but = (0, 0), (5, 0)
    resultat = astar.planifier(monde, depart, but)
    assert resultat.chemin is not None
    assert segments_traversant_une_cellule_occupee(monde, resultat.chemin) == []


def test_deux_executions_identiques_rendent_le_meme_chemin():
    """A cout egal, le depart-egalite est deterministe (R19) : meme chemin a chaque appel."""
    monde = world.World({
        "grille": {"largeur_cellules": 8, "hauteur_cellules": 8, "taille_cellule": 1.0},
        "obstacle_initial": {"colonne_min": 3, "colonne_max": 3, "ligne_min": 0, "ligne_max": 5},
    })
    depart, but = (0, 0), (7, 7)
    premier = astar.planifier(monde, depart, but)
    second = astar.planifier(monde, depart, but)
    assert premier.chemin == second.chemin
    assert premier.longueur == second.longueur


def test_egalite_de_cout_choisit_l_ordre_fixe_des_voisins_pas_un_ordre_stable_quelconque():
    """
    Revue finale (constat Mineur) : le test ci-dessus ne prouve qu'une PURETE de
    fonction -- deux appels identiques a une fonction pure rendent necessairement le
    meme resultat, meme si le departage d'egalite suivait un ordre arbitraire mais
    stable (par exemple l'iteration d'un `set`) au lieu de l'ordre d'insertion voulu
    par R19 (`world._DEPLACEMENTS_8`). Un seul obstacle place exactement entre depart
    et but, avec un espace libre symetrique de part et d'autre, cree une VRAIE egalite
    de cout entre les deux detours (2 pas diagonaux chacun) : voisins((0, 1)) rend,
    dans l'ordre fixe de _DEPLACEMENTS_8, [(1, 2), (0, 2), (0, 0), (1, 0)] -- (1, 2)
    (deplacement (1, 1)) est insere dans le tas AVANT (1, 0) (deplacement (1, -1),
    dernier de la liste), donc le chemin doit passer par (1, 2), jamais par (1, 0).
    Un ordre inverse mais tout aussi stable choisirait (1, 0) et resterait
    indetectable par le test de determinisme ci-dessus.
    """
    monde = world.World({
        "grille": {"largeur_cellules": 3, "hauteur_cellules": 3, "taille_cellule": 1.0},
    })
    monde.definir_occupation([(1, 1)], True)

    assert monde.voisins((0, 1)) == [(1, 2), (0, 2), (0, 0), (1, 0)], (
        "l'ordre fixe des voisins doit rester celui de world._DEPLACEMENTS_8, sinon ce "
        "test ne verifie plus la configuration prevue"
    )

    resultat = astar.planifier(monde, (0, 1), (2, 1))

    assert resultat.chemin is not None
    assert (1, 2) in resultat.chemin, "l'ordre fixe des voisins doit privilegier ce detour"
    assert (1, 0) not in resultat.chemin, (
        "cet autre detour, de cout strictement egal, ne doit etre choisi que par un "
        "ordre de depart-egalite different de celui voulu par R19"
    )


# --------------------------------------------------------------------- chemins d'echec

def test_arrivee_enfermee_ne_rend_rien():
    """Un but completement enferme par des obstacles ne rend jamais un chemin partiel."""
    monde = _petit_monde()
    but = (2, 2)
    anneau = [(1, 1), (1, 2), (1, 3), (2, 1), (2, 3), (3, 1), (3, 2), (3, 3)]
    monde.definir_occupation(anneau, True)
    resultat = astar.planifier(monde, (0, 0), but)
    assert resultat.chemin is None


def test_arrivee_dans_l_obstacle_leve_une_erreur_explicite():
    """
    Un but occupe leve ValueError en le nommant, plutot que de rendre chemin=None comme un
    but simplement enferme (controle negatif du contournement) : les deux echecs ont des
    causes differentes et ne doivent pas etre indiscernables l'un de l'autre. Trouve par
    comparaison avec la reference Aider (planner.py, _validate_start_goal) : avant ce test,
    un but occupe rendait silencieusement chemin=None, exactement comme un but encercle mais
    lui-meme libre -- l'appelant ne pouvait pas distinguer les deux causes.
    """
    monde = world.World({
        "grille": {"largeur_cellules": 6, "hauteur_cellules": 6, "taille_cellule": 1.0},
        "obstacle_initial": {"colonne_min": 4, "colonne_max": 4, "ligne_min": 4, "ligne_max": 4},
    })
    with pytest.raises(ValueError, match="obstacle"):
        astar.planifier(monde, (0, 0), (4, 4))


def test_depart_dans_l_obstacle_leve_une_erreur_explicite():
    """
    Trouve par comparaison avec la reference Aider : avant ce test, un depart occupe
    n'etait NI refuse NI meme detecte -- A* rendait un chemin qui commence sur l'obstacle,
    comme si le robot pouvait legalement s'y trouver (mesure : depart=(0,0) occupe,
    chemin=[(0,0), (1,1), (2,2), (3,3), (4,4), (5,5)] rendu tel quel, sans la moindre
    erreur). C'est le trou le plus serieux trouve par cette comparaison.
    """
    monde = world.World({
        "grille": {"largeur_cellules": 6, "hauteur_cellules": 6, "taille_cellule": 1.0},
        "obstacle_initial": {"colonne_min": 0, "colonne_max": 0, "ligne_min": 0, "ligne_max": 0},
    })
    with pytest.raises(ValueError, match="obstacle"):
        astar.planifier(monde, (0, 0), (5, 5))


def test_depart_hors_grille_leve_une_erreur_explicite():
    """Un depart hors grille leve ValueError, jamais un repli sur le bord."""
    monde = _petit_monde()
    with pytest.raises(ValueError, match="hors grille"):
        astar.planifier(monde, (-1, 0), (2, 2))
