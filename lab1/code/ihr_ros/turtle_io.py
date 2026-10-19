"""
ihr_ros.turtle_io - Selection de la dorsale et facade de commande de la tortue.

Un seul point d'entree pour les trois travaux :

    from ihr_ros.turtle_io import open_turtle
    with open_turtle() as turtle:
        turtle.drive(linear=2.0, angular=0.0)

La dorsale est choisie ainsi :
  - `IHR_BACKEND=ros2` : exige ROS2, echoue en nommant ce qui manque,
  - `IHR_BACKEND=sim`  : force le substitut,
  - non definie        : ROS2 s'il est importable, sinon le substitut, en le DISANT.

Le repli vers le substitut n'est jamais silencieux. Un etudiant qui croit avoir lance
ROS2 alors qu'il pilote un substitut passerait la seance a debugger une installation
qui n'a jamais ete active.
"""

from __future__ import annotations

import os
import sys
from typing import Callable

from . import config
from .backends.base import Pose, TurtleBackend, Twist

_ENV_VAR = "IHR_BACKEND"
_VALID = ("ros2", "sim", "nav2", "auto")


class BackendError(RuntimeError):
    """Dorsale demandee indisponible."""


def ros2_available() -> tuple[bool, str]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Dire si la pile ROS2 Python est importable, et sinon pourquoi.

    Inputs:
        aucun

    Outputs:
        available (bool): vrai si rclpy, geometry_msgs et turtlesim s'importent
        reason (str): message explicatif, vide si disponible
    --------------------------------------------------------------------------
    """
    missing: list[str] = []
    for module in ("rclpy", "geometry_msgs.msg", "turtlesim.msg"):
        try:
            __import__(module)
        except Exception as exc:  # ImportError, mais aussi erreurs de chargement natif
            missing.append(f"{module} ({type(exc).__name__})")
    if missing:
        return False, "modules ROS2 absents : " + ", ".join(missing)
    return True, ""


def nav2_available() -> tuple[bool, str]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Dire si la pile Nav2 Python est importable, et sinon pourquoi. Distincte
        de ros2_available() : ROS2 seul (rclpy + turtlesim) peut etre present sans
        que navigation2/nav2_simple_commander le soient (spec.md, « Nav2 et SLAM :
        disponibles, non installes »).

    Inputs:
        aucun

    Outputs:
        available (bool): vrai si rclpy et nav2_simple_commander s'importent
        reason (str): message explicatif, vide si disponible
    --------------------------------------------------------------------------
    """
    missing: list[str] = []
    for module in ("rclpy", "nav2_simple_commander.robot_navigator"):
        try:
            __import__(module)
        except Exception as exc:  # ImportError, mais aussi erreurs de chargement natif
            missing.append(f"{module} ({type(exc).__name__})")
    if missing:
        return False, "modules Nav2 absents : " + ", ".join(missing)
    return True, ""


