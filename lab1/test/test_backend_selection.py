"""
test_backend_selection.py - Tests de la selection de dorsale (ihr_ros.turtle_io).

Corrige par plan01.md, etape 9 : la version precedente supposait ROS2 absent de la
machine qui lance la suite, une precondition vraie sous le `.venv` mais fausse sous
l'environnement conda ROS2 (les deux sont des interpreteurs legitimes du laboratoire,
voir spec.md). Un test qui suppose une ressource absente au lieu de la SIMULER absente
viole workflow.md R5 ("Les tests ne dependent ... d'une installation ROS2. Ces quatre
ressources sont simulees."). La disponibilite ROS2 est donc forcee par monkeypatch sur
ihr_ros.turtle_io.ros2_available, jamais lue sur la machine reelle, pour que la suite
rende le meme resultat sous les deux interpreteurs.
"""

from __future__ import annotations

import pytest

from ihr_ros import turtle_io
from ihr_ros.turtle_io import BackendError, open_turtle, ros2_available, select_backend_name


def _simuler_ros2_absent(monkeypatch, raison: str = "modules ROS2 absents : rclpy (ModuleNotFoundError)") -> None:
    """Forcer ros2_available() a rendre (False, raison), quelle que soit la machine reelle."""
    monkeypatch.setattr(turtle_io, "ros2_available", lambda: (False, raison))


def test_ros2_available_rend_la_forme_attendue():
    """
    Contrat de ros2_available(), verifiable sur n'importe quelle machine : un couple
    (bool, str), la raison etant non vide exactement quand ROS2 est indisponible.
    Contrairement a l'ancienne version de ce test, aucune valeur precise n'est exigee :
    la disponibilite reelle depend de l'interpreteur (voir plan01.md, etape 9).
    """
    disponible, raison = ros2_available()
    assert isinstance(disponible, bool)
    assert isinstance(raison, str)
    if disponible:
        assert raison == ""
    else:
        assert "rclpy" in raison


def test_backend_ros2_force_leve_backenderror_nommant_ce_qui_manque(monkeypatch):
    """IHR_BACKEND=ros2 explicite, ROS2 simule absent, leve BackendError nommant rclpy."""
    _simuler_ros2_absent(monkeypatch)
    with pytest.raises(BackendError, match="rclpy"):
        select_backend_name(requested="ros2")


def test_backend_invalide_leve_backenderror_listant_les_valeurs_acceptees():
    """Une valeur IHR_BACKEND hors {ros2, sim, nav2, auto} liste les valeurs valides dans l'erreur."""
    with pytest.raises(BackendError) as exc_info:
        select_backend_name(requested="garbage")
    message = str(exc_info.value)
    assert "ros2" in message
    assert "sim" in message
    assert "auto" in message


def test_backend_sim_force_ignore_la_detection_ros2():
    """IHR_BACKEND=sim force le substitut et dit explicitement que ce n'est pas ROS2."""
    nom, raison = select_backend_name(requested="sim")
    assert nom == "sim"
    assert "PAS ROS2" in raison


def test_backend_auto_se_replie_sur_sim_quand_ros2_absent(monkeypatch):
    """En mode auto, ROS2 simule absent, le choix retombe sur 'sim' et l'annonce comme SUBSTITUT."""
    _simuler_ros2_absent(monkeypatch)
    nom, raison = select_backend_name(requested="auto")
    assert nom == "sim"
    assert "SUBSTITUT" in raison


def test_ihr_backend_env_ros2_leve_backenderror(monkeypatch):
    """La variable d'environnement IHR_BACKEND=ros2 produit la meme erreur que le parametre
    explicite, ROS2 simule absent."""
    _simuler_ros2_absent(monkeypatch)
    monkeypatch.setenv("IHR_BACKEND", "ros2")
    with pytest.raises(BackendError, match="rclpy"):
        select_backend_name()


def test_ihr_backend_env_invalide_liste_aussi_les_valeurs_acceptees(monkeypatch):
    """La variable d'environnement IHR_BACKEND, si invalide, liste aussi les valeurs valides."""
    monkeypatch.setenv("IHR_BACKEND", "garbage")
    with pytest.raises(BackendError) as exc_info:
        select_backend_name()
    assert "ros2, sim, nav2, auto" in str(exc_info.value)


def test_ihr_backend_env_absent_retombe_sur_auto(monkeypatch):
    """Sans IHR_BACKEND ni parametre explicite, le comportement par defaut est 'auto', qui
    retombe sur 'sim' quand ROS2 est simule absent."""
    _simuler_ros2_absent(monkeypatch)
    nom, _ = select_backend_name(requested=None)
    assert nom == "sim"


def test_open_turtle_force_le_substitut_et_l_annonce_correctement():
    """open_turtle(requested='sim', with_window=False) ouvre un TurtleClient sur le substitut,
    sans fenetre et sans ROS2 : is_real_ros2 est faux et la banniere le dit."""
    with open_turtle(requested="sim", with_window=False, announce=None) as client:
        assert client.is_real_ros2 is False
        assert "SUBSTITUT" in client.banner()
        client.drive(linear=1.0, angular=0.0)
        client.stop()


# ---------------------------------------------------------------------------
# Nav2 (plan07.md) : troisieme dorsale, jamais choisie par 'auto'.
# ---------------------------------------------------------------------------

def _simuler_nav2_absent(monkeypatch, raison: str = "modules Nav2 absents : "
                                                     "nav2_simple_commander.robot_navigator "
                                                     "(ModuleNotFoundError)") -> None:
    """Forcer nav2_available() a rendre (False, raison), quelle que soit la machine reelle."""
    monkeypatch.setattr(turtle_io, "nav2_available", lambda: (False, raison))


def test_nav2_force_leve_backenderror_nommant_ce_qui_manque(monkeypatch):
    """IHR_BACKEND=nav2 exige Nav2 explicitement ; simule absent, l'erreur nomme le module manquant."""
    _simuler_nav2_absent(monkeypatch)
    with pytest.raises(BackendError, match="nav2_simple_commander"):
        select_backend_name(requested="nav2")


def test_nav2_force_reussit_quand_disponible(monkeypatch):
    """IHR_BACKEND=nav2, Nav2 simule disponible : la dorsale nav2 est retenue."""
    monkeypatch.setattr(turtle_io, "nav2_available", lambda: (True, ""))
    nom, raison = select_backend_name(requested="nav2")
    assert nom == "nav2"
    assert "Nav2" in raison


def test_auto_ne_choisit_jamais_nav2_meme_si_disponible(monkeypatch):
    """
    'auto' ne bascule jamais sur Nav2, meme quand nav2_available() rend vrai : Nav2 exige
    une carte et un robot, ce qu'une simple importabilite ne garantit pas
    (plan07.md, « Nav2 entre comme troisieme dorsale »).
    """
    monkeypatch.setattr(turtle_io, "nav2_available", lambda: (True, ""))
    nom, _ = select_backend_name(requested="auto")
    assert nom != "nav2"
