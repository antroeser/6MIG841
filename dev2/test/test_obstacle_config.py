"""
test_obstacle_config.py - Devoir 2 : conversion de l'obstacle declare vers turtlesim.

Purement numerique (workflow.md R5) : aucun ROS2, aucun turtlesim, aucun temps reel.
`obstacle_config.py` n'importe que `Lab1/code/planif/world.py` (standard library
seule) et `arcs.py` (Devoir2/code, standard library seule), donc cette suite tourne
dans le `.venv` racine comme le reste des tests hors ligne.

Deux exigences (complement de l'orchestrateur, 2026-09-19) :
  1. la cellule d'obstacle declaree se convertit bien vers la position turtlesim
     attendue, EN PASSANT PAR world.py (World.vers_unites), jamais par une
     arithmetique recopiee ici ;
  2. une cellule hors grille est une erreur explicite nommant la cellule, jamais un
     repli silencieux sur le bord.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPERTOIRE_CODE = Path(__file__).resolve().parent.parent / "code"
if str(_REPERTOIRE_CODE) not in sys.path:
    sys.path.insert(0, str(_REPERTOIRE_CODE))

_LAB1_CODE = Path(__file__).resolve().parents[2] / "Lab1" / "code"
if str(_LAB1_CODE) not in sys.path:
    sys.path.insert(0, str(_LAB1_CODE))

from planif import world  # noqa: E402

from obstacle_config import obstacle_depuis_config  # noqa: E402


def test_obstacle_se_convertit_par_world_vers_unites(cfg):
    """
    L'obstacle declare (devoir2.obstacle) se convertit vers la position turtlesim
    attendue en passant par World.vers_unites, et non par une arithmetique recopiee
    dans obstacle_config.py : la cellule et l'echelle de la configuration REELLE
    sont relues ici independamment, puis comparees a ce qu'obstacle_depuis_config
    a rendu.
    """
    section = cfg["obstacle"]
    grille = world.World()
    x_attendu, y_attendu = grille.vers_unites(
        (int(section["cellule_colonne"]), int(section["cellule_ligne"]))
    )
    echelle = float(section["echelle_grille_vers_turtlesim"])

    obstacle = obstacle_depuis_config(cfg)

    assert obstacle is not None
    assert obstacle.x == pytest.approx(x_attendu * echelle)
    assert obstacle.y == pytest.approx(y_attendu * echelle)
    assert obstacle.rayon == pytest.approx(float(section["rayon"]))


def test_cellule_hors_grille_leve_une_erreur_nommant_la_cellule(cfg):
    """
    Controle negatif : une cellule hors grille (colonne ou ligne au-dela des bornes
    de Lab1/code/planif_config.json) leve CelluleInvalideError en nommant la
    cellule, jamais un repli silencieux sur le bord de la grille.
    """
    section = dict(cfg["obstacle"])
    section["cellule_colonne"] = 999
    config_sans_cellule_valide = dict(cfg)
    config_sans_cellule_valide["obstacle"] = section

    with pytest.raises(world.CelluleInvalideError, match=r"\(999, 7\)"):
        obstacle_depuis_config(config_sans_cellule_valide)


def test_aucune_section_obstacle_rend_none(cfg):
    """
    Controle negatif : une configuration devoir2 SANS section 'obstacle' rend None,
    exactement le comportement d'avant ce plan (aucune collision possible).
    """
    config_sans_obstacle = {cle: valeur for cle, valeur in cfg.items() if cle != "obstacle"}

    assert obstacle_depuis_config(config_sans_obstacle) is None


def test_cle_manquante_dans_obstacle_leve_une_erreur_explicite(cfg):
    """Une section 'obstacle' incomplete (une cle manquante) leve, nommant la cle absente."""
    section_incomplete = {"cellule_colonne": 6, "cellule_ligne": 7}
    config_incomplet = dict(cfg)
    config_incomplet["obstacle"] = section_incomplete

    with pytest.raises(KeyError, match="echelle_grille_vers_turtlesim"):
        obstacle_depuis_config(config_incomplet)
