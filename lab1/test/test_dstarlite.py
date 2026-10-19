"""
test_dstarlite.py - Tests de planif.dstarlite, palier 3 des trois planificateurs (plan06).

D*-Lite conserve g/rhs entre deux appels : quand une cellule change d'occupation, seules les
cellules dont le cout est reellement affecte sont reexaminees, jamais la grille entiere. Cette
suite verifie que le premier calcul n'invente pas un autre chemin qu'A*, qu'une replanification
apres ajout d'obstacle l'evite reellement, la raison d'etre mesuree du palier (moins de
cellules reexaminees qu'une replanification complete, teste en gras dans le plan, sur la grille
de planif_config.json ou l'obstacle_replanification a ete choisi pour demontrer exactement
cela), et le chemin d'echec exige (depart hors grille, workflow.md R5).
"""

from __future__ import annotations

import pytest

from planif import astar, world
from planif.dstarlite import DStarLite


# --------------------------------------------------------------------- chemin heureux

def test_premier_calcul_dstarlite_egale_la_longueur_d_astar():
    """
    Sans changement, D*-Lite n'invente pas un autre chemin : meme longueur qu'A* sur le
    meme monde (l'ordre exact des points de passage peut differer, la recherche partant du
    but, mais le cout du chemin rendu est identique).
    """
    monde = world.World({
        "grille": {"largeur_cellules": 6, "hauteur_cellules": 6, "taille_cellule": 1.0},
        "obstacle_initial": {"colonne_min": 2, "colonne_max": 2, "ligne_min": 0, "ligne_max": 4},
    })
    depart, but = (0, 0), (5, 0)
    resultat_astar = astar.planifier(monde, depart, but)
    resultat_dstar = DStarLite(monde, depart, but).planifier()
    assert resultat_dstar.chemin is not None
    assert resultat_dstar.chemin[0] == depart
    assert resultat_dstar.chemin[-1] == but
    assert resultat_dstar.longueur == pytest.approx(resultat_astar.longueur)


def test_chemin_dstarlite_ne_traverse_aucune_cellule_occupee_controle_independant(
    segments_traversant_une_cellule_occupee,
):
    """
    Controle independant (`segments_traversant_une_cellule_occupee`, conftest.py), comme
    test_astar.py et test_thetastar.py : chaque segment du chemin est echantillonne en
    coordonnees reelles et teste directement contre `monde.est_occupee`, sans jamais appeler
    `ligne_de_vue_libre` -- D*-Lite ne l'utilise de toute facon pas (ses arêtes suivent les
    aretes de la grille, comme A*), mais la meme preuve est demandee des trois planificateurs.
    """
    monde = world.World({
        "grille": {"largeur_cellules": 8, "hauteur_cellules": 8, "taille_cellule": 1.0},
        "obstacle_initial": {"colonne_min": 3, "colonne_max": 3, "ligne_min": 0, "ligne_max": 5},
    })
    depart, but = (0, 0), (7, 0)
    resultat = DStarLite(monde, depart, but).planifier()
    assert resultat.chemin is not None
    assert segments_traversant_une_cellule_occupee(monde, resultat.chemin) == []


# --------------------------------------------------------------------- non-regression : chasse a l'IndexError
#
# Mesure signalee le 2026-09-20 par l'enseignant sur planif_config.json (grille 64x64,
# depart=(1,1), but=(62,62)) : construire un DStarLite et appeler planifier() levait
# "IndexError: list index out of range". Chasse par mesure (pas par lecture seule) : appel
# direct DStarLite(...).planifier() sur la grille de production (12x10 ET 64x64, avant et
# apres le remplacement de la grille), mettre_a_jour_obstacle avec l'obstacle_replanification
# de production, et une campagne aleatoire de 3000 configurations (grilles 3x3 a 12x12,
# occupation aleatoire, depart/but aleatoires, jusqu'a 3 mises a jour incrementales
# aleatoires chacune) n'ont produit AUCUN IndexError. Les six cas ci-dessous couvrent les
# scenarios les plus probables pour une file de priorite purgee au mauvais moment (but
# occupe apres coup, depart occupe apres coup, but puis depart encercles apres coup, grille
# degeneree 1x1, retrait d'un obstacle jamais ajoute) : aucun ne plante non plus. Ce sont
# donc des tests de couverture pour cette classe de defaut, pas la reproduction du cas exact
# -- voir les reserves du rapport de regression
# (.sdd/6mig841-ameliorations/planificateurs-regression-report.md) : l'IndexError rapporte
# n'a pas ete reproduit malgre cette mesure, et aucun code n'a ete change pour un defaut
# qui ne s'est jamais manifeste (R14 : ne pas inventer un correctif pour un bogue non prouve).

