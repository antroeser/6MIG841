"""
ihr_ros.backends.nav2 - Dorsale Nav2 : planifie ET commande une pose absolue.

Troisieme dorsale derriere `turtle_io` (plan07.md, « Nav2 et SLAM » ; spec.md, « Nav2
et SLAM : disponibles, non installes »), a cote du substitut et de turtlesim. Elle est
la SEULE des trois a surcharger `TurtleBackend.goto_pose` (backends/base.py) : les
deux autres heritent du refus par defaut, qui nomme leur propre nom plutot que de
rendre un echec silencieux.

Pour tout le reste (consigne de vitesse continue, arbitree par le Projet), cette
dorsale DELEGUE a une dorsale ROS2 ordinaire : Nav2 ne remplace pas le chemin
cmd_vel/pose deja prouve (backends/ros2.py), il ajoute par-dessus la capacite
d'atteindre une pose absolue. C'est ce que veut dire le tableau de plan07.md :
« Nav2 | Nav2 planifie | Nav2 commande » ne s'applique qu'a CETTE capacite.

Le navigateur (`BasicNavigator` de `nav2_simple_commander`, l'API que documente Nav2 ;
spec.md l'a arretee plutot qu'un client d'action brut sur NavigateToPose) et la
dorsale deleguee sont tous deux injectables, pour que la suite de tests tourne sans
Nav2 installe et sans robot reel (plan07.md, tableau des tests : « Nav2 en echec :
rend un echec, ne leve pas », « dorsale sans planificateur : refuse en nommant son
nom »).
"""

from __future__ import annotations

import math
import time
from typing import Any, Callable

from .base import Pose, ResultatNavigation, TurtleBackend, Twist
from .ros2 import Ros2Backend


def construire_pose_cible(pose: Pose) -> dict[str, float]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Convertir une pose (x, y, theta) en une cible independante de ROS (un
        dict portant x, y et le quaternion de lacet pur), pour que la conversion
        reste testable sans importer geometry_msgs.

    Inputs:
        pose (Pose): pose visee, unites turtlesim, theta en radians

    Outputs:
        cible (dict): x, y, qz, qw (rotation pure autour de l'axe z)
    --------------------------------------------------------------------------
    """
    demi_angle = float(pose.theta) / 2.0
    return {
        "x": float(pose.x),
        "y": float(pose.y),
        "qz": math.sin(demi_angle),
        "qw": math.cos(demi_angle),
    }


class Nav2Backend(TurtleBackend):
    """Dorsale Nav2 : cmd_vel/pose delegues, pose absolue via BasicNavigator."""

    name = "Nav2 (nav2_simple_commander + rclpy)"
    is_real_ros2 = True

    def __init__(self,
                 node_name: str = "ihr_turtle_client_nav2",
                 delegue: TurtleBackend | None = None,
                 navigator: Any | None = None,
                 construire_but: Callable[[dict[str, float]], Any] | None = None,
                 poll_period_s: float = 0.1,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Ouvrir la dorsale ROS2 ordinaire (cmd_vel/pose) et preparer le
            navigateur Nav2. Les trois collaborateurs externes sont injectables
            pour les tests hors ligne (workflow.md R5) : aucun n'est construit
            reellement quand une valeur est fournie.

        Inputs:
            node_name (str): nom du noeud ROS2 de la dorsale deleguee
            delegue (TurtleBackend | None): dorsale cmd_vel/pose, un vrai
                Ros2Backend si absente (chemin de production, exige rclpy)
            navigator (Any | None): objet portant goToPose/isTaskComplete/
                getResult, un vrai BasicNavigator si absent (chemin de
                production, exige nav2_simple_commander)
            construire_but (callable | None): transforme une cible (dict) en
                objet attendu par `navigator.goToPose` ; enveloppe dans un
                PoseStamped ROS2 reel si absente
            poll_period_s (float): periode d'attente entre deux verifications
                de isTaskComplete()
            sleep (callable): fonction d'attente, injectee pour les tests

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        self._delegue = delegue if delegue is not None else Ros2Backend(node_name=node_name)
        self._poll_period = float(poll_period_s)
        self._sleep = sleep
        self._construire_but_fn = (
            construire_but if construire_but is not None else self._pose_stamped_depuis_cible
        )

        if navigator is not None:
            self._navigator = navigator
        else:
            from nav2_simple_commander.robot_navigator import BasicNavigator  # noqa: PLC0415

            self._navigator = BasicNavigator()
            self._navigator.waitUntilNav2Active()

    # ------------------------------------------------------------------ contrat
    def publish(self, twist: Twist) -> None:
        self._delegue.publish(twist)

    def pose(self) -> Pose:
        return self._delegue.pose()

    def spin_once(self, timeout_seconds: float = 0.0) -> None:
        self._delegue.spin_once(timeout_seconds)

    def close(self) -> None:
        self._delegue.close()

    # ------------------------------------------------------------- Nav2 seul
    def goto_pose(self, pose: Pose) -> ResultatNavigation:
        """
        --------------------------------------------------------------------------
        Purpose:
            Envoyer une pose absolue a Nav2 et attendre son verdict. Un ECHEC
            Nav2 (planification impossible, controleur bloque, but annule) est
            rendu comme un ResultatNavigation, JAMAIS leve (plan07.md, tableau
            des tests : « Nav2 en echec : rend un echec, ne leve pas ») : la
            boucle de commande de l'appelant doit pouvoir continuer.

        Inputs:
            pose (Pose): pose visee, unites turtlesim

        Outputs:
            resultat (ResultatNavigation): succes, ou echec motive par le nom du
                TaskResult rendu par Nav2
        --------------------------------------------------------------------------
        """
        cible = construire_pose_cible(pose)
        but = self._construire_but_fn(cible)
        self._navigator.goToPose(but)

        while not self._navigator.isTaskComplete():
            self._sleep(self._poll_period)

        resultat = self._navigator.getResult()
        nom = getattr(resultat, "name", str(resultat))
        if nom == "SUCCEEDED":
            return ResultatNavigation(True, "")
        return ResultatNavigation(
            False, f"Nav2 a rendu {nom} pour la pose demandee (x={cible['x']:.2f}, "
                  f"y={cible['y']:.2f})."
        )

    @staticmethod
    def _pose_stamped_depuis_cible(cible: dict[str, float]) -> Any:
        """
        --------------------------------------------------------------------------
        Purpose:
            Envelopper une cible (x, y, qz, qw) dans un PoseStamped ROS2 reel.
            Fonction separee de goto_pose pour que celui-ci reste testable hors
            ligne : les tests injectent `construire_but`, qui n'a jamais besoin
            d'importer geometry_msgs.

        Inputs:
            cible (dict): x, y, qz, qw

        Outputs:
            but (geometry_msgs.msg.PoseStamped): pose prete pour goToPose
        --------------------------------------------------------------------------
        """
        from geometry_msgs.msg import PoseStamped  # noqa: PLC0415

        but = PoseStamped()
        but.header.frame_id = "map"
        but.pose.position.x = cible["x"]
        but.pose.position.y = cible["y"]
        but.pose.orientation.z = cible["qz"]
        but.pose.orientation.w = cible["qw"]
        return but
