"""
test_backend_nav2.py - Preuves de goto_pose (plan07.md, « Nav2 et SLAM »).

Deux dorsales sans planificateur (celles qui heritent du refus par defaut de
TurtleBackend.goto_pose, backends/base.py) et une dorsale Nav2 dont le navigateur, la
dorsale deleguee et l'enveloppe de pose sont tous injectes : aucun Nav2 installe,
aucun rclpy, aucun robot reel (workflow.md R5).
"""

from __future__ import annotations

import math

import pytest

from ihr_ros.backends.base import Pose, ResultatNavigation, TurtleBackend, Twist
from ihr_ros.backends.nav2 import Nav2Backend, construire_pose_cible


class _DorsaleMinimale(TurtleBackend):
    """Dorsale concrete minimale, pour exercer le refus PAR DEFAUT de goto_pose."""

    name = "dorsale-de-test"
    is_real_ros2 = False

    def publish(self, twist: Twist) -> None:
        pass

    def pose(self) -> Pose:
        return Pose(0.0, 0.0, 0.0)

    def spin_once(self, timeout_seconds: float = 0.0) -> None:
        pass

    def close(self) -> None:
        pass


class _DorsaleDelegueeFactice:
    """Fausse dorsale cmd_vel/pose : n'enregistre que ce qu'on lui envoie."""

    def __init__(self) -> None:
        self.twists: list[Twist] = []
        self.spins = 0
        self.fermee = False
        self._pose = Pose(1.0, 2.0, 0.0)

    def publish(self, twist: Twist) -> None:
        self.twists.append(twist)

    def pose(self) -> Pose:
        return self._pose

    def spin_once(self, timeout_seconds: float = 0.0) -> None:
        self.spins += 1

    def close(self) -> None:
        self.fermee = True


class _NavigateurFactice:
    """
    Faux BasicNavigator : rend le resultat demande apres un nombre CHOISI de
    sondages de isTaskComplete(), sans jamais dormir pour de vrai (sleep injecte
    separement dans Nav2Backend).
    """

    def __init__(self, resultat_nom: str = "SUCCEEDED", sondages_avant_fin: int = 2) -> None:
        self.resultat_nom = resultat_nom
        self._sondages_restants = sondages_avant_fin
        self.buts_recus: list[dict] = []

    def goToPose(self, but) -> None:
        self.buts_recus.append(but)

    def isTaskComplete(self) -> bool:
        if self._sondages_restants <= 0:
            return True
        self._sondages_restants -= 1
        return False

    def getResult(self):
        return type("FauxTaskResult", (), {"name": self.resultat_nom})()


def _attentes_comptees():
    """Fonction sleep factice qui compte ses appels, sans jamais dormir pour de vrai."""
    appels: list[float] = []

    def _sleep(duree: float) -> None:
        appels.append(duree)

    _sleep.appels = appels  # type: ignore[attr-defined]
    return _sleep


# ---------------------------------------------------------------------------
# 1. construire_pose_cible : conversion pure, sans ROS.
# ---------------------------------------------------------------------------

def test_construire_pose_cible_theta_nul_est_quaternion_identite():
    cible = construire_pose_cible(Pose(1.0, 2.0, 0.0))
    assert cible["x"] == 1.0
    assert cible["y"] == 2.0
    assert cible["qz"] == pytest.approx(0.0)
    assert cible["qw"] == pytest.approx(1.0)


def test_construire_pose_cible_demi_tour():
    cible = construire_pose_cible(Pose(0.0, 0.0, math.pi))
    assert cible["qz"] == pytest.approx(1.0)
    assert cible["qw"] == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# 2. Dorsale sans planificateur : refuse en NOMMANT SON NOM (test exige par
#    plan07.md, tableau des tests).
# ---------------------------------------------------------------------------

def test_dorsale_sans_planificateur_refuse_goto_pose_en_nommant_son_nom():
    dorsale = _DorsaleMinimale()

    with pytest.raises(NotImplementedError, match="dorsale-de-test"):
        dorsale.goto_pose(Pose(1.0, 1.0, 0.0))


def test_le_refus_par_defaut_nomme_nav2_comme_alternative():
    """Le message doit orienter vers une solution reelle, pas seulement se plaindre."""
    dorsale = _DorsaleMinimale()

    with pytest.raises(NotImplementedError, match="Nav2"):
        dorsale.goto_pose(Pose(0.0, 0.0, 0.0))


