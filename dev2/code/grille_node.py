"""
grille_node.py - Noeud ROS2 qui affiche le quadrillage 64x64 du Lab 1 pendant le Devoir 2.

Il n'ajoute AUCUN comportement au systeme : il s'abonne a deux topics de pose deja
publies par turtlesim et ne publie rien. Un etudiant peut le retirer du launch sans
changer quoi que ce soit au fonctionnement du Devoir 2.

Pourquoi une fenetre separee plutot qu'un trace dans turtlesim : voir le docstring de
`grille_view.py`, qui porte l'inventaire mesure des services, parametres et topics de
turtlesim. Aucune API de dessin n'y existe.

LE FIL PRINCIPAL. matplotlib, comme tkinter, exige son fil principal sous Windows. Le
pompage de la fenetre vit donc dans `main()`, entre deux `rclpy.spin_once()`, exactement
comme `voice_input_node.main()` pompe la fenetre de saisie vocale. Une version anterieure
de ce depot avait place un pompage equivalent dans un fil de fond et obtenait
`RuntimeError: main thread is not in main loop`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_REPERTOIRE_CODE = Path(__file__).resolve().parent
if str(_REPERTOIRE_CODE) not in sys.path:
    sys.path.insert(0, str(_REPERTOIRE_CODE))
_CODE_LAB1 = _REPERTOIRE_CODE.parent.parent / "Lab1" / "code"
if str(_CODE_LAB1) not in sys.path:
    sys.path.insert(0, str(_CODE_LAB1))

import rclpy  # noqa: E402
from rclpy.node import Node  # noqa: E402
from turtlesim.msg import Pose  # noqa: E402

from ihr_ros import config  # noqa: E402
from planif.world import World, load_config as charger_config_planif  # noqa: E402

from grille_view import VueGrilleDevoir2  # noqa: E402


class GrilleNode(Node):
    """
    S'abonne a la pose de la tortue commandee et a celle de la tortue-obstacle, et
    reporte les deux sur le quadrillage du Lab 1.

    La vue est INJECTEE pour que les tests puissent en fournir une fausse sans ouvrir
    de fenetre ni charger matplotlib (R5).
    """

    def __init__(self, vue: Any, turtlesim_cfg: dict[str, Any],
                 obstacle_cfg: dict[str, Any], node_name: str = "grille"):
        super().__init__(node_name)
        self._vue = vue
        profondeur = int(turtlesim_cfg["queue_depth"])

        self._sub_tortue = self.create_subscription(
            Pose, str(turtlesim_cfg["pose_topic"]), self._on_pose_tortue, profondeur)

        nom_obstacle = str(obstacle_cfg["nom_tortue"])
        self._topic_obstacle = f"/{nom_obstacle}/pose"
        self._sub_obstacle = self.create_subscription(
            Pose, self._topic_obstacle, self._on_pose_obstacle, profondeur)

        self.get_logger().info(
            f"[grille] quadrillage du Lab 1 affiche, abonne a "
            f"{turtlesim_cfg['pose_topic']} et {self._topic_obstacle}."
        )

    def _on_pose_tortue(self, message: Pose) -> None:
        self._vue.maj_tortue(float(message.x), float(message.y), float(message.theta))

    def _on_pose_obstacle(self, message: Pose) -> None:
        self._vue.maj_obstacle(float(message.x), float(message.y))


def main(argv: list[str] | None = None) -> int:
    """
    --------------------------------------------------------------------------
    Purpose:
        Construire la fenetre, faire tourner rclpy et pomper matplotlib sur le FIL
        PRINCIPAL, jusqu'a ce que la fenetre soit fermee ou le noeud interrompu.

    Inputs:
        argv (list | None): arguments ROS2, passes tels quels a rclpy.init

    Outputs:
        code (int): 0 en sortie normale
    --------------------------------------------------------------------------
    """
    reglages = config.section("devoir2")
    turtlesim_cfg = config.section("turtlesim")
    grille_cfg = reglages["grille"]
    obstacle_cfg = reglages["obstacle"]

    planif_cfg = charger_config_planif()
    monde = World(planif_cfg)
    vue = VueGrilleDevoir2(monde, planif_cfg["affichage"], turtlesim_cfg, grille_cfg,
                           obstacle_cfg)
    vue.construire()

    rclpy.init(args=argv)
    noeud = GrilleNode(vue, turtlesim_cfg, obstacle_cfg)
    periode = float(grille_cfg["intervalle_rafraichissement_s"])
    try:
        while rclpy.ok():
            rclpy.spin_once(noeud, timeout_sec=periode)
            vue.pomper()
    except KeyboardInterrupt:
        pass
    finally:
        vue.fermer()
        noeud.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
