"""
test_sim_backend.py - Tests physiques du substitut de turtlesim (ihr_ros.backends.sim).

Deterministe et sans fenetre (with_window=False partout, aucune camera, aucun ROS2) :
`integrate()` est teste comme fonction pure avec un dt explicite, et SimBackend recoit
une horloge factice injectee via `clock=`, jamais time.sleep.

Piege evite : le thread de fond de SimBackend (`_run`) boucle sur
`threading.Event.wait(self._tick)`, qui attend un temps REEL, jamais l'horloge factice.
Avec le tick_seconds reel (0.05 s), ce thread se reveillerait pendant la duree d'un test
et pourrait appeler `step()` de maniere non controlee entre deux appels explicites du
test. La fixture `config_isolee` neutralise ce risque en gonflant sim.tick_seconds a
3600 s dans une config de test isolee : `Event.wait(3600)` retourne immediatement des
que `close()` appelle `.set()`, donc aucune attente reelle n'a lieu, et le thread de fond
ne peut plus interferer avec les pas explicites `step(dt, now)` du test.
"""

from __future__ import annotations

import json
import math

import pytest

from ihr_ros import config
from ihr_ros.backends.base import Pose, Twist
from ihr_ros.backends.sim import SimBackend, integrate


class HorlogeFactice:
    """Horloge pilotee a la main : aucun appel a time.monotonic ni a time.sleep."""

    def __init__(self, depart: float = 0.0) -> None:
        self.temps = depart

    def __call__(self) -> float:
        return self.temps

    def avancer(self, delta: float) -> None:
        self.temps += delta


def _pose_depart(x: float = 5.544, y: float = 5.544, theta: float = 0.0) -> Pose:
    """Pose de reference : centre du canevas turtlesim, cap 0 (pose de depart reelle)."""
    return Pose(x=x, y=y, theta=theta)


@pytest.fixture
def config_isolee(tmp_path, monkeypatch):
    """Copie ihr_config.json en gonflant sim.tick_seconds a 3600 s (voir en-tete du module)."""
    chemin_reel = config.config_path()
    donnees = json.loads(chemin_reel.read_text(encoding="utf-8"))
    donnees["sim"]["tick_seconds"] = 3600.0
    chemin_test = tmp_path / "config_sim_test.json"
    chemin_test.write_text(json.dumps(donnees), encoding="utf-8")
    monkeypatch.setenv("IHR_CONFIG", str(chemin_test))
    config.load(force_reload=True)
    return donnees


@pytest.fixture
def dorsale(config_isolee):
    """Une SimBackend sans fenetre, horloge factice partant de t=0, fermee en fin de test."""
    horloge = HorlogeFactice(0.0)
    backend = SimBackend(with_window=False, clock=horloge)
    try:
        yield backend, horloge
    finally:
        backend.close()


# --------------------------------------------------------------------- integrate() pure

def test_integrate_ligne_droite_selon_plus_x():
    """dt=0.5, linear=2.0, theta=0 : x = 5.544 + 2.0*cos(0)*0.5 = 6.544 (exemple de la consigne)."""
    arrivee = integrate(_pose_depart(), Twist(2.0, 0.0), 0.5, 11.088, 11.088)
    assert arrivee.x == pytest.approx(6.544)
    assert arrivee.y == pytest.approx(5.544)
    assert arrivee.theta == pytest.approx(0.0)


def test_integrate_rotation_pure_ne_deplace_ni_x_ni_y():
    """angular=1.0 rad/s, dt=0.3, linear=0 : theta avance de 0.3, x et y ne bougent pas."""
    arrivee = integrate(_pose_depart(), Twist(0.0, 1.0), 0.3, 11.088, 11.088)
    assert arrivee.theta == pytest.approx(0.3)
    assert arrivee.x == pytest.approx(5.544)
    assert arrivee.y == pytest.approx(5.544)


def test_integrate_angle_reste_dans_l_intervalle_apres_de_nombreuses_rotations():
    """Invariant : apres 50 pas de rotation cumulee, theta reste toujours dans [-pi, pi]."""
    pose = _pose_depart()
    for _ in range(50):
        pose = integrate(pose, Twist(0.0, 5.0), 0.7, 11.088, 11.088)
        assert -math.pi <= pose.theta <= math.pi


def test_integrate_borne_x_au_mur_du_canevas():
    """Une vitesse enorme vers +x est bornee a canvas_width : la tortue ne sort pas du canevas."""
    arrivee = integrate(_pose_depart(), Twist(1000.0, 0.0), 100.0, 11.088, 11.088)
    assert arrivee.x == pytest.approx(11.088)
    assert arrivee.x <= 11.088


