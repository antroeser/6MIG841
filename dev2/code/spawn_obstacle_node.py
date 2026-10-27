"""
spawn_obstacle_node.py - Devoir 2 : engendrer la seconde tortue, l'obstacle fixe.

Turtlesim ne dessine pas d'obstacle : ce script en rend un physiquement visible en
engendrant une SECONDE tortue, immobile, a la position que `obstacle_config.py`
calcule depuis devoir2.obstacle (une cellule de la grille de planification du
Lab 1, convertie en unites turtlesim par Lab1/code/planif/world.py). C'est
l'obstacle le plus reel que ce simulateur permette (decision de l'enseignant,
2026-09-19, .sdd/6mig841-ameliorations/obstacle-devoir2-report.md) : ne pas y
substituer une autre representation.

Un seul appel du service `/spawn` de turtlesim, puis le processus se termine :
aucune consigne de vitesse n'est jamais publiee vers la tortue engendree, elle ne
bouge donc jamais. Le service `/spawn` n'existe qu'une fois `turtlesim_node`
demarre (devoir2.launch.py lance les deux en parallele) : ce noeud ATTEND le
service par tentatives bornees (R10, aucune attente non bornee), plutot que de
supposer qu'il est deja la.

Sans obstacle declare (devoir2.obstacle absente ou vide), ce noeud ne fait rien et
se termine normalement (code 0) : c'est le cas normal d'un Devoir 2 sans obstacle,
jamais une erreur.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rclpy  # noqa: E402
from rclpy.node import Node  # noqa: E402
from turtlesim.srv import Spawn  # noqa: E402

from ihr_ros import config  # noqa: E402

from obstacle_config import obstacle_depuis_config  # noqa: E402


def engendrer_obstacle(node: Node, client: Any, settings: dict[str, Any]) -> bool:
    """
    --------------------------------------------------------------------------
    Purpose:
        Attendre le service /spawn par tentatives bornees, puis engendrer la
        tortue-obstacle a la position lue de la configuration. Fonction
        injectable (node, client) pour rester testable hors ligne sans service
        /spawn reel : seule la DECISION (attendre, appeler, se resigner) est
        prouvee ici, jamais le transport ROS2 lui-meme.

    Inputs:
        node (Node): noeud ROS2, pour logger et pour spin_until_future_complete
        client (Any): client du service /spawn (turtlesim.srv.Spawn)
        settings (dict): section 'devoir2' de la configuration

    Outputs:
        engendree (bool): vrai si la tortue-obstacle a ete engendree, faux si
            aucun obstacle n'est declare ou si le service n'est jamais devenu
            disponible
    --------------------------------------------------------------------------
    """
    obstacle = obstacle_depuis_config(settings)
    if obstacle is None:
        node.get_logger().info(
            "devoir2.obstacle absent : aucune tortue-obstacle a engendrer."
        )
        return False

    section = settings["obstacle"]
    timeout = float(section["spawn_timeout_par_tentative_s"])
    tentatives_max = int(section["spawn_tentatives_max"])

    disponible = False
    for tentative in range(1, tentatives_max + 1):
        if client.wait_for_service(timeout_sec=timeout):
            disponible = True
            break
        node.get_logger().warn(
            f"/spawn indisponible, tentative {tentative}/{tentatives_max}."
        )

    if not disponible:
        node.get_logger().error(
            f"/spawn jamais devenu disponible apres {tentatives_max} tentatives "
            f"de {timeout} s : obstacle NON engendre."
        )
        return False

    requete = Spawn.Request()
    requete.x = float(obstacle.x)
    requete.y = float(obstacle.y)
    requete.theta = 0.0
    requete.name = str(section["nom_tortue"])

    futur = client.call_async(requete)
    rclpy.spin_until_future_complete(node, futur, timeout_sec=timeout)

    if not futur.done() or futur.result() is None:
        node.get_logger().error("appel /spawn sans reponse : obstacle NON engendre.")
        return False

    node.get_logger().info(
        f"tortue-obstacle '{futur.result().name}' engendree a "
        f"({obstacle.x:.3f}, {obstacle.y:.3f}), rayon {obstacle.rayon:.2f} "
        "(immobile, aucune consigne ne lui sera jamais publiee)."
    )
    return True


def main(argv: list[str] | None = None) -> int:
    """
    --------------------------------------------------------------------------
    Purpose:
        Point d'entree du noeud : un seul appel /spawn, puis fin du processus.

    Inputs:
        argv (list[str] | None): arguments rclpy, ceux de la ligne de commande
            si absents

    Outputs:
        code (int): 0 dans tous les cas (l'absence d'obstacle ou l'indisponibilite
            du service ne doivent pas faire echouer tout le lancement ROS2)
    --------------------------------------------------------------------------
    """
    rclpy.init(args=argv)
    node = Node("spawn_obstacle_node")
    try:
        devoir2_cfg = config.section("devoir2")
        client = node.create_client(Spawn, "/spawn")
        engendrer_obstacle(node, client, devoir2_cfg)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