def test_but_occupe_apres_planification_initiale_ne_plante_pas():
    """Occuper le but APRES un premier calcul (mettre_a_jour_obstacle) ne leve jamais,
    contrairement a l'occuper avant construction (ValueError attendu, voir plus bas)."""
    monde = world.World({"grille": {"largeur_cellules": 8, "hauteur_cellules": 8, "taille_cellule": 1.0}})
    depart, but = (0, 0), (7, 7)
    planificateur = DStarLite(monde, depart, but)
    planificateur.planifier()
    resultat = planificateur.mettre_a_jour_obstacle([but], True)
    assert resultat.chemin is None


def test_depart_occupe_apres_planification_initiale_ne_plante_pas():
    """Symetrique du cas precedent : occuper le depart lui-meme apres coup."""
    monde = world.World({"grille": {"largeur_cellules": 8, "hauteur_cellules": 8, "taille_cellule": 1.0}})
    depart, but = (0, 0), (7, 7)
    planificateur = DStarLite(monde, depart, but)
    planificateur.planifier()
    resultat = planificateur.mettre_a_jour_obstacle([depart], True)
    assert resultat.chemin is None


def test_but_encercle_apres_planification_initiale_ne_plante_pas():
    """Encercler completement le but apres coup (au lieu de l'occuper directement) rend
    aussi chemin=None, jamais un IndexError."""
    monde = world.World({"grille": {"largeur_cellules": 8, "hauteur_cellules": 8, "taille_cellule": 1.0}})
    depart, but = (0, 0), (7, 7)
    planificateur = DStarLite(monde, depart, but)
    planificateur.planifier()
    anneau = [(6, 6), (6, 7), (7, 6)]
    resultat = planificateur.mettre_a_jour_obstacle(anneau, True)
    assert resultat.chemin is None


def test_grille_degeneree_1x1_ne_plante_pas():
    """Cas limite degenere : une grille a une seule cellule, depart == but."""
    monde = world.World({"grille": {"largeur_cellules": 1, "hauteur_cellules": 1, "taille_cellule": 1.0}})
    resultat = DStarLite(monde, (0, 0), (0, 0)).planifier()
    assert resultat.chemin == [(0, 0)]


def test_retrait_d_un_obstacle_jamais_ajoute_ne_plante_pas():
    """mettre_a_jour_obstacle(..., occupee=False) sur une cellule deja libre ne rapporte
    aucun changement et ne perturbe pas la replanification suivante."""
    monde = world.World({"grille": {"largeur_cellules": 8, "hauteur_cellules": 8, "taille_cellule": 1.0}})
    depart, but = (0, 0), (7, 7)
    planificateur = DStarLite(monde, depart, but)
    resultat_initial = planificateur.planifier()
    resultat = planificateur.mettre_a_jour_obstacle([(4, 4)], False)
    assert resultat.chemin == resultat_initial.chemin


def test_obstacle_ajoute_puis_replanification_evite_le_nouvel_obstacle():
    """Apres l'ajout d'un obstacle sur le chemin courant, le nouveau chemin l'evite et s'allonge."""
    monde = world.World({"grille": {"largeur_cellules": 8, "hauteur_cellules": 8, "taille_cellule": 1.0}})
    depart, but = (0, 0), (7, 0)
    planificateur = DStarLite(monde, depart, but)
    resultat_initial = planificateur.planifier()

    obstacle = [(3, ligne) for ligne in range(0, 6)]  # colonne 3, lignes 0-5 ; 6-7 restent libres
    resultat_replan = planificateur.mettre_a_jour_obstacle(obstacle, True)

    assert resultat_replan.chemin is not None
    assert all(cellule not in set(obstacle) for cellule in resultat_replan.chemin)
    assert resultat_replan.longueur > resultat_initial.longueur