# ---------------------------------------------------------------------------
# 3. Nav2Backend delegue cmd_vel/pose/spin_once/close a la dorsale injectee.
# ---------------------------------------------------------------------------

def test_nav2_backend_delegue_publish_pose_spin_close():
    delegue = _DorsaleDelegueeFactice()
    backend = Nav2Backend(delegue=delegue, navigator=_NavigateurFactice())

    backend.publish(Twist(1.0, 0.5))
    backend.spin_once(0.0)
    resultat_pose = backend.pose()
    backend.close()

    assert delegue.twists == [Twist(1.0, 0.5)]
    assert delegue.spins == 1
    assert resultat_pose == Pose(1.0, 2.0, 0.0)
    assert delegue.fermee is True


# ---------------------------------------------------------------------------
# 4. Nav2 en echec : rend un ResultatNavigation, ne LEVE PAS (test exige par
#    plan07.md, tableau des tests).
# ---------------------------------------------------------------------------

def test_nav2_en_echec_rend_un_echec_sans_lever():
    navigateur = _NavigateurFactice(resultat_nom="FAILED", sondages_avant_fin=1)
    backend = Nav2Backend(
        delegue=_DorsaleDelegueeFactice(), navigator=navigateur,
        construire_but=lambda cible: cible, sleep=_attentes_comptees(),
    )

    resultat = backend.goto_pose(Pose(3.0, 4.0, 0.0))  # ne doit lever aucune exception

    assert isinstance(resultat, ResultatNavigation)
    assert resultat.succes is False
    assert "FAILED" in resultat.raison


def test_nav2_en_succes_rend_un_succes():
    navigateur = _NavigateurFactice(resultat_nom="SUCCEEDED", sondages_avant_fin=0)
    backend = Nav2Backend(
        delegue=_DorsaleDelegueeFactice(), navigator=navigateur,
        construire_but=lambda cible: cible, sleep=_attentes_comptees(),
    )

    resultat = backend.goto_pose(Pose(0.0, 0.0, 0.0))

    assert resultat.succes is True
    assert resultat.raison == ""


def test_nav2_attend_la_fin_de_la_tache_en_sondant_isTaskComplete():
    """
    goto_pose ne rend la main qu'une fois isTaskComplete() vrai : la boucle de
    sondage doit avoir dormi exactement le nombre de sondages negatifs annonces
    par le faux navigateur, ni plus ni moins.
    """
    navigateur = _NavigateurFactice(resultat_nom="SUCCEEDED", sondages_avant_fin=3)
    attente = _attentes_comptees()
    backend = Nav2Backend(
        delegue=_DorsaleDelegueeFactice(), navigator=navigateur,
        construire_but=lambda cible: cible, sleep=attente, poll_period_s=0.2,
    )

    backend.goto_pose(Pose(0.0, 0.0, 0.0))

    assert attente.appels == [0.2, 0.2, 0.2]  # type: ignore[attr-defined]


def test_nav2_annule_rend_aussi_un_echec_motive():
    navigateur = _NavigateurFactice(resultat_nom="CANCELED", sondages_avant_fin=0)
    backend = Nav2Backend(
        delegue=_DorsaleDelegueeFactice(), navigator=navigateur,
        construire_but=lambda cible: cible, sleep=_attentes_comptees(),
    )

    resultat = backend.goto_pose(Pose(0.0, 0.0, 0.0))

    assert resultat.succes is False
    assert "CANCELED" in resultat.raison


# ---------------------------------------------------------------------------
# 5. Le but envoye au navigateur porte bien la cible transmise (construire_but
#    injecte, sans jamais toucher a geometry_msgs).
# ---------------------------------------------------------------------------

def test_nav2_transmet_la_cible_au_navigateur_via_construire_but():
    navigateur = _NavigateurFactice(resultat_nom="SUCCEEDED", sondages_avant_fin=0)
    backend = Nav2Backend(
        delegue=_DorsaleDelegueeFactice(), navigator=navigateur,
        construire_but=lambda cible: cible, sleep=_attentes_comptees(),
    )

    backend.goto_pose(Pose(2.5, -1.5, math.pi / 2))

    assert len(navigateur.buts_recus) == 1
    but = navigateur.buts_recus[0]
    assert but["x"] == pytest.approx(2.5)
    assert but["y"] == pytest.approx(-1.5)