def select_backend_name(requested: str | None = None) -> tuple[str, str]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Decider quelle dorsale utiliser, sans rien instancier. Nav2 n'est
        JAMAIS choisie par 'auto' : elle exige une carte et un robot (reel ou
        simule), ce qu'aucune detection d'importabilite ne peut garantir,
        contrairement au repli ros2/sim (plan07.md, « Nav2 entre comme
        troisieme dorsale »).

    Inputs:
        requested (str | None): 'ros2', 'sim', 'nav2', 'auto' ou None (lit
            IHR_BACKEND)

    Outputs:
        name (str): 'ros2', 'sim' ou 'nav2'
        reason (str): phrase expliquant le choix, destinee a l'utilisateur
    --------------------------------------------------------------------------
    """
    wanted = (requested or os.environ.get(_ENV_VAR) or "auto").strip().lower()
    if wanted not in _VALID:
        raise BackendError(
            f"{_ENV_VAR}='{wanted}' invalide. Valeurs acceptees : {', '.join(_VALID)}."
        )

    if wanted == "nav2":
        available, reason = nav2_available()
        if not available:
            raise BackendError(
                f"Dorsale Nav2 exigee ({_ENV_VAR}=nav2) mais indisponible : {reason}. "
                "Installer navigation2 et nav2-simple-commander dans l'environnement "
                f"conda, ou utiliser {_ENV_VAR}=ros2 pour la dorsale ROS2 ordinaire."
            )
        return "nav2", "Dorsale Nav2 exigee explicitement et disponible."

    available, reason = ros2_available()

    if wanted == "ros2":
        if not available:
            raise BackendError(
                f"Dorsale ROS2 exigee ({_ENV_VAR}=ros2) mais indisponible : {reason}. "
                "Lancer depuis un environnement ROS2 source, ou utiliser "
                f"{_ENV_VAR}=sim pour le substitut."
            )
        return "ros2", "ROS2 exige explicitement et disponible."

    if wanted == "sim":
        return "sim", "Substitut exige explicitement. Ce n'est PAS ROS2."

    if available:
        return "ros2", "ROS2 detecte automatiquement."
    return "sim", (
        f"ROS2 indisponible ({reason}). Repli sur le SUBSTITUT : la tortue affichee "
        "n'est pas turtlesim, et aucun topic ROS2 n'est publie."
    )


class TurtleClient:
    """Facade de commande, independante de la dorsale."""

    def __init__(self, backend: TurtleBackend, reason: str):
        self._backend = backend
        self._reason = reason

    # --------------------------------------------------------------- proprietes

    @property
    def backend(self) -> TurtleBackend:
        return self._backend

    @property
    def is_real_ros2(self) -> bool:
        return self._backend.is_real_ros2

    def banner(self) -> str:
        """
        --------------------------------------------------------------------------
        Purpose:
            Ligne d'annonce a imprimer au demarrage de chaque programme, pour que
            l'utilisateur sache toujours ce qui tourne reellement.

        Inputs:
            aucun

        Outputs:
            banner (str): texte sur une ou deux lignes
        --------------------------------------------------------------------------
        """
        marque = "ROS2" if self._backend.is_real_ros2 else "SUBSTITUT"
        return f"[{marque}] dorsale = {self._backend.name}\n[{marque}] {self._reason}"

    # ------------------------------------------------------------------ actions

    def drive(self, linear: float = 0.0, angular: float = 0.0) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Envoyer une consigne de vitesse a la tortue.

        Inputs:
            linear (float): vitesse lineaire en x, unites turtlesim par seconde
            angular (float): vitesse angulaire en z, radians par seconde

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        self._backend.publish(Twist(float(linear), float(angular)))

    def stop(self) -> None:
        """Immobiliser la tortue."""
        self._backend.stop()

    def pose(self) -> Pose:
        """Derniere pose connue."""
        return self._backend.pose()

    def spin_once(self, timeout_seconds: float = 0.0) -> None:
        """Laisser la dorsale traiter ses evenements."""
        self._backend.spin_once(timeout_seconds)

    def close(self) -> None:
        """Immobiliser puis liberer la dorsale."""
        try:
            self._backend.stop()
        finally:
            self._backend.close()

    def __enter__(self) -> "TurtleClient":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()


def open_turtle(requested: str | None = None,
                node_name: str = "ihr_turtle_client",
                with_window: bool = True,
                announce: Callable[[str], None] | None = print) -> TurtleClient:
    """
    --------------------------------------------------------------------------
    Purpose:
        Ouvrir la tortue avec la dorsale adaptee et annoncer laquelle.

    Inputs:
        requested (str | None): 'ros2', 'sim', 'auto' ou None
        node_name (str): nom du noeud ROS2, ignore par le substitut
        with_window (bool): ouvrir la fenetre du substitut, ignore par ROS2
        announce (callable | None): recoit la banniere, None pour rester muet

    Outputs:
        client (TurtleClient): facade prete a l'emploi
    --------------------------------------------------------------------------
    """
    name, reason = select_backend_name(requested)

    if name == "nav2":
        from .backends.nav2 import Nav2Backend  # noqa: PLC0415

        backend: TurtleBackend = Nav2Backend(node_name=node_name)
    elif name == "ros2":
        from .backends.ros2 import Ros2Backend  # noqa: PLC0415

        backend = Ros2Backend(node_name=node_name)
    else:
        from .backends.sim import SimBackend  # noqa: PLC0415

        backend = SimBackend(with_window=with_window)

    client = TurtleClient(backend, reason)
    if announce is not None:
        announce(client.banner())
    return client


def describe_environment() -> dict[str, object]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Rapport machine sur l'etat de l'environnement, consomme par
        `Lab1/code/check_env.py` et par les tests.

    Inputs:
        aucun

    Outputs:
        report (dict): interpreteur, disponibilite ROS2, dorsale retenue
    --------------------------------------------------------------------------
    """
    available, reason = ros2_available()
    chosen, why = select_backend_name()
    return {
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "config_file": str(config.config_path()),
        "ros2_available": available,
        "ros2_reason": reason,
        "backend_selected": chosen,
        "backend_reason": why,
        "env_override": os.environ.get(_ENV_VAR, ""),
    }
