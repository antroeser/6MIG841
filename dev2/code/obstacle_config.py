"""
obstacle_config.py - Devoir 2 : l'obstacle fixe declare en production (2026-09-19).

Jusqu'ici, `MotionNode.obstacle` valait None par defaut et rien en production n'en
passait un (ni devoir2.launch.py, ni ihr_config.json) : le mecanisme de refus de
collision de plan05 (motion_node.verifier_etape_libre, arcs.echantillonner_arc)
n'etait donc jamais exerce qu'en test. Ce module ferme cet ecart : il lit
devoir2.obstacle dans ihr_config.json et le convertit en un arcs.Obstacle exploitable
par motion_node (et par spawn_obstacle_node.py pour engendrer la seconde tortue),
exactement comme motion_node.main() en a besoin.

L'obstacle est une CELLULE de la grille de planification du Lab 1
(Lab1/code/planif/world.py, palier 0 des trois planificateurs), jamais une position
flottante posee sans rapport : la meme grille que le Lab 1 planifie dessus doit
designer le meme obstacle que le Devoir 2 refuse de heurter, sinon l'etudiant ne voit
jamais que la cellule du planificateur et la position de la tortue parlent du meme
monde. La conversion cellule -> unites de grille passe PAR World.vers_unites (jamais
une arithmetique recopiee ici), puis par l'echelle
devoir2.obstacle.echelle_grille_vers_turtlesim (R7 : aucune valeur numerique en dur),
qui rapporte les unites de grille (taille_cellule=1.0, Lab1/code/planif_config.json)
aux unites turtlesim (canvas 11.088, ihr_config.json).

Import DIRECT du module `world`, jamais du paquet `planif` pour un autre usage que
cette importation explicite : `planif/__init__.py` ne charge que la bibliotheque
standard (verifie par lecture, 2026-09-19), donc importer `planif.world` ne tire
jamais matplotlib dans ce noeud ROS2. `Lab1/code` est ajoute a sys.path s'il est
absent, exactement comme Devoir2/test/conftest.py le fait deja pour `ihr_ros`.

Aucun obstacle declare (section 'obstacle' absente de devoir2, ou section vide) est
le cas normal d'un Devoir 2 sans cette section : `obstacle_depuis_config` rend alors
None, et motion_node fonctionne exactement comme avant ce plan (aucune collision
possible, voir arcs.echantillonner_arc, exigence « absence d'obstacle »).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_REPERTOIRE_CODE = Path(__file__).resolve().parent
if str(_REPERTOIRE_CODE) not in sys.path:
    sys.path.insert(0, str(_REPERTOIRE_CODE))

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LAB1_CODE = _REPO_ROOT / "Lab1" / "code"
if str(_LAB1_CODE) not in sys.path:
    sys.path.insert(0, str(_LAB1_CODE))

from planif import world  # noqa: E402  (import volontairement apres l'ajustement de sys.path)

import arcs  # noqa: E402

_CLES_REQUISES = (
    "cellule_colonne", "cellule_ligne", "echelle_grille_vers_turtlesim", "rayon",
)


def obstacle_depuis_config(settings: dict[str, Any]) -> arcs.Obstacle | None:
    """
    --------------------------------------------------------------------------
    Purpose:
        Lire la section 'obstacle' de la configuration devoir2 et la convertir
        en arcs.Obstacle, en passant par World.vers_unites
        (Lab1/code/planif/world.py) pour la cellule declaree. Rend None si la
        section est absente ou vide : c'est le Devoir 2 SANS obstacle,
        motion_node fonctionne alors exactement comme avant ce plan.

    Inputs:
        settings (dict): section 'devoir2' de ihr_config.json (ou tout dict
            portant, ou non, une cle 'obstacle' de meme forme)

    Outputs:
        obstacle (arcs.Obstacle | None): obstacle pret pour motion_node, en
            unites turtlesim, ou None si aucun n'est declare
    --------------------------------------------------------------------------
    """
    section = settings.get("obstacle")
    if not section:
        return None

    absentes = [cle for cle in _CLES_REQUISES if cle not in section]
    if absentes:
        raise KeyError(
            f"Cle(s) {absentes} absente(s) de devoir2.obstacle. "
            f"Cles presentes : {sorted(section)}."
        )

    cellule = (int(section["cellule_colonne"]), int(section["cellule_ligne"]))
    echelle = float(section["echelle_grille_vers_turtlesim"])
    rayon = float(section["rayon"])

    grille = world.World()
    x_grille, y_grille = grille.vers_unites(cellule)

    return arcs.Obstacle(x=x_grille * echelle, y=y_grille * echelle, rayon=rayon)
