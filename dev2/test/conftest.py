"""
conftest.py - Configuration partagee de la suite de tests du Devoir 2.

Trois responsabilites :
  1. Rendre `state_machine`, `llm_interpreter`, `voice` et `voice_turtle` (fichiers
     simples de Devoir2/code, pas un paquet) importables depuis n'importe quel
     repertoire de travail, sans dependre du cwd d'ou pytest est lance. `ihr_ros` est
     deja importable via son installation editable dans .venv (voir
     Lab1/code/pyproject.toml et Lab1/test/conftest.py) : rien de plus n'est
     necessaire pour lui.
  2. Exposer une fixture `cfg` = section 'devoir2' de la configuration, et garantir
     qu'aucun test ne fuit d'etat via IHR_CONFIG / IHR_BACKEND ni via le cache module
     de ihr_ros.config, meme protocole que Lab1/test/conftest.py (workflow.md R5 : un
     test doit pouvoir tourner seul ou dans la suite complete, avec le meme resultat).
  3. Fournir les faux collaborateurs communs aux tests des cinq noeuds ROS2
     (plan02.md, etape 2) : faux client Ollama, faux client Ollama casse, fausse
     tortue qui n'enregistre que les couples de vitesses recus, fausse voix qui
     n'enregistre que ce qu'on lui dit. Ce fichier n'importe PAS rclpy : ces faux
     sont de purs objets Python, utilisables aussi bien par les tests hors ligne
     existants (test_boucle.py) que par test_noeuds.py, qui sont eux sautes dans le
     .venv (workflow.md R5).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPERTOIRE_CODE = Path(__file__).resolve().parent.parent / "code"
if str(_REPERTOIRE_CODE) not in sys.path:
    sys.path.insert(0, str(_REPERTOIRE_CODE))

from ihr_ros import config  # noqa: E402  (import volontairement apres l'ajustement de sys.path)

_VARIABLES_ENV_A_RESTAURER = ("IHR_CONFIG", "IHR_BACKEND")


@pytest.fixture(autouse=True)
def _restaurer_environnement_ihr():
    """
    Sauvegarde IHR_CONFIG et IHR_BACKEND avant chaque test et les restaure apres, puis
    force un rechargement de la configuration pour purger le cache de ihr_ros.config.

    Sans cela, un test qui redirige IHR_CONFIG vers un fichier temporaire (par exemple
    pour geler sim.tick_seconds dans test_boucle.py) laisserait le cache de `config`
    pointer vers ce fichier temporaire une fois celui-ci detruit par pytest, et le
    test suivant heriterait d'un etat perime.
    """
    valeurs_avant = {nom: os.environ.get(nom) for nom in _VARIABLES_ENV_A_RESTAURER}
    yield
    for nom, valeur in valeurs_avant.items():
        if valeur is None:
            os.environ.pop(nom, None)
        else:
            os.environ[nom] = valeur
    config.load(force_reload=True)


@pytest.fixture
def cfg():
    """Section 'devoir2' de la configuration commune (ihr_config.json), pour tous les tests."""
    return config.section("devoir2")


@pytest.fixture
def topics():
    """Section 'topics' de la configuration (ihr_config.json), pour les tests des noeuds ROS2."""
    return config.section("topics")


@pytest.fixture
def cinematique():
    """Section 'cinematique' de la configuration (ihr_config.json, plan05), pour trajectory.py et arcs.py."""
    return config.section("cinematique")


@pytest.fixture
def turtlesim_cfg():
    """Section 'turtlesim' de la configuration (ihr_config.json)."""
    return config.section("turtlesim")


@pytest.fixture
def faux_ollama():
    """
    Faux client Ollama, une reponse 'avancer' par defaut (plan02.md, etape 2).

    Reexporte `faux_ollama.FauxOllama` (deja utilise par test_llm_interpreter.py et
    test_boucle.py) comme fixture, pour que test_noeuds.py n'ait pas a repeter cette
    construction.
    """
    from faux_ollama import FauxOllama

    return FauxOllama(['{"action": "avancer"}'])


@pytest.fixture
def faux_ollama_casse():
    """Faux client Ollama qui leve a chaque appel (plan02.md, etape 2)."""
    from faux_ollama import OllamaQuiEchoue

    return OllamaQuiEchoue()


class _PoseFactice:
    """Pose factice, memes champs que ihr_ros.backends.base.Pose (x, y, theta)."""

    def __init__(self, x: float = 0.0, y: float = 0.0, theta: float = 0.0) -> None:
        self.x = x
        self.y = y
        self.theta = theta


class _FausseTortue:
    """
    Fausse tortue qui n'enregistre que les couples (linear, angular) recus, sans
    aucune physique (plan02.md, etape 2). Memes methodes que TurtleClient
    (drive/stop/spin_once/close/pose), rien de plus : suffisant pour verifier le
    NOMBRE et la NATURE des consignes Twist publiees par motion_node.executer_etape,
    et pour fournir une pose de depart a motion_node._executer (plan05.md, la
    verification de collision avant chaque etape).
    """

    def __init__(self) -> None:
        self.consignes: list[tuple[float, float]] = []
        self.spins = 0
        self.pose_actuelle = _PoseFactice()

    def drive(self, linear: float = 0.0, angular: float = 0.0) -> None:
        self.consignes.append((linear, angular))

    def stop(self) -> None:
        self.consignes.append((0.0, 0.0))

    def pose(self) -> _PoseFactice:
        return self.pose_actuelle

    def spin_once(self, timeout_seconds: float = 0.0) -> None:
        self.spins += 1

    def close(self) -> None:
        pass


@pytest.fixture
def fausse_tortue():
    """Instance neuve de `_FausseTortue` pour chaque test (plan02.md, etape 2)."""
    return _FausseTortue()


class _FausseVoix:
    """
    Fausse voix qui enregistre ce qu'on lui dit, sans jamais parler pour de vrai
    (plan02.md, etape 2). Memes methodes que SortieVocale (dire/close), rien de
    plus : suffisant pour verifier que voice_output prononce exactement ce qu'il
    recoit, sans decider de rien.
    """

    def __init__(self) -> None:
        self.dites: list[str] = []

    def dire(self, texte: str) -> None:
        self.dites.append(texte)

    def close(self) -> None:
        pass


@pytest.fixture
def fausse_voix():
    """Instance neuve de `_FausseVoix` pour chaque test (plan02.md, etape 2)."""
    return _FausseVoix()