# --------------------------------------------------------------------- SimBackend, pas explicites

def test_simbackend_pose_initiale_vient_de_la_configuration(dorsale):
    """A la construction, la pose de SimBackend reprend start_x/start_y/start_theta de la config."""
    backend, _ = dorsale
    pose = backend.pose()
    assert pose.x == pytest.approx(5.544)
    assert pose.y == pytest.approx(5.544)
    assert pose.theta == pytest.approx(0.0)


def test_simbackend_ligne_droite_avec_step_explicite(dorsale):
    """publish() puis step(dt=0.5, now=0.5) avance x exactement comme integrate() pur (6.544)."""
    backend, _ = dorsale
    backend.publish(Twist(2.0, 0.0))
    pose = backend.step(0.5, now=0.5)
    assert pose.x == pytest.approx(6.544)
    assert pose.y == pytest.approx(5.544)


def test_simbackend_rotation_pure_ne_deplace_pas_la_tortue(dorsale):
    """Une consigne purement angulaire change theta sans deplacer x ni y."""
    backend, _ = dorsale
    backend.publish(Twist(0.0, 1.0))
    pose = backend.step(0.3, now=0.3)
    assert pose.theta == pytest.approx(0.3)
    assert pose.x == pytest.approx(5.544)
    assert pose.y == pytest.approx(5.544)


def test_simbackend_clamp_au_mur_du_canevas(dorsale, config_isolee):
    """Foncer vers le mur ne fait jamais depasser canvas_width : la tortue s'arrete au mur.

    now=0.5 reste dans cmd_timeout_seconds (1.0) par rapport a la consigne publiee a t=0,
    de sorte que seul le mur du canevas explique le plafonnement, pas une remise a zero de
    la consigne pour cause de timeout (piege verifie manuellement lors de l'ecriture)."""
    backend, _ = dorsale
    largeur = config_isolee["turtlesim"]["canvas_width"]
    backend.publish(Twist(1000.0, 0.0))
    pose = backend.step(100.0, now=0.5)
    assert pose.x == pytest.approx(largeur)
    assert pose.x <= largeur


def test_simbackend_consigne_rafraichie_avant_expiration_continue_le_mouvement(dorsale):
    """Republier la meme consigne AVANT le timeout garde la tortue en mouvement (sens 1/2)."""
    backend, horloge = dorsale
    backend.publish(Twist(2.0, 0.0))          # t=0, last_command_at=0
    pose_1 = backend.step(0.5, now=0.5)        # 0.5-0=0.5 < cmd_timeout(1.0) : encore actif
    horloge.avancer(0.5)                       # t=0.5
    backend.publish(Twist(2.0, 0.0))           # rafraichit last_command_at a 0.5
    pose_2 = backend.step(0.5, now=1.0)        # 1.0-0.5=0.5 < 1.0 : toujours actif
    assert pose_2.x > pose_1.x
    assert pose_2.x == pytest.approx(pose_1.x + 1.0)


def test_simbackend_consigne_plus_vieille_que_le_timeout_immobilise_la_tortue(dorsale):
    """Une consigne non renouvelee au-dela de cmd_timeout_seconds est mise a zero (sens 2/2)."""
    backend, _ = dorsale
    backend.publish(Twist(2.0, 0.0))            # t=0, jamais rafraichie ensuite
    pose_avant = backend.step(0.5, now=0.5)      # 0.5-0=0.5 < 1.0 : encore dans le timeout
    pose_apres = backend.step(0.5, now=1.5)      # 1.5-0=1.5 > 1.0 : consigne remise a zero
    assert pose_apres.x == pytest.approx(pose_avant.x)
    assert pose_apres.linear_velocity == pytest.approx(0.0)


# --------------------------------------------------------------------- chemins d'echec / robustesse

def test_simbackend_close_est_idempotente(dorsale):
    """close() appelee deux fois ne doit jamais lever (contrat de TurtleBackend.close)."""
    backend, _ = dorsale
    backend.close()
    backend.close()  # ne doit pas lever d'exception


def test_simbackend_spin_once_sans_fenetre_ne_touche_jamais_a_tkinter(dorsale):
    """with_window=False : spin_once() ne doit ni ouvrir de fenetre ni lever d'exception."""
    backend, _ = dorsale
    resultat = backend.spin_once(0.0)
    assert resultat is None
