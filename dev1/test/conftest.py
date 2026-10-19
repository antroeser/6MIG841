"""
conftest.py - Amorce des tests du Devoir 1 (6MIG841).

Rend `thumb_detector` importable depuis `Devoir1/code` sans variable PYTHONPATH, et
expose la section `devoir1` de la configuration commune comme fixture partagee. Le
paquet `ihr_ros` est deja installe en mode editable dans le venv du projet (voir
Lab1/code/ihr_ros) : seul `Devoir1/code` doit etre ajoute a sys.path ici.

Aucune camera, aucun MediaPipe, aucun reseau : voir workflow.md, regle R5.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Devoir1/code doit etre sur sys.path pour que `import thumb_detector` et
# `import detect_thumbs` fonctionnent, quel que soit le repertoire d'ou pytest est
# lance. Insere une seule fois, avant tout import de module de test.
_DEVOIR1_CODE = Path(__file__).resolve().parent.parent / "code"
if str(_DEVOIR1_CODE) not in sys.path:
    sys.path.insert(0, str(_DEVOIR1_CODE))

from ihr_ros import config  # noqa: E402 (apres l'ajustement de sys.path ci-dessus)


@pytest.fixture
def cfg() -> dict:
    """
    --------------------------------------------------------------------------
    Purpose:
        Fournir la section 'devoir1' de ihr_config.json a chaque test. `config`
        met le fichier en cache et rend toujours le meme dict : une copie est
        rendue ici pour qu'un test qui ecrit dedans (voir test_thumb_detector.py,
        cas ValueError) ne contamine jamais le test suivant.

    Inputs:
        aucun

    Outputs:
        section (dict): copie de la section 'devoir1' de la configuration commune
    --------------------------------------------------------------------------
    """
    return dict(config.section("devoir1"))


@pytest.fixture
def emotion_cfg() -> dict:
    """
    --------------------------------------------------------------------------
    Purpose:
        Fournir la sous-section 'devoir1.emotion' de ihr_config.json, la meme
        copie defensive que la fixture `cfg` (voir sa docstring pour la raison).

    Inputs:
        aucun

    Outputs:
        section (dict): copie de la sous-section 'devoir1.emotion'
    --------------------------------------------------------------------------
    """
    return dict(config.section("devoir1")["emotion"])
