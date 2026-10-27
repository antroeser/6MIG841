"""
voice_output_node.py - Devoir 2, noeud ROS2 : sortie vocale (voice_output).

Le plus simple des cinq noeuds (plan02.md, etape 7) : un abonnement au topic
'speak' (section 'topics'), une sortie vocale (voice.SortieVocale, reutilisee
SANS MODIFICATION), aucune decision.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rclpy  # noqa: E402
from rclpy.node import Node  # noqa: E402
from std_msgs.msg import String  # noqa: E402

from ihr_ros import config  # noqa: E402

from voice import SortieVocale  # noqa: E402


class VoiceOutputNode(Node):
    """Abonnement -> synthese vocale. Ne decide rien."""

    def __init__(self, voix: Any | None = None,
                 topics: dict[str, Any] | None = None,
                 context: Any | None = None) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Construire le noeud. La voix est injectable pour les tests hors
            ligne (aucun moteur de synthese reel requis).

        Inputs:
            voix (Any | None): sortie vocale, une vraie SortieVocale si absente
            topics (dict | None): section 'topics' de la configuration
            context (Any | None): contexte rclpy, celui par defaut si absent

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        super().__init__("voice_output", context=context)
        self._topics = topics if topics is not None else config.section("topics")
        if voix is not None:
            self._voix = voix
        else:
            # Les reglages de moteur et de langue viennent de la configuration
            # (devoir2.synthese_vocale, R7) depuis le 2026-09-20 : sans eux, ce
            # noeud parlait francais avec la seule voix que SAPI5 expose ici,
            # TTS_MS_EN-US_ZIRA_11.0 (en-US).
            self._voix = SortieVocale(
                actif=True,
                reglages=config.section("devoir2").get("synthese_vocale", {}),
            )
        self.get_logger().info(f"[voix] {self._voix.description}")

        self._sub_speak = self.create_subscription(
            String, str(self._topics["speak_topic"]),
            self._on_speak, int(self._topics["queue_depth"]),
        )

    def _on_speak(self, message: Any) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Prononcer exactement ce qui est recu. Aucune decision, aucune
            transformation du texte (plan02.md, tableau des responsabilites).

        Inputs:
            message (std_msgs.msg.String): texte a prononcer

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        self._voix.dire(message.data)

    def close(self) -> None:
        """Fermer la sortie vocale. Rappelable sans effet."""
        self._voix.close()


def main(argv: list[str] | None = None) -> int:
    """
    --------------------------------------------------------------------------
    Purpose:
        Point d'entree du noeud.

    Inputs:
        argv (list[str] | None): arguments rclpy, ceux de la ligne de commande
            si absents

    Outputs:
        code (int): code de sortie du processus
    --------------------------------------------------------------------------
    """
    rclpy.init(args=argv)
    node = VoiceOutputNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
