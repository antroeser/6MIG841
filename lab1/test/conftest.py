"""
conftest.py - Configuration partagee de la suite de tests Lab1.

Trois responsabilites :
  1. Rendre `ihr_ros` (deja installe en mode editable dans .venv) ET `extract_libs.py`
     (script simple a la racine de Lab1/code, pas un paquet) importables depuis
     n'importe quel repertoire de travail, sans dependre du cwd d'ou pytest est lance.
  2. Garantir qu'aucun test ne fuit d'etat via les variables d'environnement IHR_CONFIG /
     IHR_BACKEND ni via le cache module de ihr_ros.config (workflow.md R5 : un test doit
     pouvoir tourner seul ou dans la suite complete, avec le meme resultat).
  3. Meme garantie pour PLANIF_CONFIG et le cache de planif.world (plan06 : les trois
     planificateurs du Lab 1 lisent une configuration separee, planif_config.json).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Lab1/code doit etre sur sys.path pour `import extract_libs` et `import planif`. `ihr_ros`
# est deja importable via l'installation editable
# (.venv/Lib/site-packages/__editable__.ihr_ros*), mais l'ajouter ici ne cause aucun
# conflit et rend ce fichier autosuffisant.
_REPERTOIRE_CODE = Path(__file__).resolve().parent.parent / "code"
if str(_REPERTOIRE_CODE) not in sys.path:
    sys.path.insert(0, str(_REPERTOIRE_CODE))

from ihr_ros import config  # noqa: E402  (import volontairement apres l'ajustement de sys.path)
from planif import world as planif_world  # noqa: E402  (meme raison)

_VARIABLES_ENV_A_RESTAURER = ("IHR_CONFIG", "IHR_BACKEND", "PLANIF_CONFIG")

# Tolerance relative a une frontiere de cellule (fraction de taille_cellule) : un echantillon
# tombant a moins de cette distance d'une frontiere entiere est ignore plutot que classe dans
# une cellule, pour ne pas confondre une erreur d'arrondi flottant (ax + (bx-ax)*t peut
# retomber a 1e-13 pres d'un bord entier sans jamais y etre exactement) avec une traversee
# reelle. Bien plus petite qu'une cellule (donc ne masque aucune vraie traversee) et bien plus
# grande que l'erreur flottant typique d'une somme de quelques multiplications (~1e-13).
_TOLERANCE_FRONTIERE = 1e-6


def _controle_ligne_de_vue_independant(
    monde: "planif_world.World", chemin: list[tuple[int, int]], echantillons: int = 2000
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Controle INDEPENDANT de `World.ligne_de_vue_libre` : jamais appelee ici (aucun
        import, aucun appel). Echantillonne chaque segment du chemin en coordonnees reelles
        et teste directement `monde.est_occupee` sur la cellule de chaque echantillon
        interieur, par un chemin de calcul entierement distinct de l'algorithme de
        Bresenham sous test (parametrage continu t dans [0, 1] plutot que pas entiers).

        Expose comme fixture pytest (`segments_traversant_une_cellule_occupee` ci-dessous)
        plutot qu'importee directement : plusieurs suites Lab1/test partagent une seule
        `conftest.py` par repertoire, et lancer pytest sur PLUSIEURS repertoires de tests a
        la fois (Lab1/test, Devoir1/test, Devoir2/test, ...) fait collisionner leurs modules
        `conftest` sous le meme nom d'import quand aucun n'est un paquet (pas de
        `__init__.py`) -- `from conftest import ...` resout alors parfois vers LE MAUVAIS
        fichier. Le mecanisme de fixture de pytest, lui, reste correctement scope par
        repertoire.

    Inputs:
        monde (World): grille et occupation a tester
        chemin (list[Cellule]): points de passage consecutifs d'un resultat de planification
        echantillons (int): nombre de points testes par segment (par defaut 2000)

    Outputs:
        segments (list[tuple[Cellule, Cellule]]): les segments (a, b) dont au moins un
            echantillon interieur (hors tolerance de frontiere) tombe sur une cellule occupee
    --------------------------------------------------------------------------
    """
    segments: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for a, b in zip(chemin, chemin[1:]):
        ax, ay = monde.vers_unites(a)
        bx, by = monde.vers_unites(b)
        traverse = False
        for k in range(echantillons + 1):
            t = k / echantillons
            x = ax + (bx - ax) * t
            y = ay + (by - ay) * t
            cx = (x - monde.origine_x) / monde.taille_cellule
            cy = (y - monde.origine_y) / monde.taille_cellule
            if abs(cx - round(cx)) < _TOLERANCE_FRONTIERE or abs(cy - round(cy)) < _TOLERANCE_FRONTIERE:
                continue  # trop pres d'une frontiere de cellule : ambigu, pas une traversee
            cellule = (int(cx // 1), int(cy // 1))
            if not monde.est_dans_la_grille(cellule):
                continue
            if monde.est_occupee(cellule):
                traverse = True
                break
        if traverse:
            segments.append((a, b))
    return segments


@pytest.fixture
def segments_traversant_une_cellule_occupee():
    """Fixture pytest exposant `_controle_ligne_de_vue_independant` (voir sa docstring pour
    le motif : eviter la collision d'import entre les `conftest.py` de plusieurs repertoires
    de test lorsque pytest est lance sur plusieurs d'entre eux a la fois)."""
    return _controle_ligne_de_vue_independant


@pytest.fixture(autouse=True)
def _restaurer_environnement_ihr():
    """
    Sauvegarde IHR_CONFIG, IHR_BACKEND et PLANIF_CONFIG avant chaque test et les restaure
    apres, puis force un rechargement des deux configurations pour purger leurs caches.

    Sans cela, un test qui redirige IHR_CONFIG ou PLANIF_CONFIG vers un fichier temporaire
    (via monkeypatch) laisserait le cache pointer vers ce fichier temporaire une fois
    celui-ci detruit par pytest, et le test suivant heriterait d'un etat perime.
    """
    valeurs_avant = {nom: os.environ.get(nom) for nom in _VARIABLES_ENV_A_RESTAURER}
    yield
    for nom, valeur in valeurs_avant.items():
        if valeur is None:
            os.environ.pop(nom, None)
        else:
            os.environ[nom] = valeur
    config.load(force_reload=True)
    planif_world.load_config(force_reload=True)
