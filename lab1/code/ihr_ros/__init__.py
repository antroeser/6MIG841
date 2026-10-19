"""
ihr_ros - Socle commun du solutionnaire 6MIG841 (interaction humain-robot).

Trois etages, utilises par le Lab1, les deux devoirs et le projet :
  - `config`    : toutes les valeurs numeriques, lues dans ihr_config.json,
  - `geometry`  : geometrie plane (angles, caps, conversion image -> turtlesim),
  - `turtle_io` : commande de la tortue, ROS2 reel ou substitut, meme interface.

Voir workflow.md a la racine du depot pour les regles que ce paquet applique.
"""

from .backends.base import Pose, Twist
from .turtle_io import BackendError, TurtleClient, open_turtle, ros2_available

__all__ = [
    "Pose",
    "Twist",
    "TurtleClient",
    "BackendError",
    "open_turtle",
    "ros2_available",
]

__version__ = "1.0.0"
