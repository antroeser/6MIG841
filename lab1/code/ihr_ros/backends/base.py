"""
ihr_ros.backends.base - Contrat commun aux deux dorsales de commande de la tortue.

Une dorsale expose trois verbes seulement : publier une consigne de vitesse, lire la
pose courante, et laisser tourner la boucle interne un instant. Les trois travaux ne
connaissent que ce contrat, jamais rclpy ni le simulateur directement.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass(frozen=True)
class Pose:
    """Pose planaire d'une tortue, en unites turtlesim et en radians."""

    x: float
    y: float
    theta: float
    linear_velocity: float = 0.0
    angular_velocity: float = 0.0


@dataclass(frozen=True)
class Twist:
    """
    Consigne de vitesse. Reproduit les deux seuls champs de geometry_msgs/msg/Twist
    qu'utilise turtlesim : la vitesse lineaire en x et la vitesse angulaire en z.
    """

    linear_x: float = 0.0
    angular_z: float = 0.0


@dataclass(frozen=True)
class ResultatNavigation:
    """
    Resultat d'une tentative d'atteindre une pose absolue (plan07.md, « Nav2 et
    SLAM »). Un ECHEC est une donnee, jamais une exception : la boucle de commande
    de l'appelant doit pouvoir continuer (plan07.md, tableau des tests, « Nav2 en
    echec : rend un echec, ne leve pas »).
    """

    succes: bool
    raison: str = ""


class TurtleBackend(abc.ABC):
    """Dorsale de commande. Implementee par Ros2Backend et SimBackend."""

    #: Nom affiche a l'utilisateur, pour qu'il sache toujours ce qui tourne.
    name: str = "abstract"

    #: Faux pour le simulateur. Un programme qui se croit sur ROS2 alors qu'il est
    #: sur le substitut est la confusion que ce drapeau existe pour empecher.
    is_real_ros2: bool = False

    @abc.abstractmethod
    def publish(self, twist: Twist) -> None:
        """Envoyer une consigne de vitesse a la tortue."""

    @abc.abstractmethod
    def pose(self) -> Pose:
        """Retourner la derniere pose connue de la tortue."""

    @abc.abstractmethod
    def spin_once(self, timeout_seconds: float = 0.0) -> None:
        """Laisser la dorsale traiter ses evenements pendant au plus `timeout_seconds`."""

    @abc.abstractmethod
    def close(self) -> None:
        """Liberer les ressources. Doit pouvoir etre appelee deux fois sans effet."""

    def stop(self) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Immobiliser la tortue. Appelee a la fermeture de chaque programme, car
            turtlesim conserve la derniere consigne recue et continue d'avancer.

        Inputs:
            aucun

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        self.publish(Twist(0.0, 0.0))

    def goto_pose(self, pose: "Pose") -> ResultatNavigation:
        """
        --------------------------------------------------------------------------
        Purpose:
            Aller a une pose absolue (plan07.md, « Nav2 et SLAM »). Implementation
            PAR DEFAUT, heritee par toute dorsale sans planificateur propre : elle
            REFUSE EN NOMMANT SON NOM plutot que de rendre un echec silencieux ou
            un mouvement approximatif. Seule `Nav2Backend` la surcharge : elle SEULE
            porte un planificateur capable d'honorer une pose absolue.

        Inputs:
            pose (Pose): pose visee, unites turtlesim

        Outputs:
            aucune (leve NotImplementedError, nommant la dorsale)
        --------------------------------------------------------------------------
        """
        raise NotImplementedError(
            f"La dorsale '{self.name}' n'a pas de planificateur : elle ne peut pas "
            "honorer une pose absolue. Utiliser la dorsale Nav2, ou les "
            "planificateurs du Lab 1 combines a l'asservissement du Projet "
            "(navigator.py)."
        )

    def __enter__(self) -> "TurtleBackend":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        try:
            self.stop()
        finally:
            self.close()
