"""
llm_node.py - Devoir 2, noeud ROS2 : service d'interpretation par la LLM.

Sert le service Interpret (section 'topics', cle 'interpret_service') : une
commande entre, un tableau d'etapes sort (plan02.md, tableau des
responsabilites : « servir l'interpretation, rendre un tableau d'etapes »).
Ce noeud NE TOUCHE PAS a la tortue. Toute la traduction reste dans
`llm_interpreter.LlmInterpreter`, reutilise SANS MODIFICATION.

Le rappel du service bloque une a deux secondes sur l'appel a la LLM. C'est
acceptable pour un service appele une fois par tour de dialogue, mais cela
EXIGE un executeur multifil avec un groupe de rappels reentrant (voir main()),
sans quoi le noeud ne pourrait pas etre arrete pendant un appel en cours.

Le sens par booleen et la sequence (plan04, ameliorations A et C). Depuis que
`LlmInterpreter.interpreter()` rend un `Plan` (une ou plusieurs `Action`, chacune
portant `distance_m`, `angle_deg`, `is_forward` et `is_clockwise` DEJA decides par
`state_machine.signer()`), ce noeud construit UN Step PAR ETAPE du plan et y copie
ces quatre champs directement. C'est la source UNIQUE de ces booleens : rien en aval
(dialogue_manager, motion_node) ne les redevine plus depuis un nom d'action ou une
valeur de configuration, ce qui evite exactement la double derivation que ce module
mettait en garde avant plan04.

L'historique (plan04, amelioration B). `request.historique` (le tableau brut transmis
par dialogue_manager) est mis en forme ici via `history.formater_lignes` avant d'etre
passe a `LlmInterpreter.interpreter(..., historique=...)` : c'est ce noeud, seul a
parler au modele, qui assemble l'invite finale.

Mise en train au demarrage (correctif du 2026-09-20)
------------------------------------------------------
`LlmInterpreter.demarrer()` est appelee une fois, ici, juste apres la
construction du traducteur : elle force le chargement du modele Ollama en VRAM
et sa residence (`devoir2.llm_keep_alive`) avant la premiere requete reelle,
corrigeant une VRAM mesuree VIDE au demarrage (defaut 2,
.sdd/6mig841-ameliorations/vram-et-transcription-report.md). N'eleve jamais :
un demon injoignable a ce moment ne doit pas empecher le noeud de demarrer.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rclpy  # noqa: E402
from rclpy.callback_groups import ReentrantCallbackGroup  # noqa: E402
from rclpy.executors import MultiThreadedExecutor  # noqa: E402
from rclpy.node import Node  # noqa: E402

from ihr_6mig841_interfaces.msg import Step  # noqa: E402
from ihr_6mig841_interfaces.srv import Interpret  # noqa: E402

from ihr_ros import config  # noqa: E402

from history import formater_lignes  # noqa: E402
from llm_interpreter import LlmInterpreter  # noqa: E402


class LlmNode(Node):
    """Serveur du service Interpret, adosse a LlmInterpreter."""

    def __init__(self, interprete: LlmInterpreter | None = None,
                 settings: dict[str, Any] | None = None,
                 topics: dict[str, Any] | None = None,
                 context: Any | None = None) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Construire le noeud et son service. Le traducteur est injectable
            pour les tests hors ligne (aucun demon Ollama requis).

        Inputs:
            interprete (LlmInterpreter | None): traducteur commande -> action
            settings (dict | None): section 'devoir2' de la configuration
            topics (dict | None): section 'topics' de la configuration
            context (Any | None): contexte rclpy, celui par defaut si absent

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        super().__init__("llm_node", context=context)
        self._settings = settings if settings is not None else config.section("devoir2")
        self._topics = topics if topics is not None else config.section("topics")
        self._interprete = (
            interprete if interprete is not None else LlmInterpreter(self._settings)
        )
        # Mise en train des le demarrage (defaut mesure le 2026-09-20, VRAM
        # vide au demarrage : .sdd/6mig841-ameliorations/
        # vram-et-transcription-report.md, defaut 2). N'eleve jamais (R8) :
        # voir LlmInterpreter.demarrer().
        self._interprete.demarrer()
        erreur_demarrage = getattr(self._interprete, "erreur_demarrage", "")
        if erreur_demarrage:
            self.get_logger().error(
                f"[llm][ERREUR] Ollama n'est pas disponible : {erreur_demarrage}"
            )

        groupe = ReentrantCallbackGroup()
        self._service = self.create_service(
            Interpret, str(self._topics["interpret_service"]),
            self._on_interpret, callback_group=groupe,
        )

    def _on_interpret(self, request: Any, response: Any) -> Any:
        """
        --------------------------------------------------------------------------
        Purpose:
            Traduire request.commande en Step[], SANS JAMAIS LEVER : un service
            qui leve renvoie une exception au client rclpy, qui n'en sait rien
            faire (plan02.md, tableau des tests : « le service rapporte l'erreur
            sans lever »).

        Inputs:
            request (Interpret.Request): commande et historique
            response (Interpret.Response): reponse a completer

        Outputs:
            response (Interpret.Response): reponse completee
        --------------------------------------------------------------------------
        """
        try:
            historique_texte = formater_lignes(list(request.historique))
            resultat = self._interprete.interpreter(request.commande,
                                                    historique=historique_texte)
        except Exception as exc:  # rattrapage de surete, voir le docstring du module
            self.get_logger().error(f"[llm][ERREUR] service Interpret : {exc}")
            response.succes = False
            response.etapes = []
            response.justification = ""
            response.erreur = f"{type(exc).__name__}: {exc}"
            return response

        if not resultat.ok:
            self.get_logger().error(
                f"[llm][ERREUR] interprétation impossible : {resultat.erreur}"
            )
            response.succes = False
            response.etapes = []
            response.justification = ""
            response.erreur = resultat.erreur
            return response

        etapes = []
        for action in resultat.plan.etapes:
            etape = Step()
            etape.nom_action = action.nom
            etape.distance_m = float(action.distance_m)
            etape.angle_deg = float(action.angle_deg)
            etape.is_forward = bool(action.is_forward)
            etape.is_clockwise = bool(action.is_clockwise)
            etapes.append(etape)

        response.succes = True
        response.etapes = etapes
        response.justification = self._extraire_justification(resultat.brut)
        response.erreur = ""
        return response

    @staticmethod
    def _extraire_justification(brut: str) -> str:
        """
        --------------------------------------------------------------------------
        Purpose:
            Relire le champ 'justification' du JSON brut deja valide par
            LlmInterpreter, sans jamais lever : c'est un champ FACULTATIF du
            schema (construire_schema, llm_interpreter.py), son absence n'est
            pas une erreur.

        Inputs:
            brut (str): texte JSON rendu par le modele, deja verifie valide

        Outputs:
            justification (str): champ 'justification', vide s'il est absent
        --------------------------------------------------------------------------
        """
        try:
            charge = json.loads(brut)
        except (json.JSONDecodeError, TypeError):
            return ""
        if isinstance(charge, dict):
            return str(charge.get("justification", ""))
        return ""


def main(argv: list[str] | None = None) -> int:
    """
    --------------------------------------------------------------------------
    Purpose:
        Point d'entree du noeud : executeur multifil, groupe reentrant (voir
        docstring du module).

    Inputs:
        argv (list[str] | None): arguments rclpy, ceux de la ligne de commande
            si absents

    Outputs:
        code (int): code de sortie du processus
    --------------------------------------------------------------------------
    """
    rclpy.init(args=argv)
    node = LlmNode()
    executeur = MultiThreadedExecutor()
    executeur.add_node(node)
    try:
        executeur.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
