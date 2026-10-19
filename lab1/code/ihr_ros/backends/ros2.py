"""
ihr_ros.backends.ros2 - Dorsale ROS2 reelle.

C'est la dorsale livree. Elle cree un noeud rclpy, publie des `geometry_msgs/msg/Twist`
sur `/turtle1/cmd_vel` et s'abonne aux `turtlesim/msg/Pose` de `/turtle1/pose`. Le code
des trois travaux ne change pas d'une ligne entre cette dorsale et le substitut.

Elle s'importe uniquement quand rclpy est present. Sur une machine sans ROS2, l'import
echoue avec un message qui nomme ce qui manque, jamais avec un repli silencieux vers le
simulateur : c'est la selection dans `ihr_ros.turtle_io` qui decide, et elle le dit.
"""

from __future__ import annotations

import threading

from .. import config
from .base import Pose, TurtleBackend, Twist


class Ros2Backend(TurtleBackend):
    """Dorsale rclpy + turtlesim."""

    name = "ROS2 (rclpy + turtlesim)"
    is_real_ros2 = True

    def __init__(self, node_name: str = "ihr_turtle_client", args: list[str] | None = None):
        """
        --------------------------------------------------------------------------
        Purpose:
            Initialiser rclpy, creer le noeud, le publisher et le subscriber.

        Inputs:
            node_name (str): nom du noeud ROS2 cree
            args (list[str] | None): arguments passes a rclpy.init

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        import rclpy  # noqa: PLC0415 - import tardif, volontaire
        from geometry_msgs.msg import Twist as TwistMsg  # noqa: PLC0415
        from turtlesim.msg import Pose as PoseMsg  # noqa: PLC0415

        self._rclpy = rclpy
        self._twist_msg_type = TwistMsg

        turtle_cfg = config.section("turtlesim")
        self._lock = threading.RLock()
        self._pose = Pose(
            x=float(turtle_cfg["start_x"]),
            y=float(turtle_cfg["start_y"]),
            theta=float(turtle_cfg["start_theta"]),
        )
        self._pose_received = False
        self._closed = False

        self._owns_context = not rclpy.ok()
        if self._owns_context:
            rclpy.init(args=args)

        self._node = rclpy.create_node(node_name)
        depth = int(turtle_cfg["queue_depth"])
        self._publisher = self._node.create_publisher(
            TwistMsg, str(turtle_cfg["cmd_vel_topic"]), depth
        )
        self._node.create_subscription(
            PoseMsg, str(turtle_cfg["pose_topic"]), self._on_pose, depth
        )

    def _on_pose(self, message) -> None:
        with self._lock:
            self._pose = Pose(
                x=float(message.x),
                y=float(message.y),
                theta=float(message.theta),
                linear_velocity=float(message.linear_velocity),
                angular_velocity=float(message.angular_velocity),
            )
            self._pose_received = True

    def publish(self, twist: Twist) -> None:
        message = self._twist_msg_type()
        message.linear.x = float(twist.linear_x)
        message.angular.z = float(twist.angular_z)
        self._publisher.publish(message)

    def pose(self) -> Pose:
        with self._lock:
            return self._pose

    def pose_received(self) -> bool:
        """
        --------------------------------------------------------------------------
        Purpose:
            Dire si au moins une pose a ete recue. Sans cette question, un programme
            regule sur la pose initiale supposee et croit piloter une tortue qui n'a
            jamais repondu, parce que turtlesim n'est pas lance.

        Inputs:
            aucun

        Outputs:
            received (bool): vrai des la premiere pose recue
        --------------------------------------------------------------------------
        """
        with self._lock:
            return self._pose_received

    def spin_once(self, timeout_seconds: float = 0.0) -> None:
        self._rclpy.spin_once(self._node, timeout_sec=timeout_seconds)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._node.destroy_node()
        finally:
            if self._owns_context and self._rclpy.ok():
                self._rclpy.shutdown()