def test_moins_de_cellules_reexaminees_qu_une_replanification_complete():
    """
    La raison d'etre du palier 3 (plan06, ligne en gras) : sur la grille de
    planif_config.json, ou obstacle_replanification a ete choisi pour ce point precis
    (provenance du fichier de configuration), la mise a jour incrementale de D*-Lite
    reexamine strictement moins de cellules qu'une replanification complete par A* sur le
    meme monde deja modifie.
    """
    monde = world.World()
    depart, but = monde.depart, monde.but
    planificateur = DStarLite(monde, depart, but)
    planificateur.planifier()

    rectangle = world.load_config()["obstacle_replanification"]
    cellules_ajoutees = world.rectangle_vers_cellules(rectangle)
    resultat_dstar_replan = planificateur.mettre_a_jour_obstacle(cellules_ajoutees, True)

    # A* relit le meme monde, deja modifie par D*-Lite : c'est une replanification COMPLETE,
    # sans reutiliser aucun calcul precedent.
    resultat_astar_replan = astar.planifier(monde, depart, but)

    assert resultat_dstar_replan.cellules_reexaminees < resultat_astar_replan.cellules_examinees


def test_obstacle_retire_le_chemin_se_raccourcit_a_nouveau():
    """Le retrait d'un obstacle ajoute rend le chemin a sa longueur initiale."""
    monde = world.World({"grille": {"largeur_cellules": 8, "hauteur_cellules": 8, "taille_cellule": 1.0}})
    depart, but = (0, 0), (7, 0)
    planificateur = DStarLite(monde, depart, but)
    resultat_initial = planificateur.planifier()

    obstacle = [(3, ligne) for ligne in range(0, 6)]
    resultat_avec_obstacle = planificateur.mettre_a_jour_obstacle(obstacle, True)
    resultat_apres_retrait = planificateur.mettre_a_jour_obstacle(obstacle, False)

    assert resultat_apres_retrait.longueur < resultat_avec_obstacle.longueur
    assert resultat_apres_retrait.longueur == pytest.approx(resultat_initial.longueur)


# --------------------------------------------------------------------- chemin d'echec

def test_depart_hors_grille_leve_une_erreur_explicite():
    """Un depart hors grille leve ValueError des la construction, jamais un repli sur le bord."""
    monde = world.World({"grille": {"largeur_cellules": 6, "hauteur_cellules": 6, "taille_cellule": 1.0}})
    with pytest.raises(ValueError, match="hors grille"):
        DStarLite(monde, (-1, 0), (2, 2))


def test_depart_dans_l_obstacle_leve_une_erreur_explicite_des_la_construction():
    """
    Comme A* et Theta* (test_astar.py, test_thetastar.py) : trouve par comparaison avec la
    reference Aider. Avant ce controle, D*-Lite finissait par rendre chemin=None pour un
    depart occupe (effet de bord de _mettre_a_jour_sommet, qui force rhs a l'infini pour une
    cellule occupee), mais sans jamais dire POURQUOI -- indiscernable d'un depart simplement
    inatteignable. La construction leve maintenant explicitement, comme les deux autres.
    """
    monde = world.World({
        "grille": {"largeur_cellules": 6, "hauteur_cellules": 6, "taille_cellule": 1.0},
        "obstacle_initial": {"colonne_min": 0, "colonne_max": 0, "ligne_min": 0, "ligne_max": 0},
    })
    with pytest.raises(ValueError, match="obstacle"):
        DStarLite(monde, (0, 0), (5, 5))


def test_but_dans_l_obstacle_leve_une_erreur_explicite_des_la_construction():
    """Comme le depart : un but occupe leve explicitement des la construction."""
    monde = world.World({
        "grille": {"largeur_cellules": 6, "hauteur_cellules": 6, "taille_cellule": 1.0},
        "obstacle_initial": {"colonne_min": 5, "colonne_max": 5, "ligne_min": 5, "ligne_max": 5},
    })
    with pytest.raises(ValueError, match="obstacle"):
        DStarLite(monde, (0, 0), (5, 5))
